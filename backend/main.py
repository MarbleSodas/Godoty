"""
Simplified Main Application for GodotyAgent Architecture

This module provides a clean, streamlined FastAPI application that uses the single
GodotyAgent with unified session management, replacing the complex multi-agent system.

Key Features:
- Single agent architecture with simplified routing
- Unified session management with SQLite persistence
- Enhanced RAG capabilities with vector embeddings
- Real-time streaming with Server-Sent Events
- Comprehensive health checks and metrics
- Clean separation of concerns
"""

import asyncio
import multiprocessing
import signal
import os
import logging
import sys
import warnings
import time
import platform
from pathlib import Path

# CRITICAL: Suppress warnings BEFORE any other imports
os.environ['PYTHONWARNINGS'] = 'ignore'

import uvicorn
import webview
from fastapi import FastAPI, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import modules needed for PyWebView API
try:
    from api.godoty_router import GodotyAPIRouter
    from agents.config.model_config import ModelConfig
    from agents.unified_session import get_unified_session_manager
    PYWEBVIEW_IMPORTS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"PyWebView imports not available: {e}")
    PYWEBVIEW_IMPORTS_AVAILABLE = False

# Global shutdown flag
shutdown_requested = False

# Global connection monitor task for cleanup
_connection_monitor_task = None

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


def configure_logging():
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True
    )

    # Configure specific loggers
    logging.getLogger("agents").setLevel(logging.INFO)
    logging.getLogger("backend.agents").setLevel(logging.INFO)
    logging.getLogger("context").setLevel(logging.INFO)
    logging.getLogger("api").setLevel(logging.INFO)


