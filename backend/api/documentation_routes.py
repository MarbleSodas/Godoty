"""
API endpoints for documentation management.

Provides REST API endpoints for checking documentation status and triggering rebuilds.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any

router = APIRouter(prefix="/api/documentation", tags=["documentation"])


def _format_godot_version(version: str) -> str:
    """
    Convert Godot version format.

    Args:
        version: Raw version string (e.g., "4.3.stable.official")

    Returns:
        Formatted version (e.g., "4.3-stable")
    """
    parts = version.split('.')
    if len(parts) >= 3 and parts[2] in ['stable', 'beta', 'rc', 'dev']:
        return f"{parts[0]}.{parts[1]}-{parts[2]}"
    return version


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    """
    Get current documentation database status.

    Returns basic status information about the documentation database
    including whether it exists, size, version, and statistics.

    Returns:
        Documentation status information
    """
    try:
        # Import the tool function
        from agents.tools.godot_docs_tools import get_documentation_status

        # Call the tool directly
        result = get_documentation_status()
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get documentation status: {str(e)}")


@router.get("/godot-version")
async def get_godot_version() -> Dict[str, Any]:
    """
    Get the Godot editor version from the connected Godot plugin.

    Returns:
        Dictionary with Godot version information or error if not connected
    """
    try:
        from agents.tools.godot_bridge import get_godot_bridge

        bridge = get_godot_bridge()

        # Check if connected and has project info
        if bridge.project_info and bridge.project_info.godot_version:
            version = bridge.project_info.godot_version
            formatted_version = _format_godot_version(version)

            return {
                "success": True,
                "connected": True,
                "godot_version": version,
                "formatted_version": formatted_version,
                "project_name": bridge.project_info.project_name,
                "project_path": bridge.project_info.project_path
            }
        else:
            return {
                "success": False,
                "connected": False,
                "error": "Godot editor not connected or version not available",
                "message": "Please ensure the Godot editor is running with the AI plugin enabled"
            }

    except Exception as e:
        return {
            "success": False,
            "connected": False,
            "error": f"Failed to get Godot version: {str(e)}"
        }


@router.post("/rebuild")
async def rebuild_documentation(
    force_rebuild: bool = True,
    godot_version: str = None
) -> Dict[str, Any]:
    """
    Start a non-blocking documentation database rebuild.

    Triggers the build script to run in the background without blocking the API.
    Users can continue using other features while the rebuild runs.

    Args:
        force_rebuild: Force rebuild even if database exists (default: True)
        godot_version: Godot version/branch to build docs for (optional, auto-detects from connected Godot editor)

    Returns:
        Rebuild operation status - returns immediately with background task info
    """
    try:
        # Import the rebuild manager
        from services.documentation_rebuild_manager import get_rebuild_manager

        # If no version specified, try to get it from the connected Godot editor
        if not godot_version:
            try:
                from agents.tools.godot_bridge import get_godot_bridge

                bridge = get_godot_bridge()

                if bridge.project_info and bridge.project_info.godot_version:
                    version = bridge.project_info.godot_version
                    godot_version = _format_godot_version(version)
                else:
                    godot_version = "4.5.1-stable"  # Fallback if not connected
            except Exception as e:
                godot_version = "4.5.1-stable"  # Fallback on error

        # Get rebuild manager and start background rebuild
        manager = get_rebuild_manager()
        result = manager.start_rebuild(godot_version, force_rebuild)

        if result["success"]:
            return {
                "status": "started",
                "message": "Documentation rebuild started in background",
                "estimated_time": "3-5 minutes",
                "godot_version": godot_version,
                "rebuild_state": result["state"]
            }
        else:
            return {
                "status": "error",
                "error": result.get("error", "Unknown error"),
                "rebuild_state": result["state"]
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start rebuild: {str(e)}")


@router.get("/rebuild/status")
async def get_rebuild_status() -> Dict[str, Any]:
    """
    Get current documentation rebuild status.

    Returns:
        Current rebuild state, timestamp, and process information
    """
    try:
        from services.documentation_rebuild_manager import get_rebuild_manager

        manager = get_rebuild_manager()
        status = manager.get_status()

        return {
            "success": True,
            "rebuild_state": status["state"],
            "running": status["state"] == "running",
            "timestamp": status.get("timestamp"),
            "error": status.get("error"),
            "progress": status.get("progress", 0),
            "message": status.get("message", ""),
            "stage": status.get("stage", ""),
            "files_processed": status.get("files_processed", 0),
            "files_total": status.get("files_total", 0),
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to get rebuild status: {str(e)}",
            "rebuild_state": "idle",
            "running": False
        }


@router.delete("/rebuild/cancel")
async def cancel_rebuild() -> Dict[str, Any]:
    """
    Cancel the currently running documentation rebuild.

    Returns:
        Cancellation result
    """
    try:
        from services.documentation_rebuild_manager import get_rebuild_manager

        manager = get_rebuild_manager()
        result = manager.cancel_rebuild()

        if result["success"]:
            return {
                "success": True,
                "message": result["message"],
                "rebuild_state": "idle"
            }
        else:
            return {
                "success": False,
                "error": result["error"],
                "rebuild_state": manager.get_status()["state"]
            }

    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to cancel rebuild: {str(e)}"
        }
