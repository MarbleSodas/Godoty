"""
Event utilities for transforming Strands events to frontend-compatible format.
"""

import logging
from typing import Any, Dict, Optional, List, Union

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
                    # Skip metrics objects that aren't primitives
                    continue
            # Skip private keys
            if isinstance(key, str) and key.startswith('_'):
                continue
            try:
                sanitized[key] = sanitize_event_data(value)
            except (TypeError, ValueError):
                # Convert to string if can't serialize
                sanitized[key] = str(value)
        return sanitized
    elif isinstance(data, (list, tuple)):
        return [sanitize_event_data(item) for item in data]
    else:
        # Try to serialize, otherwise convert to string
        try:
            import json
            json.dumps(data)
            return data
        except (TypeError, ValueError):
            return str(data)

def transform_strands_event(event: Any) -> Optional[Dict[str, Any]]:
    """
    Transform a Strands event into a frontend-compatible format.
    
    Args:
        event: The raw event from Strands (dict or object)
        
    Returns:
        Dict with 'type' and 'data' keys, or None if event should be skipped.
    """
    # If it's an object, try to convert to dict
    if not isinstance(event, dict):
        try:
            event = event.__dict__
        except:
            return {"type": "unknown", "data": str(event)}

    event_type = None
    event_data = {}

    # Graph events - Check this FIRST as they have specific types
    # Graph events - Check this FIRST as they have specific types
    if "type" in event:
        event_type = event["type"]
        
        # Handle graph-specific event types
        if event_type == "multi_agent_node_stream" or event_type == "multiagent_node_stream":
            # Unwrap the nested agent event
            # The actual agent event is nested within the data or event key
            nested_data = event.get("data", {})
            
            # Check for 'event' key (Strands standard)
            if not nested_data and "event" in event:
                nested_data = event.get("event", {})

            if isinstance(nested_data, dict):
                nested_event = nested_data.get("event")
                if nested_event:
                    # Recursively transform the nested event
                    return transform_strands_event(nested_event)
            
            # If structure is different or no nested event, try to use data directly
            # But only if it looks like an event we can handle
            if isinstance(nested_data, dict):
                 return transform_strands_event(nested_data)
            
            return None

        elif event_type == "multi_agent_node_start" or event_type == "multiagent_node_start":
            # Node starting - could notify frontend if needed
            # For now, return None to skip or map to a generic start if useful
            return None

        elif event_type == "multi_agent_node_stop" or event_type == "multiagent_node_stop":
            # Node completion
            return None

        elif event_type == "result":
            # Final graph result
            # We might want to extract metrics or stop reason
            return None
            
        # Check if this is already a transformed event (has 'type' and 'data')
        # This allows passing through events we constructed ourselves (like plan_created)
        if "data" in event:
            return event

        # If it has a type but no data, and we haven't handled it above,
        # we should check if it matches other patterns below or log it.
        # Don't just return it, as it might be a raw Strands event we missed.
        # Fall through to check other keys.
        pass

    # Handle different event types from Strands
    # Strands uses Claude's event format, so check for 'event' key first
    if "event" in event:
        # Claude-style streaming events
        inner_event = event["event"]
        
        # Check for content block delta (actual text chunks)
        if "contentBlockDelta" in inner_event:
            delta = inner_event["contentBlockDelta"].get("delta", {})
            if "text" in delta:
                event_type = "data"
                event_data = {"text": delta["text"]}
            elif "reasoning" in delta:
                 # Handle reasoning events if the model supports it (e.g. Claude 3.7)
                 event_type = "reasoning"
                 event_data = {"text": delta["reasoning"]}
        # Tool use events
        elif "contentBlockStart" in inner_event:
            block = inner_event["contentBlockStart"].get("contentBlock", {})
            if "toolUse" in block:
                tool_use = block["toolUse"]
                event_type = "tool_use"
                event_data = {
                    "tool_name": tool_use.get("name"),
                    "tool_input": tool_use.get("input", {})
                }
        # Message start/stop events - we can ignore these
        elif "messageStart" in inner_event or "messageStop" in inner_event:
            return None
        else:
            # logger.debug(f"Unhandled inner event: {inner_event}")
            return None

    # Check for top-level Strands/Claude events (OpenRouterModel yields these directly)
    elif "contentBlockDelta" in event:
        delta = event["contentBlockDelta"].get("delta", {})
        if "text" in delta:
            event_type = "data"
            event_data = {"text": delta["text"]}
        elif "reasoning" in delta:
             event_type = "reasoning"
             event_data = {"text": delta["reasoning"]}
        elif "toolUse" in delta:
            # Some implementations might put partial tool input here
            pass

    elif "contentBlockStart" in event:
        # Start of a block (text or tool)
        start = event["contentBlockStart"].get("start", {})
        if "toolUse" in start:
            tool_use = start["toolUse"]
            event_type = "tool_use"
            event_data = {
                "tool_name": tool_use.get("name"),
                "tool_input": tool_use.get("input", {}) # Might be empty if streaming args
            }
            
    elif "contentBlockStop" in event:
        return None
        
    elif "messageStart" in event or "messageStop" in event:
        return None

    elif "data" in event:
        # Skip Strands metadata events (they have agent, event_loop_cycle_id, etc.)
        # These are duplicates of the contentBlockDelta events
        if "agent" in event or "event_loop_cycle_id" in event:
            return None
        
        # Handle graph events where 'data' might contain the actual event
        data_content = event["data"]
        if isinstance(data_content, dict) and "event" in data_content:
             # Recursively transform nested graph event
             return transform_strands_event(data_content)
             
        # Legacy text data streaming (might not be used)
        event_type = "data"
        event_data = {"text": event["data"]}
        
    elif "current_tool_use" in event:
        # Tool being executed
        tool_info = event["current_tool_use"]
        event_type = "tool_use"
        event_data = {
            "tool_name": tool_info.get("name"),
            "tool_input": tool_info.get("input", {})
        }
    elif "tool_result" in event:
        # Tool execution result
        tool_result = event["tool_result"]
        event_type = "tool_result"
        event_data = {
            "tool_name": tool_result.get("name"),
            "result": tool_result.get("content", [])
        }
    elif "result" in event:
        # Final result - extract and yield end event
        result = event["result"]
        event_type = "end"
        event_data = {
            "stop_reason": getattr(result, 'stop_reason', 'end_turn')
        }

        # Include metrics if available (sanitized)
        if hasattr(result, 'metrics'):
            # Only include basic metrics, not complex objects
            try:
                metrics = result.metrics
                if isinstance(metrics, dict):
                    event_data["metrics"] = sanitize_event_data(metrics)
            except Exception as e:
                logger.debug(f"Could not include metrics: {e}")
                
    elif "complete" in event and event["complete"]:
        # Stream completion marker
        return None
        
    # Ignore these common events
    elif "message" in event:
        # Check for tool calls in the message (often happens at the end of generation)
        msg = event["message"]
        tool_calls = []
        
        # Handle object vs dict
        if hasattr(msg, 'tool_calls'):
            tool_calls = msg.tool_calls
        elif isinstance(msg, dict):
            tool_calls = msg.get('tool_calls', [])
            
        # Yield tool use events if found
        if tool_calls:
            # We can only return one event, but there might be multiple tool calls.
            # For now, we'll just return the first one or handle this differently.
            # Ideally, this function yields, but we are returning.
            # Let's return a list of events if possible? No, type signature says Dict.
            # We will return the first one. The caller might need to handle this better if we want all.
            # But typically message event comes after streaming tool calls, so it might be redundant.
            # Let's skip for now unless we really need it.
            pass
        return None

    elif "init_event_loop" in event or "start" in event or "start_event_loop" in event:
        return None
        
    else:
        # Other events - LOG THEM so we can see what we're missing!
        # logger.warning(f"Unhandled event type with keys: {list(event.keys())}")
        return None

    if event_type:
        return {
            "type": event_type,
            "data": sanitize_event_data(event_data)
        }
    
    return None
