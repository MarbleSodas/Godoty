"""
Server-Sent Events (SSE) streaming utilities for Godoty API.

Provides SSE streaming functionality for real-time communication with the frontend,
compatible with the existing frontend MessageEvent interface.
"""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, Optional
from contextlib import asynccontextmanager

from fastapi import Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)


class SSEStreamer:
    """
    Server-Sent Events streamer for real-time communication.

    Provides async streaming functionality that converts agent events
    to SSE format compatible with the frontend expectations.
    """

    def __init__(self):
        """Initialize SSE streamer."""
        self.active_streams: Dict[str, asyncio.Queue] = {}

    async def create_stream(self, stream_id: str) -> asyncio.Queue:
        """
        Create a new SSE stream.

        Args:
            stream_id: Unique identifier for the stream

        Returns:
            Queue for sending events to the stream
        """
        queue = asyncio.Queue()
        self.active_streams[stream_id] = queue
        logger.debug(f"Created SSE stream: {stream_id}")
        return queue

    async def remove_stream(self, stream_id: str) -> None:
        """
        Remove an SSE stream.

        Args:
            stream_id: Stream identifier to remove
        """
        if stream_id in self.active_streams:
            del self.active_streams[stream_id]
            logger.debug(f"Removed SSE stream: {stream_id}")

    async def send_event(self, stream_id: str, event: Dict[str, Any]) -> bool:
        """
        Send an event to a specific stream.

        Args:
            stream_id: Stream identifier
            event: Event data to send

        Returns:
            True if sent successfully, False if stream not found
        """
        try:
            if stream_id not in self.active_streams:
                logger.warning(f"Stream not found: {stream_id}")
                return False

            queue = self.active_streams[stream_id]
            sse_data = self._format_sse_event(event)
            await queue.put(sse_data)
            return True

        except Exception as e:
            logger.error(f"Error sending event to stream {stream_id}: {e}")
            return False

    def _format_sse_event(self, event: Dict[str, Any]) -> str:
        """
        Format event data as SSE message.

        Args:
            event: Event data dictionary

        Returns:
            Formatted SSE string
        """
        try:
            # Convert event to JSON
            event_json = json.dumps(event, ensure_ascii=False)

            # Format as SSE message
            # Note: The frontend expects specific event types
            sse_lines = [
                f"data: {event_json}",
                "",  # Empty line to end message
                ""   # Extra empty line for SSE format
            ]

            return "\n".join(sse_lines)

        except Exception as e:
            logger.error(f"Error formatting SSE event: {e}")
            # Send error event
            error_event = {
                "type": "error",
                "error": {
                    "type": "format_error",
                    "message": str(e)
                }
            }
            return f"data: {json.dumps(error_event)}\n\n"

    async def stream_generator(self, stream_id: str, queue: asyncio.Queue) -> AsyncGenerator[str, None]:
        """
        Generate SSE stream from queue events.

        Args:
            stream_id: Stream identifier
            queue: Event queue for the stream

        Yields:
            Formatted SSE strings
        """
        try:
            logger.info(f"Starting SSE stream: {stream_id}")

            # Send initial connection event
            initial_event = {
                "type": "connected",
                "stream_id": stream_id,
                "timestamp": self._get_timestamp()
            }
            yield self._format_sse_event(initial_event)

            # Process events from queue
            while True:
                try:
                    # Wait for event with timeout
                    event_data = await asyncio.wait_for(queue.get(), timeout=30.0)

                    # Send event
                    yield event_data

                    # Check for termination event
                    if isinstance(event_data, str) and '"type":"done"' in event_data:
                        logger.debug(f"Stream {stream_id} received done event")
                        break

                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    heartbeat = {
                        "type": "heartbeat",
                        "timestamp": self._get_timestamp()
                    }
                    yield self._format_sse_event(heartbeat)

                except Exception as e:
                    logger.error(f"Error processing stream event for {stream_id}: {e}")
                    error_event = {
                        "type": "stream_error",
                        "error": {
                            "message": str(e)
                        }
                    }
                    yield self._format_sse_event(error_event)

        except asyncio.CancelledError:
            logger.info(f"Stream {stream_id} cancelled")
        except Exception as e:
            logger.error(f"Stream {stream_id} error: {e}")
            error_event = {
                "type": "stream_terminated",
                "error": {
                    "message": str(e)
                }
            }
            yield self._format_sse_event(error_event)
        finally:
            # Clean up stream
            await self.remove_stream(stream_id)
            logger.info(f"Ended SSE stream: {stream_id}")

    def _get_timestamp(self) -> str:
        """Get current timestamp as ISO string."""
        from datetime import datetime
        return datetime.utcnow().isoformat()


