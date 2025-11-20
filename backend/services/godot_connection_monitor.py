"""
Godot Connection Monitor Service

Background service that maintains an active connection to the Godot plugin,
automatically reconnects on disconnect, and broadcasts connection state changes.
"""

import asyncio
import logging
from typing import Callable, List, Optional
from datetime import datetime

from agents.tools.godot_bridge import GodotBridge, ConnectionState, get_godot_bridge

logger = logging.getLogger(__name__)


class ConnectionEvent:
    """Connection state change event."""

    def __init__(self, state: ConnectionState, timestamp: datetime, error: Optional[str] = None):
        self.state = state
        self.timestamp = timestamp
        self.error = error

    def to_dict(self):
        """Convert to dictionary for serialization."""
        return {
            "state": self.state.value,
            "timestamp": self.timestamp.isoformat(),
            "error": self.error
        }


class GodotConnectionMonitor:
    """
    Background service for monitoring and maintaining Godot connection.

    Features:
    - Periodic health checks (every 30 seconds)
    - Automatic reconnection on disconnect
    - Exponential backoff for failed reconnection (max 5 minutes)
    - Event broadcasting for connection state changes
    - Graceful handling when Godot is not running
    """

    def __init__(
        self,
        bridge: Optional[GodotBridge] = None,
        check_interval: float = 30.0,
        initial_backoff: float = 1.0,
        max_backoff: float = 300.0,
        backoff_multiplier: float = 2.0
    ):
        """
        Initialize connection monitor.

        Args:
            bridge: GodotBridge instance (defaults to singleton)
            check_interval: Health check interval in seconds
            initial_backoff: Initial backoff delay in seconds
            max_backoff: Maximum backoff delay in seconds (5 minutes default)
            backoff_multiplier: Backoff multiplier for exponential backoff
        """
        self.bridge = bridge or get_godot_bridge()
        self.check_interval = check_interval
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff_multiplier = backoff_multiplier

        # Monitor state
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._current_backoff = initial_backoff
        self._last_state = ConnectionState.DISCONNECTED
        self._last_connection_attempt: Optional[datetime] = None

        # Event listeners
        self._state_change_listeners: List[Callable[[ConnectionEvent], None]] = []

    def add_state_change_listener(self, callback: Callable[[ConnectionEvent], None]):
        """
        Add a callback for connection state changes.

        Args:
            callback: Function to call with ConnectionEvent when state changes
        """
        self._state_change_listeners.append(callback)

    def remove_state_change_listener(self, callback: Callable[[ConnectionEvent], None]):
        """Remove a state change listener."""
        if callback in self._state_change_listeners:
            self._state_change_listeners.remove(callback)

    async def _notify_state_change(self, state: ConnectionState, error: Optional[str] = None):
        """Notify all listeners of a state change."""
        if state != self._last_state:
            event = ConnectionEvent(state, datetime.now(), error)
            self._last_state = state

            logger.info(f"Godot connection state changed: {state.value}")

            # Call all listeners
            for listener in self._state_change_listeners:
                try:
                    if asyncio.iscoroutinefunction(listener):
                        await listener(event)
                    else:
                        listener(event)
                except Exception as e:
                    logger.error(f"Error in state change listener: {e}")

    async def _attempt_connection(self) -> bool:
        """
        Attempt to connect to Godot.

        Returns:
            True if connection successful, False otherwise
        """
        self._last_connection_attempt = datetime.now()

        try:
            logger.debug("Attempting to connect to Godot...")
            await self._notify_state_change(ConnectionState.CONNECTING)

            success = await self.bridge.connect()

            if success:
                logger.info("Successfully connected to Godot")
                self._current_backoff = self.initial_backoff  # Reset backoff on success
                await self._notify_state_change(ConnectionState.CONNECTED)
                return True
            else:
                logger.warning("Failed to connect to Godot (not running or not responding)")
                await self._notify_state_change(ConnectionState.DISCONNECTED, "Connection failed")
                return False

        except Exception as e:
            logger.warning(f"Error connecting to Godot: {e}")
            await self._notify_state_change(ConnectionState.ERROR, str(e))
            return False

    async def _check_connection_health(self) -> bool:
        """
        Check if connection is healthy.

        Returns:
            True if connected and healthy, False otherwise
        """
        try:
            is_connected = await self.bridge.is_connected()

            if is_connected and self._last_state != ConnectionState.CONNECTED:
                await self._notify_state_change(ConnectionState.CONNECTED)
            elif not is_connected and self._last_state == ConnectionState.CONNECTED:
                logger.warning("Lost connection to Godot")
                await self._notify_state_change(ConnectionState.DISCONNECTED, "Connection lost")

            return is_connected

        except Exception as e:
            logger.warning(f"Error checking connection health: {e}")
            if self._last_state == ConnectionState.CONNECTED:
                await self._notify_state_change(ConnectionState.ERROR, str(e))
            return False

    async def _monitor_loop(self):
        """Main monitoring loop."""
        logger.info("Godot connection monitor started")

        # Initial connection attempt
        await self._attempt_connection()

        while self._running:
            try:
                # Check if connected
                is_healthy = await self._check_connection_health()

                if not is_healthy:
                    # Not connected, attempt reconnection
                    logger.info(f"Attempting reconnection (backoff: {self._current_backoff}s)...")
                    success = await self._attempt_connection()

                    if not success:
                        # Increase backoff exponentially
                        self._current_backoff = min(
                            self._current_backoff * self.backoff_multiplier,
                            self.max_backoff
                        )
                        # Wait with backoff before next attempt
                        await asyncio.sleep(self._current_backoff)
                    else:
                        # Connected successfully, use normal check interval
                        await asyncio.sleep(self.check_interval)
                else:
                    # Already connected, wait for next check
                    await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                logger.info("Monitor loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(self.check_interval)

        logger.info("Godot connection monitor stopped")

    async def start(self):
        """Start the connection monitor."""
        if self._running:
            logger.warning("Connection monitor already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Starting Godot connection monitor...")

    async def stop(self):
        """Stop the connection monitor."""
        if not self._running:
            return

        logger.info("Stopping Godot connection monitor...")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def get_status(self) -> dict:
        """
        Get current monitor status.

        Returns:
            Dictionary with status information
        """
        project_info = self.bridge.project_info

        return {
            "running": self._running,
            "state": self._last_state.value,
            "last_attempt": self._last_connection_attempt.isoformat() if self._last_connection_attempt else None,
            "current_backoff": self._current_backoff,
            "project_path": project_info.project_path if project_info else None,
            "godot_version": project_info.godot_version if project_info else None,
            "plugin_version": project_info.plugin_version if project_info else None,
            "project_settings": project_info.project_settings if project_info else {}
        }


# Global monitor instance
_monitor: Optional[GodotConnectionMonitor] = None


def get_connection_monitor() -> GodotConnectionMonitor:
    """Get or create the global connection monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = GodotConnectionMonitor()
    return _monitor
