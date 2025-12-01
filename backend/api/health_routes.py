"""
Health check endpoints for monitoring system status and integrations.
"""

import asyncio
import logging
import shutil
from typing import Dict, Any
from fastapi import APIRouter, HTTPException

from agents.config import AgentConfig
from api.godoty_router import get_godoty_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/", response_model=Dict[str, Any])
async def health_check():
    """
    Comprehensive health check of all system components.

    Returns:
        Dictionary containing health status of all components
    """
    health_status = {
        "status": "healthy",
        "timestamp": asyncio.get_event_loop().time(),
        "components": {}
    }

    try:
        # Check configuration
        config_result = AgentConfig.validate()
        health_status["components"]["configuration"] = {
            "status": "healthy" if config_result["valid"] else "unhealthy",
            "details": {
                "valid": config_result["valid"],
                "godot_available": config_result["godot_available"],
                "mcp_available": config_result["mcp_available"],
                "errors": config_result["errors"],
                "warnings": config_result["warnings"]
            }
        }

        # Check Node.js/npm availability
        npx_available = shutil.which("npx") is not None
        health_status["components"]["nodejs"] = {
            "status": "healthy" if npx_available else "unhealthy",
            "details": {
                "npx_available": npx_available
            }
        }

        
        # Check Godot integration
        godot_status = {"status": "healthy", "details": {}}
        try:
            if config_result["godot_available"]:
                from agents.tools.godot_bridge import get_godot_bridge
                bridge = get_godot_bridge()
                is_connected = await bridge.is_connected()
                godot_status["details"] = {
                    "connected": is_connected,
                    "plugin_accessible": True
                }
                if not is_connected:
                    godot_status["status"] = "unhealthy"
                    godot_status["details"]["error"] = "Godot plugin not connected"
            else:
                godot_status["status"] = "disabled"
                godot_status["details"] = {"enabled": False}
        except Exception as e:
            godot_status["status"] = "unhealthy"
            godot_status["details"] = {"error": str(e)}
            logger.error(f"Godot health check failed: {e}")

        health_status["components"]["godot"] = godot_status

        # Check GodotyAgent
        agent_status = {"status": "healthy", "details": {}}
        try:
            agent = get_godoty_agent()
            agent_status["details"] = {
                "initialized": True,
                "tools_count": len(agent.tools) if hasattr(agent, 'tools') else 0
            }
        except Exception as e:
            agent_status["status"] = "unhealthy"
            agent_status["details"] = {"error": str(e)}
            logger.error(f"GodotyAgent health check failed: {e}")

        health_status["components"]["godoty_agent"] = agent_status

        # Determine overall status
        component_statuses = [comp["status"] for comp in health_status["components"].values()]
        if any(status == "unhealthy" for status in component_statuses):
            health_status["status"] = "degraded"
        if any(status == "unhealthy" for status in component_statuses if status != "disabled"):
            health_status["status"] = "unhealthy"

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        health_status["status"] = "unhealthy"
        health_status["error"] = str(e)

    return health_status






