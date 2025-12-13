"""
Godoty Brain Entry Point

This script is the entry point for the PyInstaller bundle.
It starts the FastAPI server with uvicorn.
"""

import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Godoty Brain Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev only)")
    args = parser.parse_args()

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
