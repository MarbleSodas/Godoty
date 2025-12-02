"""
Model Management API Endpoints

Provides endpoints for fetching and managing AI models from OpenRouter.
Handles model listing, validation, and configuration updates.
"""

import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.model_service import ModelService

logger = logging.getLogger(__name__)

# Create FastAPI router
router = APIRouter()

# Global model service instance
model_service = ModelService()


class SetDefaultModelRequest(BaseModel):
    """Request model for setting default model."""
    model_id: str


@router.get("/available")
async def get_available_models():
    """
    Get list of available models from OpenRouter API.

    Returns:
        List of available models with metadata
    """
    try:
        models = await model_service.get_available_models()
        return {
            "success": True,
            "models": models,
            "count": len(models)
        }
    except Exception as e:
        logger.error(f"[Models] Failed to fetch available models: {e}")
        # Return fallback models on error
        fallback_models = model_service.get_fallback_models()
        return {
            "success": False,
            "models": fallback_models,
            "count": len(fallback_models),
            "error": str(e),
            "using_fallback": True
        }


@router.post("/default")
async def set_default_model(request: SetDefaultModelRequest):
    """
    Set the default model for the application.

    Args:
        request: Request containing model_id to set as default

    Returns:
        Success/error response
    """
    try:
        success = await model_service.set_default_model(request.model_id)

        if success:
            logger.info(f"[Models] Default model set to: {request.model_id}")
            return {
                "success": True,
                "message": "Default model updated successfully",
                "model_id": request.model_id
            }
        else:
            logger.warning(f"[Models] Invalid model ID attempted: {request.model_id}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid model ID: {request.model_id}"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Models] Failed to set default model {request.model_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to set default model: {str(e)}"
        )


@router.get("/validate/{model_id}")
async def validate_model(model_id: str):
    """
    Validate if a model ID exists and is available.

    Args:
        model_id: The model ID to validate

    Returns:
        Validation result with model details if valid
    """
    try:
        is_valid = await model_service.validate_model_id(model_id)

        if is_valid:
            model_details = await model_service.get_model_details(model_id)
            return {
                "valid": True,
                "model_id": model_id,
                "model": model_details
            }
        else:
            return {
                "valid": False,
                "model_id": model_id,
                "error": "Model not found or unavailable"
            }
    except Exception as e:
        logger.error(f"[Models] Error validating model {model_id}: {e}")
        return {
            "valid": False,
            "model_id": model_id,
            "error": str(e)
        }


@router.get("/details/{model_id}")
async def get_model_details(model_id: str):
    """
    Get detailed information about a specific model.

    Args:
        model_id: The model ID to get details for

    Returns:
        Model details or error if not found
    """
    try:
        model_details = await model_service.get_model_details(model_id)

        if model_details:
            return {
                "success": True,
                "model": model_details
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Model not found: {model_id}"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Models] Error getting model details for {model_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get model details: {str(e)}"
        )


@router.post("/cache/clear")
async def clear_model_cache():
    """
    Clear the model cache to force refresh on next request.

    Returns:
        Success response
    """
    try:
        model_service.clear_cache()
        return {
            "success": True,
            "message": "Model cache cleared successfully"
        }
    except Exception as e:
        logger.error(f"[Models] Error clearing cache: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear cache: {str(e)}"
        )


@router.get("/search")
async def search_models(
    query: str = Query(..., description="Search query for model names or descriptions"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of results")
):
    """
    Search for models by name or description.

    Args:
        query: Search query string
        limit: Maximum number of results to return

    Returns:
        List of matching models
    """
    try:
        models = await model_service.get_available_models()

        # Simple case-insensitive search
        query_lower = query.lower()
        matching_models = []

        for model in models:
            if (query_lower in model["name"].lower() or
                query_lower in model.get("description", "").lower()):
                matching_models.append(model)

                if len(matching_models) >= limit:
                    break

        return {
            "success": True,
            "query": query,
            "results": matching_models,
            "count": len(matching_models)
        }
    except Exception as e:
        logger.error(f"[Models] Error searching models with query '{query}': {e}")
        # Return fallback on error
        fallback_models = model_service.get_fallback_models()
        matching_fallback = [
            model for model in fallback_models
            if query.lower() in model["name"].lower()
        ]

        return {
            "success": False,
            "query": query,
            "results": matching_fallback,
            "count": len(matching_fallback),
            "error": str(e),
            "using_fallback": True
        }