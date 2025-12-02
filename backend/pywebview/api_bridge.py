"""
PyWebView API bridge for desktop application integration.

Provides JavaScript ↔ Python communication bridge for desktop mode,
allowing the Angular frontend to call backend Python methods directly.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, Optional
import threading
import queue

import pywebview
from flask import Flask, request, jsonify

from app.main import app as fastapi_app
from app.config import settings

logger = logging.getLogger(__name__)


class APIBridge:
    """
    Bridge between frontend JavaScript and backend Python services.

    Handles method calls, event streaming, and state management for
    PyWebView desktop application mode.
    """

    def __init__(self):
        """Initialize API bridge."""
        self.window: Optional[pywebview.window] = None
        self.event_queue = queue.Queue()
        self.response_futures: Dict[str, asyncio.Future] = {}
        self.is_desktop_mode = True

        logger.info("Initialized PyWebView API bridge")

    def initialize(self, window: pywebview.window) -> None:
        """
        Initialize bridge with PyWebView window.

        Args:
            window: PyWebView window instance
        """
        self.window = window
        logger.info("API bridge initialized with PyWebView window")

    async def call_method(
        self,
        method_name: str,
        args: Optional[list] = None,
        kwargs: Optional[dict] = None
    ) -> Any:
        """
        Call a Python method from JavaScript.

        Args:
            method_name: Name of the method to call
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Method result
        """
        try:
            if args is None:
                args = []
            if kwargs is None:
                kwargs = {}

            # Generate unique call ID
            call_id = f"{method_name}_{hash(str(args) + str(kwargs))}"

            # Create future for response
            future = asyncio.Future()
            self.response_futures[call_id] = future

            # Prepare method call data
            call_data = {
                "type": "method_call",
                "call_id": call_id,
                "method": method_name,
                "args": args,
                "kwargs": kwargs
            }

            # Send to frontend
            if self.window:
                await self._send_to_frontend(call_data)

                # Wait for response
                try:
                    result = await asyncio.wait_for(future, timeout=30.0)
                    return result
                except asyncio.TimeoutError:
                    logger.error(f"Timeout waiting for method call {method_name}")
                    raise TimeoutError(f"Method call timeout: {method_name}")
            else:
                raise RuntimeError("PyWebView window not initialized")

        except Exception as e:
            logger.error(f"Error calling method {method_name}: {e}")
            raise

    async def _send_to_frontend(self, data: Dict[str, Any]) -> None:
        """
        Send data to frontend JavaScript.

        Args:
            data: Data to send
        """
        try:
            if self.window:
                # Convert to JSON string
                json_data = json.dumps(data)

                # Execute JavaScript in window
                js_code = f"""
                if (window.godotyBridge) {{
                    window.godotyBridge.receiveMessage({json_data});
                }} else {{
                    console.warn('Godoty bridge not found in window');
                }}
                """

                await self.window.evaluate_js(js_code)
                logger.debug(f"Sent data to frontend: {data.get('type', 'unknown')}")

        except Exception as e:
            logger.error(f"Error sending data to frontend: {e}")
            raise

    def handle_frontend_message(self, message_data: Dict[str, Any]) -> None:
        """
        Handle message from frontend JavaScript.

        Args:
            message_data: Message data from frontend
        """
        try:
            message_type = message_data.get("type")

            if message_type == "method_response":
                self._handle_method_response(message_data)
            elif message_type == "event":
                self._handle_frontend_event(message_data)
            else:
                logger.warning(f"Unknown message type: {message_type}")

        except Exception as e:
            logger.error(f"Error handling frontend message: {e}")

    def _handle_method_response(self, message_data: Dict[str, Any]) -> None:
        """Handle method response from frontend."""
        try:
            call_id = message_data.get("call_id")
            result = message_data.get("result")
            error = message_data.get("error")

            if call_id in self.response_futures:
                future = self.response_futures.pop(call_id)

                if error:
                    future.set_exception(Exception(error))
                else:
                    future.set_result(result)
            else:
                logger.warning(f"Received response for unknown call ID: {call_id}")

        except Exception as e:
            logger.error(f"Error handling method response: {e}")

    def _handle_frontend_event(self, message_data: Dict[str, Any]) -> None:
        """Handle event from frontend."""
        try:
            event_name = message_data.get("event")
            event_data = message_data.get("data", {})

            logger.info(f"Received frontend event: {event_name}")

            # Route event to appropriate handler
            if event_name == "session_created":
                self._on_session_created(event_data)
            elif event_name == "chat_message":
                self._on_chat_message(event_data)
            elif event_name == "session_closed":
                self._on_session_closed(event_data)
            else:
                logger.debug(f"Unhandled event: {event_name}")

        except Exception as e:
            logger.error(f"Error handling frontend event: {e}")

    def _on_session_created(self, data: Dict[str, Any]) -> None:
        """Handle session created event."""
        logger.info(f"Session created: {data}")

    def _on_chat_message(self, data: Dict[str, Any]) -> None:
        """Handle chat message event."""
        logger.info(f"Chat message: {data}")

    def _on_session_closed(self, data: Dict[str, Any]) -> None:
        """Handle session closed event."""
        logger.info(f"Session closed: {data}")

    def expose_to_js(self) -> Dict[str, Callable]:
        """
        Get methods to expose to JavaScript.

        Returns:
            Dictionary of method name -> callable
        """
        return {
            "getAppInfo": self._get_app_info,
            "createSession": self._create_session,
            "listSessions": self._list_sessions,
            "sendMessage": self._send_message,
            "getMetrics": self._get_metrics,
            "checkConnection": self._check_connection,
            "closeApp": self._close_app
        }

    async def _get_app_info(self) -> Dict[str, Any]:
        """Get application information."""
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "model": settings.default_godoty_model,
            "desktop_mode": True
        }

    async def _create_session(self, title: str, project_path: str) -> Dict[str, Any]:
        """Create a new session."""
        # This would call the actual session creation logic
        # For now, return mock data
        return {
            "session_id": "mock_session_id",
            "title": title,
            "project_path": project_path,
            "created_at": "2024-01-01T00:00:00Z"
        }

    async def _list_sessions(self, project_path: str) -> list:
        """List sessions for a project."""
        # This would call the actual session listing logic
        return []

    async def _send_message(self, session_id: str, message: str) -> Dict[str, Any]:
        """Send a chat message."""
        # This would call the actual message sending logic
        return {
            "session_id": session_id,
            "response": f"Mock response to: {message[:50]}...",
            "timestamp": "2024-01-01T00:00:00Z"
        }

    async def _get_metrics(self) -> Dict[str, Any]:
        """Get usage metrics."""
        # This would call the actual metrics collection
        return {
            "total_sessions": 0,
            "total_messages": 0,
            "total_cost": 0.0
        }

    async def _check_connection(self) -> Dict[str, Any]:
        """Check OpenRouter connection."""
        return {
            "connected": bool(settings.openrouter_api_key),
            "model": settings.default_godoty_model
        }

    async def _close_app(self) -> None:
        """Close the application."""
        if self.window:
            self.window.destroy()


# Global API bridge instance
api_bridge = APIBridge()


def create_flask_bridge() -> Flask:
    """
    Create Flask app for PyWebView bridge communication.

    Returns:
        Flask application instance
    """
    flask_app = Flask(__name__)

    @flask_app.route('/bridge/message', methods=['POST'])
    def handle_message():
        """Handle message from frontend."""
        try:
            data = request.get_json()
            api_bridge.handle_frontend_message(data)
            return jsonify({"status": "ok"})

        except Exception as e:
            logger.error(f"Error in bridge message handler: {e}")
            return jsonify({"error": str(e)}), 500

    @flask_app.route('/bridge/method', methods=['POST'])
    def handle_method_call():
        """Handle method call from frontend."""
        try:
            data = request.get_json()
            method_name = data.get("method")
            args = data.get("args", [])
            kwargs = data.get("kwargs", {})

            # Get exposed methods
            methods = api_bridge.expose_to_js()

            if method_name in methods:
                # Call method (sync for Flask)
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                try:
                    result = loop.run_until_complete(
                        methods[method_name](*args, **kwargs)
                    )
                    return jsonify({"result": result})
                finally:
                    loop.close()
            else:
                return jsonify({"error": f"Unknown method: {method_name}"}), 404

        except Exception as e:
            logger.error(f"Error in bridge method handler: {e}")
            return jsonify({"error": str(e)}), 500

    @flask_app.route('/bridge/status')
    def bridge_status():
        """Get bridge status."""
        return jsonify({
            "active": True,
            "desktop_mode": True,
            "api_bridge_initialized": api_bridge.window is not None
        })

    return flask_app


def get_bridge_js_code() -> str:
    """
    Get JavaScript code for frontend bridge integration.

    Returns:
        JavaScript code as string
    """
    return """
