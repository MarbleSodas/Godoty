"""
Background documentation rebuild manager.

Handles non-blocking documentation rebuilds using threading.
Works in both development and PyInstaller bundled environments.
"""

import os
import json
import threading
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

from user_data import get_docs_db_path, get_docs_rebuild_db_path, get_rebuild_status_path

logger = logging.getLogger(__name__)

# User data paths
STATUS_FILE = get_rebuild_status_path()
TEMP_DB_PATH = get_docs_rebuild_db_path()
FINAL_DB_PATH = get_docs_db_path()


class RebuildState(Enum):
    """Rebuild process states."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class DocumentationRebuildManager:
    """Manager for background documentation rebuilds using threading."""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._state = RebuildState.IDLE
        self._error: Optional[str] = None
        self._cancel_requested = False
        self._lock = threading.Lock()
        self._load_status()

    def _load_status(self) -> None:
        """Load rebuild status from file."""
        try:
            if STATUS_FILE.exists():
                with open(STATUS_FILE, 'r') as f:
                    data = json.load(f)
                    saved_state = data.get('state', RebuildState.IDLE.value)
                    # If we were running before, it means app was closed during rebuild
                    # Reset to idle in this case
                    if saved_state == RebuildState.RUNNING.value:
                        self._state = RebuildState.IDLE
                        self._save_status()
                    else:
                        self._state = RebuildState(saved_state)
                        if saved_state == RebuildState.ERROR.value:
                            self._error = data.get('error')
        except (json.JSONDecodeError, KeyError, ValueError):
            self._state = RebuildState.IDLE
            self._save_status()

    def _save_status(self, error: Optional[str] = None, progress: int = 0,
                      message: str = "", stage: str = "", 
                      files_processed: int = 0, files_total: int = 0) -> None:
        """Save rebuild status to file."""
        status_data = {
            'state': self._state.value,
            'timestamp': datetime.utcnow().isoformat(),
            'progress': progress,
            'message': message,
            'stage': stage,
            'files_processed': files_processed,
            'files_total': files_total,
        }
        if error:
            status_data['error'] = error

        try:
            with open(STATUS_FILE, 'w') as f:
                json.dump(status_data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save rebuild status: {e}")

    def _run_rebuild(self, godot_version: str, force: bool) -> None:
        """Run rebuild in background thread."""
        try:
            # Import here to avoid circular imports
            from scripts.build_docs_db import DocumentationBuilder

            logger.info(f"Starting documentation rebuild for Godot {godot_version}")

            # Define progress callback that saves to status file
            def on_progress(stage: str, progress: int, message: str, 
                          files_processed: int, files_total: int):
                """Save progress updates to status file."""
                self._save_status(
                    progress=progress,
                    message=message,
                    stage=stage,
                    files_processed=files_processed,
                    files_total=files_total
                )

            # Build directly using the DocumentationBuilder with progress callback
            builder = DocumentationBuilder(str(FINAL_DB_PATH))
            builder.build(godot_version=godot_version, force=force, 
                         progress_callback=on_progress)

            # Check if cancelled during build
            if self._cancel_requested:
                logger.info("Rebuild was cancelled")
                with self._lock:
                    self._state = RebuildState.IDLE
                    self._cancel_requested = False
                self._save_status()
                return

            logger.info("Documentation rebuild completed successfully")
            with self._lock:
                self._state = RebuildState.COMPLETED
                self._error = None
            self._save_status(progress=100, message="Documentation rebuild completed!", 
                            stage="completed")

        except Exception as e:
            logger.error(f"Documentation rebuild failed: {e}")
            with self._lock:
                self._state = RebuildState.ERROR
                self._error = str(e)
            self._save_status(error=str(e), message=f"Error: {str(e)}", stage="error")
        finally:
            with self._lock:
                self._thread = None

    def start_rebuild(self, godot_version: str, force_rebuild: bool = True) -> Dict[str, Any]:
        """
        Start a non-blocking documentation rebuild.

        Args:
            godot_version: Godot version to rebuild for
            force_rebuild: Force rebuild even if recent build exists

        Returns:
            Dictionary with rebuild status information
        """
        with self._lock:
            # Check if already running
            if self._state == RebuildState.RUNNING and self._thread and self._thread.is_alive():
                return {
                    "success": False,
                    "error": "Rebuild already in progress",
                    "state": self._state.value
                }

            # Reset cancel flag
            self._cancel_requested = False

            # Start background thread
            try:
                self._thread = threading.Thread(
                    target=self._run_rebuild,
                    args=(godot_version, force_rebuild),
                    daemon=True,
                    name="docs-rebuild"
                )
                self._thread.start()
                self._state = RebuildState.RUNNING
                self._error = None
                self._save_status()

                return {
                    "success": True,
                    "state": self._state.value,
                    "message": "Rebuild started in background",
                    "estimated_time": "3-5 minutes"
                }

            except Exception as e:
                logger.error(f"Failed to start rebuild: {e}")
                self._state = RebuildState.ERROR
                self._error = str(e)
                self._save_status(error=str(e))
                return {
                    "success": False,
                    "error": str(e),
                    "state": self._state.value
                }

    def get_status(self) -> Dict[str, Any]:
        """
        Get current rebuild status.

        Returns:
            Dictionary with current status information including progress
        """
        with self._lock:
            # Check if thread is still alive
            if self._state == RebuildState.RUNNING:
                if not self._thread or not self._thread.is_alive():
                    # Thread finished but state wasn't updated (shouldn't happen normally)
                    if self._error:
                        self._state = RebuildState.ERROR
                    else:
                        self._state = RebuildState.COMPLETED

            result = {
                "state": self._state.value,
                "timestamp": None,
                "error": self._error,
                "progress": 0,
                "message": "",
                "stage": "",
                "files_processed": 0,
                "files_total": 0,
            }

            # Load additional info from file
            try:
                if STATUS_FILE.exists():
                    with open(STATUS_FILE, 'r') as f:
                        data = json.load(f)
                        result['timestamp'] = data.get('timestamp')
                        result['progress'] = data.get('progress', 0)
                        result['message'] = data.get('message', '')
                        result['stage'] = data.get('stage', '')
                        result['files_processed'] = data.get('files_processed', 0)
                        result['files_total'] = data.get('files_total', 0)
            except Exception:
                pass

            return result

    def cancel_rebuild(self) -> Dict[str, Any]:
        """
        Request cancellation of the current rebuild.

        Note: Cancellation is cooperative - the rebuild thread checks the flag
        periodically and will stop at the next checkpoint.

        Returns:
            Dictionary with cancellation result
        """
        with self._lock:
            if self._state != RebuildState.RUNNING or not self._thread:
                return {
                    "success": False,
                    "error": "No rebuild in progress"
                }

            # Request cancellation
            self._cancel_requested = True

            # Clean up any temporary files
            try:
                if TEMP_DB_PATH.exists():
                    TEMP_DB_PATH.unlink()
            except Exception as e:
                logger.warning(f"Failed to clean up temp file: {e}")

            return {
                "success": True,
                "message": "Cancellation requested. Rebuild will stop at next checkpoint."
            }


# Global instance
_rebuild_manager: Optional[DocumentationRebuildManager] = None
_manager_lock = threading.Lock()


def get_rebuild_manager() -> DocumentationRebuildManager:
    """Get the singleton rebuild manager instance."""
    global _rebuild_manager

    with _manager_lock:
        if _rebuild_manager is None:
            _rebuild_manager = DocumentationRebuildManager()
        return _rebuild_manager
