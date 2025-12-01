"""
Godot Connection Monitor Service

Background service that maintains an active connection to the Godot plugin,
automatically reconnects on disconnect, and broadcasts connection state changes.
"""

import asyncio
import logging
import random
import time
from typing import Callable, List, Optional
from datetime import datetime, timedelta

from utils.serialization import json_serialize_safe

from agents.tools.godot_bridge import (
    GodotBridge, ConnectionState, get_godot_bridge,
    ConnectionErrorType, ConnectionErrorInfo
)

logger = logging.getLogger(__name__)


class ConnectionEvent:
    """Connection state change event."""

    def __init__(
        self,
        state: ConnectionState,
        timestamp: datetime,
        error: Optional[str] = None,
        project_path: Optional[str] = None,
        godot_version: Optional[str] = None,
        plugin_version: Optional[str] = None
    ):
        self.state = state
        self.timestamp = timestamp
        self.error = error
        self.project_path = project_path
        self.godot_version = godot_version
        self.plugin_version = plugin_version

    def to_dict(self):
        """Convert to dictionary for serialization."""
        return json_serialize_safe({
            "state": self.state.value,
            "timestamp": self.timestamp.isoformat(),
            "error": self.error,
            "project_path": self.project_path,
            "godot_version": self.godot_version,
            "plugin_version": self.plugin_version
        })