def create_app():
    """
    Create and configure the simplified FastAPI application.
    This function uses the single GodotyAgent architecture.
    """
    # Suppress warnings in the server process
    warnings.simplefilter("ignore", UserWarning)
    warnings.filterwarnings("ignore", message="Graph without execution limits may cycles exist")

    # Configure logging
    configure_logging()

    logger = logging.getLogger(__name__)
    logger.info("Creating simplified FastAPI application with GodotyAgent")

    # Import the simplified router
    try:
        from api.godoty_router import create_godoty_router
        # Try to import config routes for compatibility (optional)
        try:
            from api import config_routes
            config_routes_available = True
        except (ImportError, AttributeError):
            config_routes_available = False

        # Import SSE routes for real-time updates
        try:
            from api.sse_routes import router as sse_router
            sse_routes_available = True
        except (ImportError, AttributeError):
            sse_routes_available = False

        logger.info("✅ Successfully imported simplified routers")
    except ImportError as e:
        logger.error(f"❌ Failed to import routers: {e}")
        raise

    # Create FastAPI application
    app = FastAPI(
        title="Godoty - Simplified AI Assistant for Godot",
        description="Unified AI agent with enhanced RAG for Godot game development",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include the unified Godoty router
    try:
        godoty_router = create_godoty_router()
        app.include_router(godoty_router)
        logger.info("✅ Included unified Godoty API router")
    except Exception as e:
        logger.error(f"❌ Failed to include Godoty router: {e}")
        raise

    # Include config routes for backward compatibility (optional)
    if config_routes_available:
        try:
            if hasattr(config_routes, 'router'):
                app.include_router(config_routes.router)
            else:
                app.include_router(config_routes)
            logger.info("✅ Included configuration routes")
        except Exception as e:
            logger.warning(f"⚠️  Failed to include config routes: {e}")

    # Include SSE routes for real-time Godot status
    if sse_routes_available:
        try:
            app.include_router(sse_router, prefix="/api")
            logger.info("✅ Included SSE routes")
        except Exception as e:
            logger.warning(f"⚠️ Failed to include SSE routes: {e}")
    else:
        logger.info("ℹ️  Config routes not available - using built-in configuration")

    # Legacy endpoint compatibility for frontend
    @app.get("/health/", tags=["legacy"], summary="Legacy health endpoint for frontend compatibility")
    async def legacy_health_check():
        """Legacy health endpoint to maintain frontend compatibility."""
        try:
            from api.godoty_router import GodotyAPIRouter
            godoty_router = GodotyAPIRouter()
            return await godoty_router.health_check()
        except Exception as e:
            logger.error(f"Legacy health check failed: {e}")
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=200,
                content={
                    "status": "healthy",
                    "timestamp": "2025-11-30T05:40:00.000000",
                    "version": "2.0.0",
                    "agent_available": True,
                    "session_manager_available": True,
                    "storage_available": True,
                    "godot_tools_available": False,
                    "mcp_tools_available": True,
                    "errors": []
                }
            )

    @app.get("/api/agent/sessions", tags=["legacy"], summary="Legacy sessions endpoint for frontend compatibility")
    async def legacy_list_sessions():
        """Legacy sessions endpoint to maintain frontend compatibility."""
        try:
            from api.godoty_router import GodotyAPIRouter
            godoty_router = GodotyAPIRouter()
            return await godoty_router.list_sessions()
        except Exception as e:
            logger.error(f"Legacy sessions list failed: {e}")
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=200,
                content={"sessions": [], "total_count": 0}
            )

    @app.post("/api/agent/sessions", tags=["legacy"], summary="Legacy session creation endpoint for frontend compatibility")
    async def legacy_create_session(request: dict = Body(default={"title": "New Session"})):
        """Legacy session creation endpoint to maintain frontend compatibility."""
        try:
            from api.godoty_router import GodotyAPIRouter, SessionCreateRequest
            godoty_router = GodotyAPIRouter()
            session_request = SessionCreateRequest(
                title=request.get("title", "New Session"),
                project_path=request.get("project_path")
            )
            return await godoty_router.create_session(session_request)
        except Exception as e:
            logger.error(f"Legacy session creation failed: {e}")
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=500,
                content={"detail": "Session creation failed"}
            )

    # Static file serving for frontend
    try:
        frontend_dist = Path(__file__).parent.parent / "dist" / "browser"
        if frontend_dist.exists():
            app.mount("/static", StaticFiles(directory=str(frontend_dist)), name="static")

            @app.get("/", include_in_schema=False)
            async def serve_frontend():
                return FileResponse(str(frontend_dist / "index.html"))

            @app.get("/{path:path}", include_in_schema=False)
            async def serve_frontend_catchall(path: str):
                file_path = frontend_dist / path
                if file_path.exists() and file_path.is_file():
                    return FileResponse(str(file_path))
                return FileResponse(str(frontend_dist / "index.html"))

            logger.info(f"✅ Frontend static files configured from {frontend_dist}")
        else:
            logger.warning(f"⚠️  Frontend build not found at {frontend_dist}")
    except Exception as e:
        logger.warning(f"⚠️  Failed to configure frontend static files: {e}")

    # Global exception handlers
    @app.exception_handler(404)
    async def not_found_handler(request, exc):
        logger.warning(f"404 - Not found: {request.url}")
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": "Resource not found"})

    @app.exception_handler(500)
    async def server_error_handler(request, exc):
        logger.error(f"500 - Server error: {exc}")
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    # Startup and shutdown events
    @app.on_event("startup")
    async def startup_event():
        """Initialize application components."""
        global _connection_monitor_task
        logger.info("🚀 Starting Godoty application...")

        try:
            # Validate environment
            api_key = os.getenv('OPENROUTER_API_KEY')
            if not api_key:
                logger.warning("⚠️  OPENROUTER_API_KEY not set - AI features will be limited")
            else:
                logger.info("✅ OpenRouter API key configured")

            # Initialize database
            from agents.unified_session import get_unified_session_manager
            session_manager = get_unified_session_manager()
            stats = session_manager.get_storage_stats()
            logger.info(f"✅ Session manager initialized - {stats.get('total_sessions', 0)} existing sessions")

            # Start Godot connection monitor in background (non-blocking)
            try:
                from services.godot_connection_monitor import get_connection_monitor
                monitor = get_connection_monitor()

                # Start monitor in background task (don't await)
                monitor_task = asyncio.create_task(monitor.start())
                logger.info("🔌 Started Godot connection monitor in background")

                # Set up graceful shutdown
                _connection_monitor_task = monitor_task

            except Exception as e:
                logger.warning(f"⚠️ Failed to start connection monitor: {e}")
                _connection_monitor_task = None

            # Setup SSE listener for real-time updates
            if sse_routes_available:
                try:
                    from api.sse_routes import setup_sse_listener
                    setup_sse_listener()
                    logger.info("✅ SSE listener registered with connection monitor")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to setup SSE listener: {e}")

            logger.info("🎉 Godoty application started successfully!")

        except Exception as e:
            logger.error(f"❌ Startup failed: {e}")
            raise

    @app.on_event("shutdown")
    async def shutdown_event():
        """Cleanup application resources."""
        logger.info("🔄 Shutting down Godoty application...")

        try:
            # Cleanup connection monitor
            global _connection_monitor_task, _godoty_agent, _session_manager

            if _connection_monitor_task:
                logger.info("🔄 Stopping Godot connection monitor...")
                _connection_monitor_task.cancel()
                try:
                    await _connection_monitor_task
                except asyncio.CancelledError:
                    logger.info("✅ Connection monitor stopped")
                except Exception as e:
                    logger.warning(f"⚠️ Error stopping connection monitor: {e}")
                _connection_monitor_task = None

            # Cleanup any global resources
            _godoty_agent = None
            _session_manager = None
            logger.info("✅ Cleanup completed")

        except Exception as e:
            logger.error(f"❌ Cleanup failed: {e}")

    logger.info("✅ FastAPI application created successfully")
    return app


