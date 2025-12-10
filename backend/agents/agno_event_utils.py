"""
Event utilities for transforming Agno events to frontend-compatible format.

This module provides event transformation for Agno agents, including:
- RunResponse and RunResponseStream events
- Tool call events
- Metrics extraction from OpenRouter responses
- HITL (Human-in-the-Loop) pause events
"""

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def sanitize_event_data(data: Any) -> Any:
    """
    Sanitize event data to ensure JSON serializability.
    Filters out complex objects like EventLoopMetrics.
    """
    if data is None or isinstance(data, (str, int, float, bool)):
        return data
    elif isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            # Skip non-serializable objects
            if hasattr(value, '__class__'):
                class_name = value.__class__.__name__
                if 'EventLoopMetrics' in class_name or 'Metrics' in class_name:
                    continue
            # Skip private keys
            if isinstance(key, str) and key.startswith('_'):
                continue
            try:
                sanitized[key] = sanitize_event_data(value)
            except (TypeError, ValueError):
                sanitized[key] = str(value)
        return sanitized
    elif isinstance(data, (list, tuple)):
        return [sanitize_event_data(item) for item in data]
    else:
        try:
            json.dumps(data)
            return data
        except (TypeError, ValueError):
            return str(data)


def transform_agno_event(
    event: Any,
    mode: Optional[str] = None,
    session_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Transform an Agno event into a frontend-compatible format.
    
    Args:
        event: The raw event from Agno (RunResponse, dict, or other)
        mode: Current agent mode ("learning", "planning", "execution")
        session_id: Session ID for tracking
        
    Returns:
        Dict with 'type' and 'data' keys, or None if event should be skipped
    """
    try:
        # Handle RunResponse objects
        if hasattr(event, 'event'):
            return _transform_run_event(event, mode, session_id)
        
        # Handle dict events
        if isinstance(event, dict):
            return _transform_dict_event(event, mode, session_id)
        
        # Handle string content (streaming text)
        if isinstance(event, str):
            return {
                "type": "text",
                "data": {"text": event},
                "mode": mode,
            }
        
        # Handle content chunks from streaming
        if hasattr(event, 'content'):
            content = event.content
            if content:
                return {
                    "type": "text",
                    "data": {"text": content},
                    "mode": mode,
                }
        
        # Unknown event type - log and skip
        logger.debug(f"Unknown event type: {type(event)}")
        return None
        
    except Exception as e:
        logger.error(f"Error transforming event: {e}", exc_info=True)
        return {"type": "error", "data": {"error": str(e)}}


def _transform_run_event(
    event: Any,
    mode: Optional[str],
    session_id: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Transform a RunResponse event."""
    event_type = getattr(event, 'event', None)
    
    # Text/content events
    if event_type == 'text' or event_type == 'content':
        content = getattr(event, 'content', '')
        if content:
            return {
                "type": "text",
                "data": {"text": content},
                "mode": mode,
            }
    
    # Tool call start
    elif event_type == 'tool_call_started' or event_type == 'tool_start':
        tool_name = getattr(event, 'tool_name', None) or getattr(event, 'name', 'unknown')
        tool_args = getattr(event, 'tool_args', {}) or getattr(event, 'arguments', {})
        return {
            "type": "tool_start",
            "data": {
                "tool_name": tool_name,
                "arguments": _sanitize_args(tool_args),
            },
            "mode": mode,
        }
    
    # Tool call completed
    elif event_type == 'tool_call_completed' or event_type == 'tool_result':
        tool_name = getattr(event, 'tool_name', None) or getattr(event, 'name', 'unknown')
        result = getattr(event, 'result', None) or getattr(event, 'content', '')
        return {
            "type": "tool_result",
            "data": {
                "tool_name": tool_name,
                "result": _truncate_result(str(result)),
            },
            "mode": mode,
        }
    
    # Reasoning/thinking
    elif event_type == 'reasoning' or event_type == 'thinking':
        reasoning = getattr(event, 'content', '') or getattr(event, 'reasoning', '')
        if reasoning:
            return {
                "type": "reasoning",
                "data": {"reasoning": reasoning},
                "mode": mode,
            }
    
    # Agent messages (for team coordination)
    elif event_type == 'agent_message':
        agent_name = getattr(event, 'agent_name', 'Agent')
        content = getattr(event, 'content', '')
        return {
            "type": "agent_message",
            "data": {
                "agent": agent_name,
                "content": content,
            },
            "mode": mode,
        }
    
    # Run completed with metrics
    elif event_type == 'run_completed' or event_type == 'completed':
        metrics = _extract_metrics(event)
        return {
            "type": "complete",
            "data": {
                "metrics": metrics,
            },
            "mode": mode,
        }
    
    # HITL pause event (for plan approval)
    elif event_type == 'paused' or event_type == 'awaiting_confirmation':
        tool_name = getattr(event, 'tool_name', None)
        tool_args = getattr(event, 'tool_args', {})
        return {
            "type": "paused",
            "data": {
                "reason": "awaiting_confirmation",
                "tool_name": tool_name,
                "tool_args": _sanitize_args(tool_args),
                "message": f"Awaiting confirmation for {tool_name}",
            },
            "mode": mode,
        }
    
    # Error event
    elif event_type == 'error':
        error = getattr(event, 'error', None) or getattr(event, 'content', 'Unknown error')
        return {
            "type": "error",
            "data": {"error": str(error)},
            "mode": mode,
        }
    
    return None


def _transform_dict_event(
    event: Dict[str, Any],
    mode: Optional[str],
    session_id: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Transform a dictionary event."""
    event_type = event.get('type') or event.get('event')
    
    # OpenRouter metrics
    if 'openrouter_metrics' in event or 'usage' in event:
        usage = event.get('openrouter_metrics') or event.get('usage', {})
        return {
            "type": "metrics",
            "data": {
                "metrics": {
                    "input_tokens": usage.get('prompt_tokens', 0),
                    "output_tokens": usage.get('completion_tokens', 0),
                    "total_tokens": usage.get('total_tokens', 0),
                    "cost": usage.get('cost', 0.0),
                    "model_id": usage.get('model_id', 'unknown'),
                },
            },
            "mode": mode,
        }
    
    # Text content
    if event_type == 'text' or 'content' in event:
        content = event.get('content') or event.get('text', '')
        if content:
            return {
                "type": "text",
                "data": {"text": content},
                "mode": mode,
            }
    
    # Tool events
    if event_type in ('tool_start', 'tool_call_started'):
        return {
            "type": "tool_start",
            "data": {
                "tool_name": event.get('tool_name') or event.get('name', 'unknown'),
                "arguments": _sanitize_args(event.get('arguments', {})),
            },
            "mode": mode,
        }
    
    if event_type in ('tool_result', 'tool_call_completed'):
        return {
            "type": "tool_result",
            "data": {
                "tool_name": event.get('tool_name') or event.get('name', 'unknown'),
                "result": _truncate_result(str(event.get('result', ''))),
            },
            "mode": mode,
        }
    
    # Pause event
    if event_type == 'paused':
        return {
            "type": "paused",
            "data": event.get('data', {}),
            "mode": mode,
        }
    
    # Error event
    if event_type == 'error':
        return {
            "type": "error",
            "data": {"error": event.get('error') or event.get('message', 'Unknown error')},
            "mode": mode,
        }
    
    # Complete event
    if event_type in ('complete', 'completed', 'run_completed'):
        return {
            "type": "complete",
            "data": event.get('data', {}),
            "mode": mode,
        }
    
    return None


def _extract_metrics(event: Any) -> Dict[str, Any]:
    """Extract metrics from a RunResponse event."""
    metrics = {}
    
    # Try to get metrics from various sources
    if hasattr(event, 'metrics'):
        m = event.metrics
        if m:
            metrics = {
                "input_tokens": getattr(m, 'input_tokens', 0) or getattr(m, 'prompt_tokens', 0),
                "output_tokens": getattr(m, 'output_tokens', 0) or getattr(m, 'completion_tokens', 0),
                "total_tokens": getattr(m, 'total_tokens', 0),
                "time_to_first_token": getattr(m, 'time_to_first_token', None),
                "response_time": getattr(m, 'response_timer', None),
            }
    
    # Try response usage
    if hasattr(event, 'response') and hasattr(event.response, 'usage'):
        usage = event.response.usage
        if usage:
            metrics["input_tokens"] = getattr(usage, 'prompt_tokens', 0)
            metrics["output_tokens"] = getattr(usage, 'completion_tokens', 0)
            metrics["total_tokens"] = getattr(usage, 'total_tokens', 0)
    
    return metrics


def _sanitize_args(args: Any) -> Dict[str, Any]:
    """Sanitize tool arguments for JSON serialization."""
    if not args:
        return {}
    
    if isinstance(args, dict):
        sanitized = {}
        for key, value in args.items():
            if isinstance(value, (str, int, float, bool, type(None))):
                sanitized[key] = value
            elif isinstance(value, (list, tuple)):
                sanitized[key] = [str(v)[:500] for v in value[:10]]
            else:
                sanitized[key] = str(value)[:500]
        return sanitized
    
    return {"args": str(args)[:1000]}


def _truncate_result(result: str, max_length: int = 2000) -> str:
    """Truncate tool result for transmission."""
    if len(result) <= max_length:
        return result
    return result[:max_length] + f"... (truncated {len(result) - max_length} chars)"


# =============================================================================
# Backward Compatibility
# =============================================================================

def transform_strands_event(event: Any, agent_type: Optional[str] = None, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Backward compatibility wrapper for the old transform_strands_event function.
    
    This function now delegates to transform_agno_event for Agno events,
    while maintaining compatibility with the old Strands event format.
    """
    return transform_agno_event(event, mode=agent_type, session_id=session_id)
