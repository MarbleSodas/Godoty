import threading
import signal
import os
import sys
import asyncio
import atexit
import gc

# CRITICAL: Set UTF-8 encoding BEFORE any other imports
# This prevents UnicodeEncodeError on Windows when logging emoji characters
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None
sys.stderr.reconfigure(encoding='utf-8') if hasattr(sys.stderr, 'reconfigure') else None

# CRITICAL: Suppress warnings BEFORE any other imports
# This must be set before importing uvicorn, fastapi, or agents
os.environ['PYTHONWARNINGS'] = 'ignore'

# Initialize user data directory early (~/.godoty/)
from user_data import ensure_user_data_dir
ensure_user_data_dir()

import uvicorn
import webview
import webbrowser
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import time
import platform
import warnings
import logging

# Setup logger for cleanup operations
cleanup_logger = logging.getLogger("cleanup")

# Aggressively suppress all LangGraph warnings
warnings.simplefilter("ignore", UserWarning)
warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")

def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller."""
    if getattr(sys, 'frozen', False):
        # Running in PyInstaller bundle
        base_path = sys._MEIPASS
    else:
        # Running in normal Python environment
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, relative_path)

# Global shutdown flag
shutdown_requested = False


async def cleanup_all_resources():
    """
    Comprehensive cleanup of all application resources.
    Called on application shutdown to prevent memory leaks.
    """
    cleanup_logger.info("Starting comprehensive resource cleanup...")
    
    # 1. Stop Godot connection monitor
    try:
        from services.godot_connection_monitor import get_connection_monitor, reset_connection_monitor
        monitor = get_connection_monitor()
        if monitor._running:
            await monitor.stop()
            cleanup_logger.info("Godot connection monitor stopped")
        reset_connection_monitor()
    except Exception as e:
        cleanup_logger.warning(f"Error stopping connection monitor: {e}")
    
    # 2. Disconnect Godot bridge and clear singleton
    try:
        from agents.tools.godot_bridge import get_godot_bridge, reset_godot_bridge
        bridge = get_godot_bridge()
        await bridge.disconnect()
        reset_godot_bridge()
        cleanup_logger.info("Godot bridge disconnected and cleared")
    except Exception as e:
        cleanup_logger.warning(f"Error disconnecting Godot bridge: {e}")
    
    # 3. Close database connections
    try:
        from database import get_db_manager
        import database.db_manager as dbm
        db_manager = get_db_manager()
        await db_manager.close()
        dbm._db_manager = None
        cleanup_logger.info("Database connections closed")
    except Exception as e:
        cleanup_logger.warning(f"Error closing database: {e}")
    
    # 4. Clear context engine
    try:
        from agents.tools.context_tools import set_context_engine
        set_context_engine(None)
        cleanup_logger.info("Context engine cleared")
    except Exception as e:
        cleanup_logger.warning(f"Error clearing context engine: {e}")
    
    # 5. Clear agent instances
    try:
        import agents.godoty_agent as ga
        if ga._godoty_agent_instance:
            ga._godoty_agent_instance = None
        cleanup_logger.info("Agent instances cleared")
    except Exception as e:
        cleanup_logger.warning(f"Error clearing agent instances: {e}")
    
    # 6. Clear config manager
    try:
        import config_manager as cm
        cm._config_manager = None
        cleanup_logger.info("Config manager cleared")
    except Exception as e:
        cleanup_logger.warning(f"Error clearing config manager: {e}")
    
    # 7. Clear auth instance
    try:
        import services.supabase_auth as sa
        sa._auth_instance = None
        cleanup_logger.info("Auth instance cleared")
    except Exception as e:
        cleanup_logger.warning(f"Error clearing auth instance: {e}")
    
    # 8. Clear streaming tracker
    try:
        import agents.event_utils as eu
        eu._streaming_tracker = None
        cleanup_logger.info("Streaming tracker cleared")
    except Exception as e:
        cleanup_logger.warning(f"Error clearing streaming tracker: {e}")
    
    # 9. Clear executor tools
    try:
        import agents.tools.godot_executor_tools as get
        get._godot_executor_tools_instance = None
        cleanup_logger.info("Executor tools cleared")
    except Exception as e:
        cleanup_logger.warning(f"Error clearing executor tools: {e}")
    
    # 10. Clear model config
    try:
        import agents.config.model_config as mc
        mc._model_config_instance = None
        cleanup_logger.info("Model config cleared")
    except Exception as e:
        cleanup_logger.warning(f"Error clearing model config: {e}")
    
    # 11. Clear agents db
    try:
        import agents.db as adb
        adb._db_instance = None
        cleanup_logger.info("Agents DB cleared")
    except Exception as e:
        cleanup_logger.warning(f"Error clearing agents DB: {e}")
    
    # 12. Force garbage collection
    gc.collect()
    cleanup_logger.info("Garbage collection completed")
    
    cleanup_logger.info("Resource cleanup completed")


def run_cleanup_sync():
    """Run async cleanup in a synchronous context."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(asyncio.wait_for(cleanup_all_resources(), timeout=10.0))
        loop.close()
    except asyncio.TimeoutError:
        cleanup_logger.warning("Cleanup timed out after 10 seconds")
    except Exception as e:
        cleanup_logger.warning(f"Error during cleanup: {e}")


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
    """
    # CRITICAL: Suppress warnings
    import warnings
    warnings.simplefilter("ignore", UserWarning)
    warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")

    # Configure logging
    import logging
    import sys
    
    # Setup basic logging configuration if not already set
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True  # Force reconfiguration to ensure our settings apply
    )
    
    # Set loggers to INFO for production
    logging.getLogger("agents").setLevel(logging.INFO)
    logging.getLogger("agents.event_utils").setLevel(logging.INFO)
    logging.getLogger("api.agent_routes").setLevel(logging.INFO)
    logging.getLogger("backend.agents").setLevel(logging.INFO)

    # Suppress websocket client ping/pong debug logs
    logging.getLogger("websockets.client").setLevel(logging.WARNING)
    logging.getLogger("websockets.server").setLevel(logging.WARNING)

    from fastapi.middleware.cors import CORSMiddleware
    from api import agent_router
    from api.health_routes import router as health_router
    from api.metrics_routes import router as metrics_router
    from api.sse_routes import router as sse_router
    from api.documentation_routes import router as documentation_router
    from api.config_routes import router as config_router
    from api.auth_routes import router as auth_router

    app = FastAPI(title="Godoty Desktop App", version="0.1.0-beta")

    # Add CORS middleware - restricted to localhost for security
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
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

    # Include documentation management routes
    app.include_router(documentation_router)

    # Include configuration management routes
    app.include_router(config_router)

    # Include authentication routes
    app.include_router(auth_router)

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
    
    # Path differs between dev mode and PyInstaller bundle
    if getattr(sys, 'frozen', False):
        # Running in PyInstaller bundle - dist is bundled at dist/browser
        dist_path = os.path.join(sys._MEIPASS, 'dist', 'browser')
    else:
        # Running in dev mode - dist is at ../dist/browser relative to backend
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
            'version': '0.1.0-beta',
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

    def open_url(self, url):
        """Open a URL in the default system browser."""
        if not url:
            return {'success': False, 'error': 'No URL provided'}
        
        try:
            webbrowser.open(url)
            return {'success': True}
        except Exception as e:
            print(f"Error opening URL {url}: {e}")
            return {'success': False, 'error': str(e)}


class UvicornServer:
    """
    Run uvicorn server in a background thread.
    This is simpler and more reliable than multiprocessing for PyInstaller builds.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8000):
        self.host = host
        self.port = port
        self.server = None
        self.thread = None

    def start(self):
        """Start the uvicorn server in a background thread."""
        app = create_app()
        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
        self.server = uvicorn.Server(config=config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop the uvicorn server gracefully."""
        if self.server:
            self.server.should_exit = True
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=3)


def main():
    """
    Main application entry point.
    Starts the FastAPI server in a background thread and pywebview in the main thread.
    """
    # Register cleanup on exit
    atexit.register(run_cleanup_sync)
    
    # Start uvicorn server in background thread
    server = UvicornServer(host="127.0.0.1", port=8000)
    server.start()

    # Give server time to start
    print("Starting FastAPI server...")
    time.sleep(2)
    print("Server started on http://127.0.0.1:8000")
    print("You can test the server at: http://127.0.0.1:8000/api/health")

    # Create Desktop API instance
    api = DesktopApi()

    # Create and start pywebview window in main thread
    url = "http://127.0.0.1:8000"
    print(f"Opening window at {url}")
    
    window = webview.create_window(
        'Godoty',
        url,
        js_api=api,
        width=1200,
        height=800,
        resizable=True,
        min_size=(800, 600)
    )

    # Start webview - this blocks until window is closed
    print("Application running. Close the window to exit.")
    webview.start(debug=False)

    # Cleanup after window closes
    print("Shutting down...")
    
    # Stop the uvicorn server first
    server.stop()
    
    # Run comprehensive cleanup
    print("Cleaning up resources...")
    run_cleanup_sync()
    
    # Force final garbage collection
    gc.collect()
    
    print("Application closed.")


if __name__ == '__main__':
    main()
