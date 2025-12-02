"""
Desktop application entry point for Godoty using PyWebView.

Launches the Angular frontend in a desktop window with Python backend integration.
"""

import logging
import os
import sys
from pathlib import Path

import pywebview
from flask import Flask

# Add backend to Python path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.config import settings
from pywebview.api_bridge import create_flask_bridge, api_bridge

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("godoty-desktop.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def create_desktop_app() -> Flask:
    """
    Create Flask application for desktop mode.

    Returns:
        Flask application instance with bridge routes
    """
    app = create_flask_bridge()

    # Add additional desktop-specific routes
    @app.route('/')
    def serve_frontend():
        """Serve the Angular frontend."""
        # This would serve the built Angular app
        # For now, return a simple HTML page
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Godoty Desktop</title>
            <meta charset="utf-8">
        </head>
        <body>
            <h1>Godoty Desktop Mode</h1>
            <p>Desktop application is running.</p>
            <p>API Bridge: <span id="bridge-status">Loading...</span></p>

            <script>
                fetch('/bridge/status')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('bridge-status').textContent =
                            data.active ? 'Active' : 'Inactive';
                    })
                    .catch(error => {
                        document.getElementById('bridge-status').textContent = 'Error';
                    });
            </script>
        </body>
        </html>
        '''

    return app


def start_desktop_app() -> None:
    """Start the desktop application with PyWebView."""
    try:
        logger.info(f"Starting {settings.app_name} desktop application")
        logger.info(f"Version: {settings.app_version}")
        logger.info(f"Model: {settings.default_godoty_model}")

        # Create Flask app for bridge communication
        flask_app = create_desktop_app()

        # Determine frontend URL
        if os.path.exists(os.path.join(backend_path.parent, "frontend", "dist")):
            # Production built frontend
            frontend_url = f"file://{backend_path.parent / 'frontend' / 'dist' / 'index.html'}"
            logger.info("Using built frontend")
        else:
            # Development server
            frontend_url = "http://localhost:4200"
            logger.info("Using development frontend server")

        # Create window
        window = pywebview.create_window(
            title=settings.app_name,
            url=frontend_url,
            js_api=api_bridge,
            width=1200,
            height=800,
            min_size=(800, 600)
        )

        # Initialize API bridge with window
        api_bridge.initialize(window)

        # Start Flask server in a separate thread
        import threading

        def run_flask():
            flask_app.run(
                host="127.0.0.1",
                port=5000,
                debug=False,
                use_reloader=False
            )

        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()

        # Start PyWebView
        logger.info("Starting PyWebView window...")
        pywebview.start()

    except Exception as e:
        logger.error(f"Failed to start desktop application: {e}")
        sys.exit(1)


def check_dependencies() -> bool:
    """
    Check if all required dependencies are available.

    Returns:
        True if all dependencies are available, False otherwise
    """
    try:
        import pywebview
        import flask
        return True
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        return False


def main() -> None:
    """Main entry point for desktop application."""
    logger.info("=== Godoty Desktop Application ===")

    # Check dependencies
    if not check_dependencies():
        logger.error("Missing required dependencies")
        sys.exit(1)

    # Check environment
    if not settings.openrouter_api_key:
        logger.error("OPENROUTER_API_KEY not configured")
        sys.exit(1)

    logger.info("All dependencies and environment checks passed")

    # Start desktop application
    start_desktop_app()


if __name__ == "__main__":
    main()