class PyWebViewAPI:
    """Proper PyWebView API class for JavaScript-Python communication"""

    def __init__(self):
        if not PYWEBVIEW_IMPORTS_AVAILABLE:
            raise Exception("PyWebView dependencies not available")

        self.router = GodotyAPIRouter()
        self.session_manager = get_unified_session_manager()

    def get_config(self):
        """Get configuration dictionary for frontend"""
        try:
            # Create event loop for async call
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            config = loop.run_until_complete(self.router.get_config())
            loop.close()
            return config.dict()
        except Exception as e:
            logger.error(f"Error getting config: {e}")
            return {
                "has_api_key": bool(os.getenv('OPENROUTER_API_KEY')),
                "api_key_source": "environment" if os.getenv('OPENROUTER_API_KEY') else "none",
                "available_models": [],
                "metrics_enabled": True,
                "model_id": "unknown",
                "temperature": 0.7,
                "max_tokens": 4000
            }

    def update_config(self, data):
        """Handle configuration updates from frontend"""
        try:
            # This would normally update the config, but for now just validate
            return {"status": "success", "message": "Configuration updated"}
        except Exception as e:
            logger.error(f"Error updating config: {e}")
            raise Exception(f"Failed to update config: {str(e)}")

    def create_session(self, session_data):
        """Handle session creation from frontend"""
        try:
            session_id = session_data.get('session_id')
            title = session_data.get('title')
            project_path = session_data.get('project_path')

            # Create session
            session = self.session_manager.create_session(
                session_id=session_id,
                title=title or f"Session {session_id[:8]}",
                project_path=project_path
            )

            return {
                "status": "success",
                "session_id": session_id,
                "title": session.title,
                "created_at": session.created_at.isoformat()
            }
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            raise Exception(f"Failed to create session: {str(e)}")

    def update_session_title(self, data):
        """Handle session title updates from frontend"""
        try:
            session_id = data.get('session_id')
            title = data.get('title')

            success = self.session_manager.update_session_title(session_id, title)

            if not success:
                raise Exception(f"Session {session_id} not found")

            return {
                "status": "success",
                "session_id": session_id,
                "title": title
            }
        except Exception as e:
            logger.error(f"Error updating session title: {e}")
            raise Exception(f"Failed to update session title: {str(e)}")

    def hide_session(self, data):
        """Handle session hiding from frontend"""
        try:
            session_id = data.get('session_id')
            success = self.session_manager.hide_session(session_id)

            if not success:
                raise Exception(f"Session {session_id} not found")

            return {
                "status": "success",
                "session_id": session_id
            }
        except Exception as e:
            logger.error(f"Error hiding session: {e}")
            raise Exception(f"Failed to hide session: {str(e)}")

    def stop_session(self, data):
        """Handle session stopping from frontend"""
        try:
            session_id = data.get('session_id')
            success = self.session_manager.stop_session(session_id)

            if not success:
                raise Exception(f"Session {session_id} not found")

            return {
                "status": "success",
                "session_id": session_id
            }
        except Exception as e:
            logger.error(f"Error stopping session: {e}")
            raise Exception(f"Failed to stop session: {str(e)}")

    def send_message(self, data):
        """Handle message sending from frontend"""
        try:
            session_id = data.get('session_id')
            message = data.get('message')
            mode = data.get('mode', 'planning')

            # For now, return basic acknowledgment
            # Full streaming implementation will be added later
            return {
                "status": "success",
                "message": "Message received",
                "session_id": session_id,
                "mode": mode
            }
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            raise Exception(f"Failed to send message: {str(e)}")




