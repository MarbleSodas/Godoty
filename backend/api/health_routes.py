"""
Health check endpoints for monitoring system status and integrations.
"""

import asyncio
import logging
import shutil
from typing import Dict, Any
from fastapi import APIRouter, HTTPException

from agents.config import AgentConfig
from agents.godoty_agent import get_godoty_agent
from rate_limiter import get_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])
limiter = get_limiter()


@router.get("/", response_model=Dict[str, Any])
@limiter.exempt
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

        # Check planning agent
        agent_status = {"status": "healthy", "details": {}}
        try:
            agent = get_godoty_agent()
            agent_status["details"] = {
                "initialized": True,
                "tools_count": len(agent.tools)
            }
        except Exception as e:
            agent_status["status"] = "unhealthy"
            agent_status["details"] = {"error": str(e)}
            logger.error(f"Planning agent health check failed: {e}")

        health_status["components"]["planning_agent"] = agent_status

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


@router.get("/godot", response_model=Dict[str, Any])
@limiter.exempt
async def godot_health():
    """
    Detailed Godot integration health check.

    Returns:
        Dictionary containing Godot-specific health information
    """
    try:
        from agents.tools.godot_bridge import get_godot_bridge

        bridge = get_godot_bridge()
        is_connected = await bridge.is_connected()

        result = {
            "status": "healthy" if is_connected else "unhealthy",
            "connected": is_connected,
            "plugin_accessible": True
        }

        if is_connected:
            try:
                project_info = await bridge.get_project_info()
                if project_info:
                    result["project_info"] = {
                        "project_path": project_info.project_path,
                        "scene_path": project_info.scene_path,
                        "engine_version": project_info.engine_version,
                        "is_ready": project_info.is_ready
                    }
            except Exception as e:
                logger.warning(f"Could not get project info: {e}")
                result["project_info_error"] = str(e)
        else:
            result["error"] = "Godot plugin not connected - ensure Godot Editor is running with Assistant plugin"

        return result

    except Exception as e:
        logger.error(f"Godot health check failed: {e}")
        return {
            "status": "unhealthy",
            "connected": False,
            "error": str(e),
            "plugin_accessible": False
        }


@router.get("/tools", response_model=Dict[str, Any])
@limiter.exempt
async def tools_health():
    """
    Health check for all available tools.

    Returns:
        Dictionary containing tool availability and status
    """
    try:
        from agents.tools import (
            # Basic tools
            read_file, list_files, search_codebase,
            search_documentation, fetch_webpage, get_godot_api_reference,
            # Godot tools
            ensure_godot_connection,
            get_project_overview, analyze_scene_tree, capture_visual_context, search_nodes,
            create_node, modify_node_property, create_scene, open_scene,
            select_nodes, play_scene, stop_playing,
            validate_operation, validate_path, validate_node_name
        )

        agent = get_godoty_agent()

        # Categorize tools
        tool_categories = {
            "file_system": ["read_file", "list_files", "search_codebase"],
            "web": ["search_documentation", "fetch_webpage", "get_godot_api_reference"],
            "godot_bridge": ["ensure_godot_connection"],
            "godot_debug": ["get_project_overview", "analyze_scene_tree", "capture_visual_context", "search_nodes"],
            "godot_executor": ["create_node", "modify_node_property", "create_scene", "open_scene", "select_nodes", "play_scene", "stop_playing"],
        }

        available_tools = {}
        for category, tool_names in tool_categories.items():
            available_tools[category] = {
                "tools": tool_names,
                "count": len(tool_names),
                "available": True
            }

        return {
            "status": "healthy",
            "total_tools": len(agent.tools),
            "categories": available_tools
        }

    except Exception as e:
        logger.error(f"Tools health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "total_tools": 0,
            "categories": {}
        }