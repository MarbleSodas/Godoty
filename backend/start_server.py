"""
Simple startup script for Godoty backend server.

This script can be used to test the server without full dependency installation.
"""

import sys
import os
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

def main():
    """Main startup function."""
    print("=== Godoty Backend Server ===")
    print()

    # Check if .env file exists
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        print("⚠️  Warning: .env file not found")
        print("   Creating example .env file...")

        example_env = """# OpenRouter API Configuration
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Godoty Model Configuration
DEFAULT_GODOTY_MODEL=x-ai/grok-4.1-fast:free

# Application Configuration
APP_NAME=Godoty
APP_URL=http://localhost:8000

# Server Configuration
HOST=0.0.0.0
PORT=8000
DEBUG=false

# Session Management
SESSIONS_DIR=.godot/godoty_sessions

# OpenRouter API Settings
OPENROUTER_TIMEOUT=30

# Cost and Metrics Settings
COST_WARNING_THRESHOLD=1.0
ENABLE_METRICS=true

# File Security Settings
MAX_FILE_SIZE=10485760
ALLOWED_FILE_EXTENSIONS=[".gd",".cs",".tscn",".tres",".md",".txt"]
"""

        with open(env_file, 'w') as f:
            f.write(example_env)

        print("   ✅ Created .env file")
        print("   ⚠️  Please edit .env and add your OPENROUTER_API_KEY")
        print()

    # Test configuration loading
    try:
        from app.config import settings
        print("✅ Configuration loaded successfully")
        print(f"   - App Name: {settings.app_name}")
        print(f"   - Default Model: {settings.default_godoty_model}")
        print(f"   - API Key Configured: {'✅' if settings.openrouter_api_key else '❌'}")
        print()
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return False

    # Check if dependencies are available
    missing_deps = []

    try:
        import fastapi
        print("✅ FastAPI available")
    except ImportError:
        missing_deps.append("fastapi")
        print("❌ FastAPI not installed")

    try:
        import pydantic_settings
        print("✅ Pydantic Settings available")
    except ImportError:
        missing_deps.append("pydantic-settings")
        print("❌ Pydantic Settings not installed")

    try:
        import uvicorn
        print("✅ Uvicorn available")
    except ImportError:
        missing_deps.append("uvicorn")
        print("❌ Uvicorn not installed")

    if missing_deps:
        print()
        print(f"❌ Missing dependencies: {', '.join(missing_deps)}")
        print("   Install with: pip install " + " ".join(missing_deps))
        return False

    print()
    print("🚀 Starting server...")
    print("   Server will be available at: http://localhost:8000")
    print("   API Documentation: http://localhost:8000/docs")
    print("   Health Check: http://localhost:8000/api/godoty/health")
    print()
    print("Press Ctrl+C to stop the server")
    print()

    # Start the FastAPI server
    try:
        import uvicorn
        from main import app

        uvicorn.run(
            app,
            host=settings.host,
            port=settings.port,
            reload=settings.debug,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
        return True
    except Exception as e:
        print(f"❌ Server error: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)