class AgentEventStreamer:
    """
    Bridge between agent events and SSE streaming.

    Converts Strands agent events to frontend-compatible format
    and streams them via SSE.
    """

    def __init__(self, sse_streamer: SSEStreamer):
        """
        Initialize agent event streamer.

        Args:
            sse_streamer: SSE streamer instance
        """
        self.sse_streamer = sse_streamer
        logger.info("Initialized agent event streamer")

    async def stream_agent_response(
        self,
        stream_id: str,
        agent_generator
    ) -> None:
        """
        Stream agent response events to SSE.

        Args:
            stream_id: SSE stream identifier
            agent_generator: Async generator from agent
        """
        try:
            async for agent_event in agent_generator:
                # Convert agent event to frontend format
                frontend_event = self._convert_agent_event(agent_event)

                # Send via SSE
                success = await self.sse_streamer.send_event(stream_id, frontend_event)

                if not success:
                    logger.warning(f"Failed to send event to stream {stream_id}")
                    break

                # If this was a final event, break
                if frontend_event.get("type") == "done":
                    break

        except Exception as e:
            logger.error(f"Error streaming agent response for {stream_id}: {e}")
            error_event = {
                "type": "error",
                "error": {
                    "type": "streaming_error",
                    "message": str(e),
                    "recoverable": False
                }
            }
            await self.sse_streamer.send_event(stream_id, error_event)

    def _convert_agent_event(self, agent_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert agent event to frontend-compatible format.

        Args:
            agent_event: Event from Strands agent

        Returns:
            Frontend-compatible event dictionary
        """
        try:
            event_type = agent_event.get("type", "unknown")

            # Map event types to frontend format
            if event_type == "text":
                return {
                    "type": "text",
                    "content": agent_event.get("content", ""),
                    "timestamp": self._get_timestamp()
                }
            elif event_type == "tool_use":
                return {
                    "type": "tool_use",
                    "tool": agent_event.get("tool", ""),
                    "parameters": agent_event.get("parameters", {}),
                    "id": agent_event.get("id", ""),
                    "timestamp": self._get_timestamp()
                }
            elif event_type == "tool_result":
                return {
                    "type": "tool_result",
                    "tool": agent_event.get("tool", ""),
                    "result": agent_event.get("result", {}),
                    "id": agent_event.get("id", ""),
                    "timestamp": self._get_timestamp()
                }
            elif event_type == "plan_created":
                return {
                    "type": "plan_created",
                    "plan": agent_event.get("plan", {}),
                    "timestamp": self._get_timestamp()
                }
            elif event_type == "execution_started":
                return {
                    "type": "execution_started",
                    "step": agent_event.get("step", ""),
                    "timestamp": self._get_timestamp()
                }
            elif event_type == "metadata":
                return {
                    "type": "metadata",
                    "data": agent_event.get("data", {}),
                    "timestamp": self._get_timestamp()
                }
            elif event_type == "done":
                return {
                    "type": "done",
                    "final_message": agent_event.get("final_message", ""),
                    "metrics": agent_event.get("metrics", {}),
                    "timestamp": self._get_timestamp()
                }
            elif event_type == "error":
                return {
                    "type": "error",
                    "error": agent_event.get("error", {}),
                    "timestamp": self._get_timestamp()
                }
            else:
                # Pass through unknown events
                return {
                    **agent_event,
                    "timestamp": self._get_timestamp()
                }

        except Exception as e:
            logger.error(f"Error converting agent event: {e}")
            return {
                "type": "error",
                "error": {
                    "type": "conversion_error",
                    "message": str(e)
                },
                "timestamp": self._get_timestamp()
            }

    def _get_timestamp(self) -> str:
        """Get current timestamp as ISO string."""
        from datetime import datetime
        return datetime.utcnow().isoformat()


# Global streamer instances
sse_streamer = SSEStreamer()
agent_streamer = AgentEventStreamer(sse_streamer)


async def create_sse_response(stream_id: str) -> StreamingResponse:
    """
    Create a FastAPI StreamingResponse for SSE.

    Args:
        stream_id: Unique stream identifier

    Returns:
        FastAPI StreamingResponse configured for SSE
    """
    # Create stream queue
    queue = await sse_streamer.create_stream(stream_id)

    # Create streaming response
    return StreamingResponse(
        sse_streamer.stream_generator(stream_id, queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )


@asynccontextmanager
async def stream_context(stream_id: str):
    """
    Context manager for managing SSE stream lifecycle.

    Args:
        stream_id: Stream identifier
    """
    try:
        logger.info(f"Starting stream context: {stream_id}")
        yield agent_streamer
    finally:
        logger.info(f"Cleaning up stream context: {stream_id}")
        await sse_streamer.remove_stream(stream_id)