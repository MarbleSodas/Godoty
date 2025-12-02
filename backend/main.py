"""
FastAPI application entry point for Godoty backend.

Provides API endpoints for Strands agent integration with OpenRouter.
"""

import logging
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# PyWebView imports (conditional to support both web and desktop modes)
try:
    import pywebview
    DESKTOP_MODE_AVAILABLE = True
except ImportError:
    DESKTOP_MODE_AVAILABLE = False
    pywebview = None

# Import application modules
from app.config import settings, validate_environment
from app.api.endpoints import router as api_router
from app.api.godot_status import router as godot_status_router
from app.api.models import router as models_router


# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("godoty.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    try:
        # Validate environment variables
        missing_vars = validate_environment()
        if missing_vars:
            logger.error(f"Missing environment variables: {missing_vars}")
            raise ValueError("Configuration incomplete")

        logger.info("Environment validation passed")
        logger.info(f"OpenRouter API configured for model: {settings.default_godoty_model}")

        yield

    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise

    finally:
        # Shutdown
        logger.info("Shutting down Godoty backend")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="Strands agent backend for Godot development assistance",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",  # Angular development server
        "http://localhost:8000",  # Backend itself
        "file://",               # PyWebView file protocol
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle uncaught exceptions globally."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc) if settings.debug else "An unexpected error occurred"
        }
    )


# Include API routes
app.include_router(api_router, prefix="/api/godoty")
app.include_router(godot_status_router, prefix="/api")
app.include_router(models_router, prefix="/api/godoty/models", tags=["models"])


# Root endpoint
@app.get("/")
async def root() -> dict:
    """Root endpoint with basic application info."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "model": settings.default_godoty_model,
    }


if __name__ == "__main__":
    # Run development server
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info" if not settings.debug else "debug",
    )