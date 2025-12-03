import multiprocessing
import signal
import os
import sys

# CRITICAL: Set UTF-8 encoding BEFORE any other imports
# This prevents UnicodeEncodeError on Windows when logging emoji characters
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None
sys.stderr.reconfigure(encoding='utf-8') if hasattr(sys.stderr, 'reconfigure') else None

# CRITICAL: Suppress warnings BEFORE any other imports
# This must be set before importing uvicorn, fastapi, or agents
os.environ['PYTHONWARNINGS'] = 'ignore'

import uvicorn
import webview
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import time
import platform
import warnings

# Aggressively suppress all LangGraph warnings
warnings.simplefilter("ignore", UserWarning)
warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Global shutdown flag
shutdown_requested = False

def signal_handler(signum, frame):
    """Handle system signals for graceful shutdown."""
    global shutdown_requested
    print(f"\nReceived signal {signum}, initiating graceful shutdown...")
    shutdown_requested = True

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
if hasattr(signal, 'SIGBREAK'):
    signal.signal(signal.SIGBREAK, signal_handler)


def create_app():
    """
    Create and configure the FastAPI application.
    This function is called inside the server process to avoid pickling issues.
    """
    # CRITICAL: Suppress warnings in the server process
    # This runs in a separate process, so parent warnings config doesn't apply
    import warnings
    warnings.simplefilter("ignore", UserWarning)
    warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")

    # Configure logging
    import logging
    import sys
    
    # Setup basic logging configuration if not already set
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True  # Force reconfiguration to ensure our settings apply
    )
    
    # Ensure specific loggers are set to DEBUG for SSE debugging
    logging.getLogger("agents").setLevel(logging.DEBUG)
    logging.getLogger("agents.event_utils").setLevel(logging.DEBUG)
    logging.getLogger("api.agent_routes").setLevel(logging.DEBUG)
    logging.getLogger("backend.agents").setLevel(logging.DEBUG)

    # Suppress websocket client ping/pong debug logs
    logging.getLogger("websockets.client").setLevel(logging.WARNING)
    logging.getLogger("websockets.server").setLevel(logging.WARNING)

    from fastapi.middleware.cors import CORSMiddleware
    from api import agent_router
    from api.health_routes import router as health_router
    from api.metrics_routes import router as metrics_router
    from api.sse_routes import router as sse_router

    app = FastAPI(title="PyWebView Desktop App", version="1.0.0")

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include agent routes
    app.include_router(agent_router)

    # Include health check routes
    app.include_router(health_router)

    # Include metrics routes
    app.include_router(metrics_router)

    # Include SSE routes for real-time Godot status
    app.include_router(sse_router, prefix="/api")

    # FastAPI API Routes (must be defined before mounting static files)
    @app.get("/api/health")
    async def health():
        """Health check endpoint"""
        return {"status": "ok", "message": "FastAPI backend is running"}

    @app.get("/api/data")
    async def get_data():
        """Sample data endpoint"""
        return {
            "message": "Hello from FastAPI",
            "items": [
                {"id": 1, "name": "Item 1", "value": 100},
                {"id": 2, "name": "Item 2", "value": 200},
                {"id": 3, "name": "Item 3", "value": 300}
            ]
        }

    @app.post("/api/echo")
    async def echo(data: dict):
        """Echo endpoint for testing"""
        return {"received": data, "timestamp": time.time()}

    # Serve Angular static files
    # IMPORTANT: Mount static files LAST so API routes take precedence
    dist_path = os.path.join(os.path.dirname(__file__), '..', 'dist', 'browser')
    dist_path = os.path.abspath(dist_path)

    # Check if dist path exists
    if os.path.exists(dist_path):
        print(f"Serving static files from: {dist_path}")

        # Mount the entire browser directory as static files
        # html=True means it will serve index.html for directories
        # This will properly handle MIME types for all static assets
        app.mount("/", StaticFiles(directory=dist_path, html=True), name="static")
    else:
        print(f"Warning: dist path not found at {dist_path}")
        print("Please build the Angular app first with: cd frontend && npm run build")

    # Initialize database on startup
    @app.on_event("startup")
    async def startup_event():
        """Initialize database and connection monitor on application startup."""
        # Initialize metrics database
        try:
            from database import get_db_manager
            from agents.config import AgentConfig

            # Check if metrics tracking is enabled
            metrics_config = AgentConfig.get_metrics_config()
            if metrics_config.get("enabled", True):
                db_manager = get_db_manager()
                await db_manager.initialize()
                print("Metrics database initialized successfully")
        except Exception as e:
            print(f"Warning: Failed to initialize metrics database: {e}")

        # Start Godot connection monitor
        try:
            from services import get_connection_monitor
            from api.sse_routes import setup_sse_listener

            monitor = get_connection_monitor()
            await monitor.start()
            setup_sse_listener()  # Register SSE broadcaster with monitor
            print("Godot connection monitor started")
        except Exception as e:
            print(f"Warning: Failed to start Godot connection monitor: {e}")

    # Cleanup database on shutdown
    @app.on_event("shutdown")
    async def shutdown_event():
        """Cleanup database connections and connection monitor on shutdown."""
        # Stop Godot connection monitor
        try:
            from services import get_connection_monitor
            monitor = get_connection_monitor()
            await monitor.stop()
            print("Godot connection monitor stopped")
        except Exception as e:
            print(f"Warning: Failed to stop Godot connection monitor: {e}")

        # Close metrics database
        try:
            from database import get_db_manager
            from agents.config import AgentConfig

            metrics_config = AgentConfig.get_metrics_config()
            if metrics_config.get("enabled", True):
                db_manager = get_db_manager()
                await db_manager.close()
                print("Metrics database closed successfully")
        except Exception as e:
            print(f"Warning: Failed to close metrics database: {e}")

    return app