class GodotConnectionMonitor:
    """
    Background service for monitoring and maintaining Godot connection with adaptive retry logic.

    Features:
    - Periodic health checks (every 30 seconds)
    - Automatic reconnection on disconnect
    - Adaptive exponential backoff with jitter for failed reconnection
    - Error-aware retry strategies based on error types
    - Event broadcasting for connection state changes
    - Graceful handling when Godot is not running
    - Connection statistics and performance monitoring
    """

    def __init__(
        self,
        bridge: Optional[GodotBridge] = None,
        check_interval: float = 30.0,
        initial_backoff: float = 1.0,
        max_backoff: float = 300.0,
        backoff_multiplier: float = 2.0,
        jitter_factor: float = 0.25
    ):
        """
        Initialize connection monitor.

        Args:
            bridge: GodotBridge instance (defaults to singleton)
            check_interval: Health check interval in seconds
            initial_backoff: Initial backoff delay in seconds
            max_backoff: Maximum backoff delay in seconds (5 minutes default)
            backoff_multiplier: Backoff multiplier for exponential backoff
            jitter_factor: Jitter factor for preventing thundering herd (0.25 = ±25%)
        """
        self.bridge = bridge or get_godot_bridge()
        self.check_interval = check_interval
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff_multiplier = backoff_multiplier
        self.jitter_factor = jitter_factor

        # Monitor state
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._current_backoff = initial_backoff
        self._last_state = ConnectionState.DISCONNECTED
        self._last_connection_attempt: Optional[datetime] = None

        # Adaptive retry state
        self._consecutive_failures = 0
        self._last_successful_connection: Optional[datetime] = None
        self._failure_history: List[ConnectionErrorInfo] = []
        self._error_type_counters = {error_type: 0 for error_type in ConnectionErrorType}

        # Performance tracking
        self._total_connections = 0
        self._successful_connections = 0
        self._total_downtime = 0.0
        self._last_downtime_start: Optional[float] = None

        # Event listeners
        self._state_change_listeners: List[Callable[[ConnectionEvent], None]] = []

    def _calculate_adaptive_backoff(self, error_info: Optional[ConnectionErrorInfo] = None) -> float:
        """
        Calculate adaptive backoff delay based on error history and patterns.

        Args:
            error_info: Optional current error information

        Returns:
            Adaptive backoff delay in seconds
        """
        # Base exponential backoff
        base_delay = min(
            self.initial_backoff * (self.backoff_multiplier ** self._consecutive_failures),
            self.max_backoff
        )

        # Apply jitter to prevent thundering herd
        jitter_range = base_delay * self.jitter_factor
        jitter = random.uniform(-jitter_range, jitter_range)
        delay = base_delay + jitter

        # Error-type specific adjustments
        if error_info:
            if error_info.error_type == ConnectionErrorType.REFUSED_ERROR:
                # Godot not running - shorter backoff, check frequently
                delay = min(delay, 10.0)
            elif error_info.error_type == ConnectionErrorType.TIMEOUT_ERROR:
                # Timeout might be temporary - moderate backoff
                delay = min(delay, 30.0)
            elif error_info.error_type == ConnectionErrorType.NETWORK_ERROR:
                # Network issues might persist - longer backoff
                delay = max(delay, 15.0)

        # Pattern-based adjustments
        if len(self._failure_history) >= 3:
            # Check if we're in a failure pattern
            recent_failures = self._failure_history[-3:]
            same_error_type = all(f.error_type == recent_failures[0].error_type for f in recent_failures)

            if same_error_type:
                # Same error repeating - increase backoff
                delay *= 1.5

        # Time-based adjustments
        if self._last_successful_connection:
            time_since_success = (datetime.now() - self._last_successful_connection).total_seconds()
            if time_since_success > 3600:  # No success for over an hour
                # Reduce backoff to try more aggressively
                delay = min(delay, 20.0)

        # Ensure minimum delay
        return max(delay, 1.0)

    def _should_give_up(self, error_info: ConnectionErrorInfo) -> bool:
        """
        Determine if we should give up based on error patterns.

        Args:
            error_info: Current error information

        Returns:
            True if we should give up for now
        """
        # Never give up for recoverable errors
        if error_info.is_recoverable:
            return False

        # Give up after many consecutive non-recoverable errors
        if self._consecutive_failures >= 5:
            return True

        # Give up if we've seen the same non-recoverable error many times
        non_recoverable_count = sum(
            1 for f in self._failure_history
            if not f.is_recoverable and f.error_type == error_info.error_type
        )
        return non_recoverable_count >= 10

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
            # Get project info from bridge
            project_info = self.bridge.project_info

            event = ConnectionEvent(
                state=state,
                timestamp=datetime.now(),
                error=error,
                project_path=project_info.project_path if project_info else None,
                godot_version=project_info.godot_version if project_info else None,
                plugin_version=project_info.plugin_version if project_info else None
            )
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
        Attempt to connect to Godot with adaptive retry logic and enhanced error handling.

        Returns:
            True if connection successful, False otherwise
        """
        self._last_connection_attempt = datetime.now()
        self._total_connections += 1

        try:
            logger.debug("Attempting to connect to Godot...")
            await self._notify_state_change(ConnectionState.CONNECTING)

            success = await self.bridge.connect()

            if success:
                # Connection successful - update statistics
                self._successful_connections += 1
                self._consecutive_failures = 0
                self._current_backoff = self.initial_backoff  # Reset backoff on success
                self._last_successful_connection = datetime.now()

                # Calculate downtime if we were disconnected
                if self._last_downtime_start:
                    downtime = time.time() - self._last_downtime_start
                    self._total_downtime += downtime
                    self._last_downtime_start = None
                    logger.info(f"📊 Connection restored after {downtime:.1f}s downtime")

                success_rate = (self._successful_connections / self._total_connections) * 100
                logger.info(
                    f"✅ Successfully connected to Godot "
                    f"(success rate: {success_rate:.1f}%, "
                    f"attempts: {self._total_connections})"
                )

                # Automatically fetch project info after successful connection
                try:
                    project_info = await self.bridge.get_project_info()
                    if project_info:
                        logger.info(f"📁 Connected to project: {project_info.project_name}")
                        logger.info(f"📍 Project path: {project_info.project_path}")
                        logger.info(f"🔧 Godot version: {project_info.godot_version}")
                        logger.info(f"🔌 Plugin version: {project_info.plugin_version}")
                except Exception as e:
                    logger.warning(f"Failed to fetch project info after connection: {e}")

                await self._notify_state_change(ConnectionState.CONNECTED)
                return True
            else:
                # Connection failed - analyze error from bridge
                self._consecutive_failures += 1

                # Get error information from bridge
                error_info = getattr(self.bridge, 'last_connection_error', None)
                if error_info:
                    self._failure_history.append(error_info)
                    self._error_type_counters[error_info.error_type] += 1

                    # Log detailed failure information
                    logger.warning(
                        f"❌ Connection failed ({error_info.error_type.value}): {error_info.message} "
                        f"(consecutive failures: {self._consecutive_failures})"
                    )

                    # Check if we should give up
                    if self._should_give_up(error_info):
                        logger.error(f"🛑 Giving up on connection due to persistent non-recoverable errors")
                        await self._notify_state_change(ConnectionState.ERROR, error_info.message)
                        return False

                    # Calculate adaptive backoff for next attempt
                    self._current_backoff = self._calculate_adaptive_backoff(error_info)
                    logger.info(f"🔄 Next connection attempt in {self._current_backoff:.1f}s (adaptive backoff)")
                else:
                    logger.warning(f"⚠️ Connection failed with unknown error (attempt {self._consecutive_failures})")
                    self._current_backoff = self._calculate_adaptive_backoff()

                await self._notify_state_change(ConnectionState.DISCONNECTED, "Connection failed")
                return False

        except Exception as e:
            # Unexpected error during connection attempt
            self._consecutive_failures += 1
            error_msg = f"Unexpected error during connection: {str(e)}"
            logger.warning(error_msg)

            # Create error info for tracking
            error_info = ConnectionErrorInfo(
                error_type=ConnectionErrorType.UNKNOWN_ERROR,
                message=error_msg,
                original_exception=e,
                retry_count=self._consecutive_failures,
                is_recoverable=True
            )

            self._failure_history.append(error_info)
            self._error_type_counters[ConnectionErrorType.UNKNOWN_ERROR] += 1
            self._current_backoff = self._calculate_adaptive_backoff(error_info)

            await self._notify_state_change(ConnectionState.ERROR, error_msg)
            return False

    async def _check_connection_health(self) -> bool:
        """
        Check if connection is healthy with enhanced tracking and logging.

        Returns:
            True if connected and healthy, False otherwise
        """
        try:
            is_connected = await self.bridge.is_connected()

            if is_connected and self._last_state != ConnectionState.CONNECTED:
                # Connection regained
                if self._last_downtime_start:
                    downtime = time.time() - self._last_downtime_start
                    self._total_downtime += downtime
                    self._last_downtime_start = None
                    logger.info(f"📊 Connection health check: connection restored after {downtime:.1f}s downtime")

                await self._notify_state_change(ConnectionState.CONNECTED)
            elif not is_connected and self._last_state == ConnectionState.CONNECTED:
                # Connection lost
                logger.warning("⚠️ Connection lost to Godot during health check")
                self._last_downtime_start = time.time()
                await self._notify_state_change(ConnectionState.DISCONNECTED, "Connection lost during health check")

            return is_connected

        except Exception as e:
            logger.warning(f"Error checking connection health: {e}")
            if self._last_state == ConnectionState.CONNECTED:
                self._last_downtime_start = time.time()
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
        Get current monitor status with comprehensive statistics and performance metrics.

        Returns:
            Dictionary with detailed status information
        """
        project_info = self.bridge.project_info

        # Calculate success rate
        success_rate = 0.0
        if self._total_connections > 0:
            success_rate = (self._successful_connections / self._total_connections) * 100

        # Calculate uptime percentage (approximate)
        uptime_percentage = 100.0
        if self._total_connections > 1:  # Need some history
            total_time = sum(f.timestamp for f in self._failure_history[-10:])  # Last 10 failures
            if total_time > 0 and self._total_downtime > 0:
                uptime_percentage = max(0, 100 - (self._total_downtime / total_time) * 100)

        # Basic status
        status = {
            "running": self._running,
            "state": self._last_state.value,
            "last_attempt": self._last_connection_attempt.isoformat() if self._last_connection_attempt else None,
            "current_backoff": round(self._current_backoff, 2),
            "consecutive_failures": self._consecutive_failures,
            "project_path": project_info.project_path if project_info else None,
            "godot_version": project_info.godot_version if project_info else None,
            "plugin_version": project_info.plugin_version if project_info else None,
            "project_settings": project_info.project_settings if project_info else {}
        }

        # Performance statistics
        status["performance"] = {
            "total_connections": self._total_connections,
            "successful_connections": self._successful_connections,
            "success_rate": round(success_rate, 1),
            "total_downtime": round(self._total_downtime, 1),
            "uptime_percentage": round(uptime_percentage, 1),
            "last_successful_connection": self._last_successful_connection.isoformat() if self._last_successful_connection else None,
            "currently_in_downtime": self._last_downtime_start is not None
        }

        # Error statistics
        status["error_statistics"] = {
            "error_type_counts": {error_type.value: count for error_type, count in self._error_type_counters.items()},
            "recent_failures": len([f for f in self._failure_history if time.time() - f.timestamp < 3600]),  # Last hour
            "total_failures": len(self._failure_history)
        }

        # Bridge statistics (if available)
        try:
            bridge_stats = self.bridge.get_connection_stats()
            status["bridge_stats"] = bridge_stats
        except Exception as e:
            logger.warning(f"Failed to get bridge stats: {e}")
            status["bridge_stats"] = None

        # Adaptive retry information
        status["retry_logic"] = {
            "backoff_multiplier": self.backoff_multiplier,
            "max_backoff": self.max_backoff,
            "jitter_factor": self.jitter_factor,
            "adaptive_enabled": True
        }

        # Recent error details (last 3 errors)
        if self._failure_history:
            status["recent_errors"] = [
                {
                    "type": f.error_type.value,
                    "message": f.message,
                    "timestamp": f.timestamp,
                    "retry_count": f.retry_count,
                    "is_recoverable": f.is_recoverable
                }
                for f in self._failure_history[-3:]
            ]
        else:
            status["recent_errors"] = []

        logger.debug(
            f"get_status() - State: {status['state']}, "
            f"Success Rate: {success_rate:.1f}%, "
            f"Consecutive Failures: {self._consecutive_failures}, "
            f"Path: {status['project_path']}"
        )

        # Use safe serialization to handle numpy types and other non-JSON-serializable objects
        return json_serialize_safe(status)


# Global monitor instance
_monitor: Optional[GodotConnectionMonitor] = None


def get_connection_monitor() -> GodotConnectionMonitor:
    """Get or create the global connection monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = GodotConnectionMonitor()
    return _monitor