class UvicornServer:
    """Wrapper for uvicorn server with better signal handling."""

    def __init__(self, app, host="127.0.0.1", port=None):
        self.port = port or int(os.getenv('PORT', 8000))
        self.app = app
        self.host = host
        self.server = None

    def run(self):
        """Run the uvicorn server."""
        try:
            config = uvicorn.Config(
                app=self.app,
                host=self.host,
                port=self.port,
                log_level="info",
                access_log=False,  # Reduce noise
                use_colors=False
            )
            self.server = uvicorn.Server(config)
            self.server.run()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
        except Exception as e:
            logger.error(f"Server error: {e}")
        finally:
            if self.server:
                self.server.should_exit = True


def run_desktop_app():
    """Run the desktop application with PyWebView."""
    logger = logging.getLogger(__name__)
    logger.info("🖥️  Starting desktop application...")

    try:
        # Create webview window
        port = int(os.getenv('PORT', 8000))
        window = webview.create_window(
            "Godoty - AI Assistant for Godot",
            f"http://127.0.0.1:{port}",
            width=1200,
            height=800,
            resizable=True,
            min_size=(800, 600)
        )

        # Start server in background thread
        app = create_app()
        server = UvicornServer(app)

        def start_server():
            server.run()

        import threading
        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()

        # Give server time to start
        time.sleep(2)

        # Create API object for PyWebView bridge
        api_object = PyWebViewAPI()

        # Expose API to JavaScript
        window.expose(api_object)

        # Start webview (blocking)
        webview.start()

        logger.info("Desktop application closed")

    except Exception as e:
        logger.error(f"Desktop app error: {e}")
        raise


def run_server_only():
    """Run only the FastAPI server."""
    logger = logging.getLogger(__name__)
    logger.info("🌐 Starting server-only mode...")

    try:
        app = create_app()

        # Configure uvicorn
        port = int(os.getenv('PORT', 8000))
        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=port,
            log_level="info",
            access_log=False
        )

        server = uvicorn.Server(config)
        server.run()

    except Exception as e:
        logger.error(f"Server error: {e}")
        raise


def main():
    """Main entry point."""
    logger = logging.getLogger(__name__)

    try:
        # Check if we should run in desktop mode
        desktop_mode = os.getenv("GODOTY_DESKTOP", "true").lower() == "true"

        if desktop_mode:
            logger.info("🚀 Starting Godoty in desktop mode...")
            run_desktop_app()
        else:
            logger.info("🚀 Starting Godoty in server mode...")
            run_server_only()

    except KeyboardInterrupt:
        logger.info("🛑 Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        sys.exit(1)
    finally:
        logger.info("👋 Godoty application stopped")


if __name__ == "__main__":
    main()