# Desktop API for JavaScript-Python bridge
class DesktopApi:
    """
    API class that exposes Python methods to JavaScript via pywebview.
    All methods here can be called from the Angular frontend using window.pywebview.api
    """

    def get_system_info(self):
        """Get system information"""
        return {
            'platform': platform.system(),
            'version': '1.0.0',
            'node_name': platform.node(),
            'python_version': platform.python_version(),
            'machine': platform.machine()
        }

    def save_file(self, data):
        """Save file using native file dialog"""
        # This is a placeholder - implement actual file saving logic
        return {'success': True, 'message': 'File saved successfully'}

    def open_file_dialog(self):
        """Open native file dialog"""
        # This would need to be called from main thread
        return {'path': '/path/to/file'}

    def get_godot_status(self):
        """Get Godot connection status and project info."""
        from agents.tools.godot_bridge import get_godot_bridge
        bridge = get_godot_bridge()
        
        # Check connection status (this is non-blocking check)
        is_connected = bridge.connection_state.value == "connected"
        
        # Get project info if available
        project_path = bridge.get_project_path()
        project_info = bridge.project_info
        
        return {
            'connected': is_connected,
            'status': bridge.connection_state.value,
            'project_path': project_path,
            'godot_version': project_info.godot_version if project_info else None,
            'plugin_version': project_info.plugin_version if project_info else None
        }


# Uvicorn Server Process
class UvicornServer(multiprocessing.Process):
    """
    Wrapper for uvicorn server to run in a separate process.
    This avoids conflicts with pywebview's event loop.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8000):
        super().__init__()
        self.host = host
        self.port = port
        self._shutdown_event = None

    def stop(self):
        """Stop the server process gracefully"""
        if self.is_alive():
            # Try graceful shutdown first
            self.terminate()
            # Wait a bit for graceful shutdown
            self.join(timeout=3)
            # Force kill if still alive
            if self.is_alive():
                self.kill()
                self.join(timeout=2)

    def run(self):
        """Run the uvicorn server"""
        try:
            app = create_app()
            config = uvicorn.Config(
                app,
                host=self.host,
                port=self.port,
                log_level="info"
            )
            server = uvicorn.Server(config=config)
            server.run()
        except Exception as e:
            print(f"Server error: {e}")
        finally:
            # Ensure clean exit
            import sys
            sys.exit(0)


def start_window(conn_send, url):
    """
    Start the pywebview window in a separate process.

    Args:
        conn_send: Pipe connection for sending close signal
        url: URL to load in the window
    """
    # Create Desktop API instance
    api = DesktopApi()

    # Create window
    window = webview.create_window(
        'PyWebView Desktop App',
        url,
        js_api=api,
        width=1200,
        height=800,
        resizable=True,
        min_size=(800, 600)
    )

    # Register closing event handler
    def on_closing():
        conn_send.send('closed')

    window.events.closing += on_closing

    # Start webview with debug mode enabled
    webview.start(debug=True)


def main():
    """
    Main application entry point.
    Starts both the FastAPI server and pywebview window using multiprocessing.
    """
    # Set multiprocessing start method
    multiprocessing.set_start_method('spawn')

    # Create pipe for inter-process communication
    conn_recv, conn_send = multiprocessing.Pipe()

    # Configure and start FastAPI server
    server = UvicornServer(host="127.0.0.1", port=8000)
    server.start()

    # Give server time to start
    print("Starting FastAPI server...")
    time.sleep(3)
    print("Server started on http://127.0.0.1:8000")
    print("You can test the server at: http://127.0.0.1:8000/api/health")

    # Start pywebview window
    url = "http://127.0.0.1:8000"
    print(f"Opening window at {url}")
    window_process = multiprocessing.Process(target=start_window, args=(conn_send, url))
    window_process.start()

    # Wait for window to close
    print("Application running. Close the window to exit.")
    window_status = ''

    try:
        while 'closed' not in window_status and not shutdown_requested:
            try:
                # Use non-blocking recv with timeout
                if conn_recv.poll(timeout=1):
                    window_status = conn_recv.recv()
                else:
                    # Check if processes are still alive
                    if not server.is_alive():
                        print("Server process died unexpectedly.")
                        break
                    if not window_process.is_alive():
                        print("Window process died unexpectedly.")
                        break
            except KeyboardInterrupt:
                print("\nReceived keyboard interrupt, shutting down...")
                break
            except (EOFError, OSError):
                # Connection closed unexpectedly
                print("Connection to window process lost.")
                break
    except Exception as e:
        print(f"Error in main loop: {e}")

    # Cleanup
    print("Shutting down...")

    try:
        # Stop window process first
        if window_process.is_alive():
            window_process.terminate()
            window_process.join(timeout=3)
            if window_process.is_alive():
                print("Force killing window process...")
                window_process.kill()
                window_process.join(timeout=2)
    except Exception as e:
        print(f"Error stopping window process: {e}")

    try:
        # Stop server process
        server.stop()
    except Exception as e:
        print(f"Error stopping server: {e}")

    # Close pipe connections
    try:
        conn_recv.close()
        conn_send.close()
    except:
        pass

    print("Application closed.")


if __name__ == '__main__':
    main()
