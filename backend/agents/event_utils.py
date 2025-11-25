"""
Event utilities for transforming Strands events to frontend-compatible format.
"""

import logging
from typing import Any, Dict, Optional, List, Union
from agents.metrics_tracker import ModelPricing

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

def transform_strands_event(event: Any, agent_type: Optional[str] = None, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Transform a Strands event into a frontend-compatible format.

    Args:
        event: The raw event from Strands (dict or object)
        agent_type: Optional agent type ("planning", "execution") for metrics tracking
        session_id: Optional session ID for workflow metrics tracking

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
        # This allows passing through events we constructed ourselves
        if "data" in event:
            # Pass through workflow metrics events and other custom events
            if event["type"] == "workflow_metrics_complete":
                return event
            # Also pass through other custom events like plan_created, execution_started, etc.
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
        # Message start/stop events
        elif "messageStop" in inner_event:
             # Check for usage in the inner event
             # Note: The structure might vary, but let's try to find usage
             # Usually usage is a top-level field in the message object, but in streaming 
             # it comes in the message_stop event.
             pass
        elif "messageStart" in inner_event:
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
        
    elif "messageStop" in event:
        # Message stop event - often contains usage metrics from OpenRouter adapter
        stop_event = event["messageStop"]

        # Extract usage if present (now provided by OpenRouterModel)
        usage = stop_event.get("usage", {})
        if usage:
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

            # Get actual cost if available from OpenRouter
            actual_cost = usage.get("actual_cost")

            # Get model_id from event context if available
            # Check inside stop_event first (in case it was injected there)
            model_id = stop_event.get("model_id")
            if not model_id:
                model_id = event.get("model_id", "anthropic/claude-3.5-sonnet")

            # Use actual cost if available, otherwise fallback to calculation
            if actual_cost is not None:
                estimated_cost = float(actual_cost)
            else:
                # Calculate estimated cost as fallback using ModelPricing
                estimated_cost = ModelPricing.calculate_cost(
                    model_id,
                    input_tokens,
                    output_tokens
                )

            # Prepare metrics response with both actual and estimated cost
            metrics_data = {
                "total_tokens": total_tokens,
                "estimated_cost": estimated_cost,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "model_id": model_id,
                "agent_type": agent_type,
                "session_id": session_id,
                "cost": estimated_cost  # Add 'cost' field for consistency with database schema
            }

            return {
                "type": "metrics",
                "data": {
                    "metrics": metrics_data
                }
            }

    elif "messageStart" in event:
        return None

    elif "type" in event and event["type"] == "message_stop":
         # Alternative message stop format (fallback handler)
         if "amazon-bedrock-invocationMetrics" in event:
             # Bedrock format
             pass

         # Check for usage
         usage = event.get("usage", {})
         if usage:
             input_tokens = usage.get("input_tokens", 0)
             output_tokens = usage.get("output_tokens", 0)
             total_tokens = input_tokens + output_tokens

             # Get actual cost if available
             actual_cost = usage.get("actual_cost")

             # Get model_id from event context
             model_id = event.get("model_id", "anthropic/claude-3.5-sonnet")
             if "model_id" not in event:
                 logger.warning("No model_id in message_stop event, using default for cost calculation")

             # Use actual cost if available, otherwise fallback to calculation
             if actual_cost is not None:
                 estimated_cost = float(actual_cost)
             else:
                 # Use ModelPricing class for accurate cost calculation
                 estimated_cost = ModelPricing.calculate_cost(
                     model_id,
                     input_tokens,
                     output_tokens
                 )

             metrics_data = {
                 "total_tokens": total_tokens,
                 "estimated_cost": estimated_cost,
                 "input_tokens": input_tokens,
                 "output_tokens": output_tokens,
                 "model_id": model_id,
                 "agent_type": agent_type,
                 "session_id": session_id,
                 "cost": estimated_cost  # Add 'cost' field for consistency
             }

             return {
                 "type": "metrics",
                 "data": {
                     "metrics": metrics_data
                 }
             }

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
    elif "toolResult" in event:
        # Tool execution result (CamelCase from Strands/Claude)
        tool_result = event["toolResult"]
        event_type = "tool_result"
        event_data = {
            "tool_name": tool_result.get("name"),
            "result": tool_result.get("content", [])
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


def accumulate_workflow_metrics(
    session_id: str,
    metrics_event: Dict[str, Any],
    multi_agent_manager: Any,
    agent_type: str
) -> None:
    """
    Accumulate metrics for a workflow session.

    Args:
        session_id: The session ID
        metrics_event: The metrics event data
        multi_agent_manager: The multi-agent manager instance
        agent_type: "planning" or "execution"
    """
    try:
        if session_id not in multi_agent_manager._workflow_metrics:
            multi_agent_manager._workflow_metrics[session_id] = WorkflowMetricsAccumulator(session_id)

        accumulator = multi_agent_manager._workflow_metrics[session_id]
        metrics = metrics_event.get("data", {}).get("metrics", {})

        if agent_type == "planning":
            accumulator.add_planning_metrics(metrics)
        elif agent_type == "execution":
            accumulator.add_execution_metrics(metrics)

        logger.debug(f"Accumulated {agent_type} metrics for {session_id}: "
                    f"tokens={metrics.get('total_tokens', 0)}, "
                    f"cost=${metrics.get('cost', 0):.4f}")

    except Exception as e:
        logger.error(f"Failed to accumulate workflow metrics: {e}")


def get_workflow_metrics_summary(session_id: str, multi_agent_manager: Any) -> Optional[Dict[str, Any]]:
    """
    Get workflow metrics summary for a session.

    Args:
        session_id: The session ID
        multi_agent_manager: The multi-agent manager instance

    Returns:
        Workflow metrics summary or None if not available
    """
    try:
        if session_id not in multi_agent_manager._workflow_metrics:
            return None

        return multi_agent_manager._workflow_metrics[session_id].get_aggregated_metrics()
    except Exception as e:
        logger.error(f"Failed to get workflow metrics summary: {e}")
        return None