class GodotyBridge {
    constructor() {
        this.messageId = 0;
        this.pendingResponses = new Map();
        this.eventListeners = new Map();

        // Initialize bridge
        if (window.pywebview) {
            this.pywebviewMode = true;
        } else {
            this.pywebviewMode = false;
        }
    }

    async callMethod(methodName, args = [], kwargs = {}) {
        const messageId = ++this.messageId;

        return new Promise((resolve, reject) => {
            this.pendingResponses.set(messageId, { resolve, reject });

            const message = {
                type: 'method_call',
                messageId: messageId,
                method: methodName,
                args: args,
                kwargs: kwargs
            };

            this.sendMessage(message);

            // Timeout after 30 seconds
            setTimeout(() => {
                if (this.pendingResponses.has(messageId)) {
                    this.pendingResponses.delete(messageId);
                    reject(new Error('Method call timeout'));
                }
            }, 30000);
        });
    }

    sendMessage(message) {
        if (this.pywebviewMode && window.pywebview) {
            // Send via pywebview API
            window.pywebview.api.sendMessage(message);
        } else {
            // Send via HTTP API for browser mode
            fetch('/api/bridge/message', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(message)
            }).catch(error => {
                console.error('Bridge message error:', error);
            });
        }
    }

    receiveMessage(message) {
        const { messageId, result, error, type } = message;

        if (type === 'method_response' && messageId) {
            const pending = this.pendingResponses.get(messageId);
            if (pending) {
                this.pendingResponses.delete(messageId);

                if (error) {
                    pending.reject(new Error(error));
                } else {
                    pending.resolve(result);
                }
            }
        } else if (type === 'event') {
            this.emitEvent(message.event, message.data);
        }
    }

    emitEvent(eventName, data) {
        const listeners = this.eventListeners.get(eventName) || [];
        listeners.forEach(listener => {
            try {
                listener(data);
            } catch (error) {
                console.error('Event listener error:', error);
            }
        });
    }

    addEventListener(eventName, listener) {
        if (!this.eventListeners.has(eventName)) {
            this.eventListeners.set(eventName, []);
        }
        this.eventListeners.get(eventName).push(listener);
    }

    removeEventListener(eventName, listener) {
        const listeners = this.eventListeners.get(eventName);
        if (listeners) {
            const index = listeners.indexOf(listener);
            if (index > -1) {
                listeners.splice(index, 1);
            }
        }
    }
}

// Initialize global bridge
window.godotyBridge = new GodotyBridge();
"""