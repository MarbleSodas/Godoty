"""
Event utilities for transforming Strands events to frontend-compatible format.
"""

import logging
import time
from typing import Any, Dict, Optional, List, Union

logger = logging.getLogger(__name__)

# Global streaming metrics tracker instance
_streaming_tracker = None

def get_streaming_metrics_tracker():
    """Get or create the global streaming metrics tracker."""
    global _streaming_tracker
    if _streaming_tracker is None:
        try:
            from agents.streaming_metrics_tracker import StreamingMetricsTracker
            _streaming_tracker = StreamingMetricsTracker()
        except ImportError:
            logger.warning("StreamingMetricsTracker not available, metrics tracking disabled")
            _streaming_tracker = None  # Set to None to skip tracking
    return _streaming_tracker

def get_metrics_buffer():
    """Get or create the global metrics buffer."""
    try:
        from agents.metrics_buffer import MetricsBuffer
        return MetricsBuffer()
    except ImportError:
        logger.warning("MetricsBuffer not available, using fallback")
        return None

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

    This function now includes enhanced metrics tracking for partial operations
    using the StreamingMetricsTracker and MetricsBuffer systems.

    Args:
        event: The raw event from Strands (dict or object)
        agent_type: Optional agent type ("planning", "execution") for metrics tracking
        session_id: Optional session ID for workflow metrics tracking

    Returns:
        Dict with 'type' and 'data' keys, or None if event should be skipped.
    """
    # Initialize tracking if session_id is provided
    if session_id:
        streaming_tracker = get_streaming_metrics_tracker()
        metrics_buffer = get_metrics_buffer()

        # Start tracking if this is a new session (only if tracker is available)
        if streaming_tracker and session_id not in streaming_tracker.get_all_active_sessions():
            streaming_tracker.start_session_tracking(session_id)
    # If it's an object, try to convert to dict
    if not isinstance(event, dict):
        try:
            event = event.__dict__
        except:
            return {"type": "unknown", "data": str(event)}

    event_type = None
    event_data = {}

    # Handle OpenRouter metrics events FIRST (from GodotyOpenRouterModel)
    if "openrouter_metrics" in event:
        usage = event["openrouter_metrics"]
        logger.info(f"[METRICS] OpenRouter metrics event: {usage}")
        return {
            "type": "metrics",
            "data": {
                "metrics": {
                    "total_tokens": usage.get("total_tokens", 0),
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                    "estimated_cost": usage.get("cost", 0.0),
                    "cost": usage.get("cost", 0.0),
                    "model_id": usage.get("model_id", "unknown"),
                    "agent_type": agent_type,
                    "session_id": session_id
                }
            }
        }
    
    # Also check for openrouter_usage injected into other events
    if "openrouter_usage" in event:
        usage = event["openrouter_usage"]
        logger.info(f"[METRICS] OpenRouter usage in event: {usage}")
        return {
            "type": "metrics",
            "data": {
                "metrics": {
                    "total_tokens": usage.get("total_tokens", 0),
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                    "estimated_cost": usage.get("cost", 0.0),
                    "cost": usage.get("cost", 0.0),
                    "model_id": usage.get("model_id", "unknown"),
                    "agent_type": agent_type,
                    "session_id": session_id
                }
            }
        }

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
                    "tool_input": tool_use.get("input", {}),
                    "tool_use_id": tool_use.get("toolUseId", f"tool-{int(time.time()*1000)}")
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
        # Track partial metrics for streaming operations
        if session_id:
            streaming_tracker.accumulate_partial_usage(event, session_id)

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
                "tool_input": tool_use.get("input", {}), # Might be empty if streaming args
                "tool_use_id": tool_use.get("toolUseId", f"tool-{int(time.time()*1000)}")
            }
            
    elif "contentBlockStop" in event:
        # Content block stop might signal tool completion
        block_stop = event.get("contentBlockStop", {})
        content_block = block_stop.get("contentBlock", {})
        
        # Check if this is a tool result block
        if "toolResult" in content_block:
            tool_result = content_block["toolResult"]
            event_type = "tool_result"
            event_data = {
                "tool_name": tool_result.get("name"),
                "result": tool_result.get("content", []),
                "tool_use_id": tool_result.get("toolUseId"),
                "status": "success"  # Explicit success status
            }
        else:
            return None
        
    elif "messageStop" in event:
        # Message stop event - often contains usage metrics from OpenRouter adapter
        stop_event = event["messageStop"]
        
        # OpenRouter with stream_options.include_usage=true puts usage at top level or in stop_event
        # Try multiple locations for usage data
        usage = stop_event.get("usage") or event.get("usage") or {}
        
        # Log what we found for debugging
        logger.debug(f"[METRICS] messageStop event keys: {list(event.keys())}")
        logger.debug(f"[METRICS] stop_event keys: {list(stop_event.keys()) if isinstance(stop_event, dict) else 'not a dict'}")
        logger.debug(f"[METRICS] usage found: {usage if usage else 'None'}")
        
        if usage:
            # Support both OpenAI SDK format (prompt_tokens) and OpenRouter format (input_tokens)
            input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens", 0)
            output_tokens = usage.get("completion_tokens") or usage.get("output_tokens", 0)
            total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

            # Get cost from OpenRouter - can be in 'cost' or 'actual_cost'
            actual_cost = usage.get("cost") or usage.get("actual_cost")
            
            logger.info(f"[METRICS] Extracted from messageStop: {input_tokens} in, {output_tokens} out, ${actual_cost or 0:.6f}")

            # Get model_id from event context if available
            # Check inside stop_event first (in case it was injected there)
            model_id = stop_event.get("model_id")
            if not model_id:
                model_id = event.get("model_id") or event.get("model", "unknown")

            # Use actual cost if available, otherwise fallback to zero
            if actual_cost is not None:
                estimated_cost = float(actual_cost)
            else:
                # No cost available - this is expected for some free models
                estimated_cost = 0.0
                logger.debug(f"[METRICS] No cost in usage data, defaulting to $0.00")

            # Finalize metrics in streaming tracker if session_id is provided
            if session_id:
                streaming_tracker = get_streaming_metrics_tracker()
                metrics_buffer = get_metrics_buffer()
                
                if streaming_tracker:
                    final_metrics = streaming_tracker.finalize_metrics(session_id, event)
                    # Buffer the finalized metrics for recovery
                    if final_metrics and metrics_buffer:
                        message_id = f"msg-{int(time.time()*1000)}"
                        metrics_buffer.add_metric(session_id, message_id, agent_type or "unknown", final_metrics, is_finalized=True)

                    # End tracking for this session
                    streaming_tracker.end_session_tracking(session_id)

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
            
            logger.info(f"[METRICS] Emitting metrics event: {metrics_data}")

            return {
                "type": "metrics",
                "data": {
                    "metrics": metrics_data
                }
            }
        else:
            # No usage data found - log for debugging
            logger.warning(f"[METRICS] messageStop event without usage data. Event: {event}")

    elif "messageStart" in event:
        return None

    elif "data" in event:
        # Skip Strands metadata events
        if "agent" in event or "event_loop_cycle_id" in event:
            return None
        
        # Handle graph events where 'data' might contain the actual event
        data_content = event["data"]
        if isinstance(data_content, dict) and "event" in data_content:
             return transform_strands_event(data_content)
             
        event_type = "data"
        event_data = {"text": event["data"]}
        
    elif "current_tool_use" in event:
        # Tool being executed
        tool_info = event["current_tool_use"]
        event_type = "tool_use"
        event_data = {
            "tool_name": tool_info.get("name"),
            "tool_input": tool_info.get("input", {}),
            "tool_use_id": tool_info.get("toolUseId", f"tool-{int(time.time()*1000)}")
        }
    elif "message" in event:
        # Handle ToolResultMessageEvent from Strands - contains message with toolResult blocks
        # This is the primary way tool results are streamed in real-time
        message = event["message"]
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content", [])
            # Emit a tool_result event for each toolResult in the message
            tool_results_to_emit = []
            for block in content:
                if isinstance(block, dict) and "toolResult" in block:
                    tool_result = block["toolResult"]
                    tool_results_to_emit.append({
                        "type": "tool_result",
                        "data": sanitize_event_data({
                            "tool_name": tool_result.get("name"),
                            "result": tool_result.get("content", []),
                            "tool_use_id": tool_result.get("toolUseId"),
                            "status": tool_result.get("status", "success")
                        })
                    })
            # If we have tool results, return the first one
            # Note: Multiple tool results are rare; if needed, caller should handle message events
            if tool_results_to_emit:
                return tool_results_to_emit[0]
    elif "toolResult" in event:
        # Tool execution result (CamelCase from Strands/Claude)
        tool_result = event["toolResult"]
        event_type = "tool_result"
        event_data = {
            "tool_name": tool_result.get("name"),
            "result": tool_result.get("content", []),
            "tool_use_id": tool_result.get("toolUseId"),
            "status": "success"  # Explicit success status
        }
    elif "tool_result" in event:
        # Tool execution result
        tool_result = event["tool_result"]
        event_type = "tool_result"
        event_data = {
            "tool_name": tool_result.get("name"),
            "result": tool_result.get("content", []),
            "tool_use_id": tool_result.get("toolUseId"),
            "status": "success"  # Explicit success status
        }
    elif "toolError" in event or "tool_cancelled" in event:
        # Handle tool errors/cancellations
        tool_error = event.get("toolError", event.get("tool_cancelled"))
        event_type = "tool_error"
        event_data = {
            "tool_name": tool_error.get("name"),
            "tool_use_id": tool_error.get("toolUseId"),
            "error": tool_error.get("error", "Tool execution failed"),
            "error_type": tool_error.get("type", "execution_error")
        }
    elif "result" in event:
        # Final result from Strands - extract metrics from result.metrics.accumulated_usage
        result = event["result"]
        
        # Try to extract metrics from Strands AgentResult
        metrics_extracted = False
        if hasattr(result, 'metrics') and result.metrics:
            try:
                accumulated_usage = getattr(result.metrics, 'accumulated_usage', None)
                
                if accumulated_usage:
                    # Strands uses inputTokens/outputTokens format
                    input_tokens = accumulated_usage.get("inputTokens", 0) or accumulated_usage.get("input_tokens", 0)
                    output_tokens = accumulated_usage.get("outputTokens", 0) or accumulated_usage.get("output_tokens", 0)
                    total_tokens = accumulated_usage.get("totalTokens", 0) or (input_tokens + output_tokens)
                    cost = accumulated_usage.get("cost", 0.0)
                    
                    logger.info(f"[METRICS] Extracted from result.metrics: {input_tokens} in, {output_tokens} out, total={total_tokens}, cost=${cost}")
                    
                    metrics_data = {
                        "total_tokens": total_tokens,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "estimated_cost": cost,
                        "cost": cost,
                        "model_id": "unknown",  # Model ID not available in result
                        "agent_type": agent_type,
                        "session_id": session_id
                    }
                    
                    # Return metrics event FIRST, the caller will need to handle the end event separately
                    # Actually, we can only return one event. Let's make the result include both.
                    # No wait - we need to return metrics as a separate event before end.
                    # The cleanest approach: return a metrics dict that can be processed
                    metrics_extracted = True
                    return {
                        "type": "metrics",
                        "data": {
                            "metrics": metrics_data
                        }
                    }
            except Exception as e:
                logger.warning(f"[METRICS] Failed to extract from result.metrics: {e}")
        
        # If we didn't extract metrics, return the end event
        if not metrics_extracted:
            event_type = "end"
            event_data = {
                "stop_reason": getattr(result, 'stop_reason', 'end_turn')
            }
                
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
    
    # Handle standalone usage event (OpenRouter may send this separately with include_usage=true)
    elif "usage" in event and "messageStop" not in event:
        usage = event["usage"]
        
        # Support both OpenAI SDK format and OpenRouter format
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens", 0)
        output_tokens = usage.get("completion_tokens") or usage.get("output_tokens", 0)
        total_tokens = usage.get("total_tokens", input_tokens + output_tokens)
        actual_cost = usage.get("cost") or usage.get("actual_cost")
        model_id = event.get("model_id") or event.get("model", "unknown")
        
        logger.info(f"[METRICS] Standalone usage event: {input_tokens} in, {output_tokens} out, ${actual_cost or 0:.6f}")
        
        return {
            "type": "metrics",
            "data": {
                "metrics": {
                    "total_tokens": total_tokens,
                    "estimated_cost": float(actual_cost) if actual_cost else 0.0,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "model_id": model_id,
                    "agent_type": agent_type,
                    "session_id": session_id,
                    "cost": float(actual_cost) if actual_cost else 0.0
                }
            }
        }
        
    else:
        # Other events - LOG THEM so we can see what we're missing!
        logger.debug(f"[EVENTS] Unhandled event type with keys: {list(event.keys())}")
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


def handle_session_cancellation(session_id: str, agent_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Handle session cancellation by capturing partial metrics.

    This function should be called when a streaming session is cancelled
    to ensure no metrics are lost.

    Args:
        session_id: The session ID being cancelled
        agent_type: Optional agent type for context

    Returns:
        Cancellation event with partial metrics, or None if no metrics to capture
    """
    try:
        streaming_tracker = get_streaming_metrics_tracker()
        metrics_buffer = get_metrics_buffer()

        # Skip metrics tracking if modules not available
        if not streaming_tracker or not metrics_buffer:
            logger.debug("Metrics tracking unavailable, skipping cancellation metrics")
            return None

        # Capture partial metrics from the streaming tracker
        partial_metrics = streaming_tracker.handle_cancellation(session_id)

        if partial_metrics:
            # Buffer the partial metrics for recovery
            message_id = f"cancelled-msg-{int(time.time()*1000)}"
            metrics_buffer.add_metric(
                session_id=session_id,
                message_id=message_id,
                agent_type=agent_type or "unknown",
                metrics=partial_metrics,
                is_finalized=False
            )

            logger.info(f"Captured partial metrics on cancellation for session {session_id}: {partial_metrics.total_tokens} tokens, ${partial_metrics.cost:.6f}")

            return {
                "type": "cancellation_metrics",
                "data": {
                    "session_id": session_id,
                    "agent_type": agent_type,
                    "partial_metrics": {
                        "total_tokens": partial_metrics.total_tokens,
                        "input_tokens": partial_metrics.input_tokens,
                        "output_tokens": partial_metrics.output_tokens,
                        "cost": partial_metrics.cost,
                        "model_name": partial_metrics.model_name,
                        "is_complete": partial_metrics.is_complete
                    }
                }
            }

        return None

    except Exception as e:
        logger.error(f"Failed to handle session cancellation for {session_id}: {e}")
        return None


def recover_session_metrics(session_id: str) -> Dict[str, Any]:
    """
    Attempt to recover metrics for a cancelled or interrupted session.

    Args:
        session_id: The session ID to recover metrics for

    Returns:
        Recovery statistics and recovered metrics
    """
    try:
        metrics_buffer = get_metrics_buffer()

        # Skip if metrics buffer not available
        if not metrics_buffer:
            logger.debug("Metrics buffer unavailable, skipping recovery")
            return {"recovered": 0, "failed": 0, "metrics": []}

        # Attempt recovery
        recovery_stats = metrics_buffer.attempt_recovery(session_id)

        # Get recovered metrics
        recovered_metrics = metrics_buffer.get_metrics(session_id, include_recovered=True)

        # Calculate totals from recovered metrics
        total_tokens = sum(m.metrics.total_tokens for m in recovered_metrics if m.recovery_attempted)
        total_cost = sum(m.metrics.cost for m in recovered_metrics if m.recovery_attempted)

        result = {
            "session_id": session_id,
            "recovery_stats": recovery_stats,
            "summary": {
                "recovered_messages": len([m for m in recovered_metrics if m.recovery_attempted]),
                "total_tokens": total_tokens,
                "total_cost": total_cost,
                "recovery_successful": recovery_stats["successful"] > 0
            },
            "recovered_metrics": [
                {
                    "message_id": m.message_id,
                    "agent_type": m.agent_type,
                    "tokens": m.metrics.total_tokens,
                    "cost": m.metrics.cost,
                    "is_complete": m.metrics.is_complete,
                    "timestamp": m.timestamp
                }
                for m in recovered_metrics if m.recovery_attempted
            ]
        }

        logger.info(f"Metrics recovery completed for session {session_id}: {result['summary']}")
        return result

    except Exception as e:
        logger.error(f"Failed to recover metrics for session {session_id}: {e}")
        return {
            "session_id": session_id,
            "recovery_stats": {"total_attempted": 0, "successful": 0, "failed": 0},
            "summary": {"recovered_messages": 0, "total_tokens": 0, "total_cost": 0.0, "recovery_successful": False},
            "error": str(e)
        }


def create_checkpoint_for_session(session_id: str) -> bool:
    """
    Create a checkpoint for the current state of a session's metrics.

    Args:
        session_id: The session ID

    Returns:
        True if checkpoint was created successfully, False otherwise
    """
    try:
        streaming_tracker = get_streaming_metrics_tracker()

        # Skip if tracker not available
        if not streaming_tracker:
            logger.debug("Streaming tracker unavailable, skipping checkpoint creation")
            return False

        if session_id not in streaming_tracker.get_all_active_sessions():
            logger.warning(f"Session {session_id} is not actively tracking, cannot create checkpoint")
            return False

        checkpoint = streaming_tracker.create_checkpoint(session_id)
        logger.debug(f"Created checkpoint for session {session_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to create checkpoint for session {session_id}: {e}")
        return False


def cleanup_session_metrics(session_id: str, keep_recovered: bool = False) -> bool:
    """
    Clean up metrics data for a session.

    Args:
        session_id: The session ID
        keep_recovered: Whether to keep metrics that have been recovered

    Returns:
        True if cleanup was successful, False otherwise
    """
    try:
        streaming_tracker = get_streaming_metrics_tracker()
        metrics_buffer = get_metrics_buffer()

        # Skip if modules not available
        if not streaming_tracker and not metrics_buffer:
            logger.debug("Metrics tracking unavailable, skipping cleanup")
            return True

        # Clean up streaming tracker (if available)
        if streaming_tracker:
            streaming_tracker.end_session_tracking(session_id)

        # Clean up metrics buffer (if available)
        if metrics_buffer:
            cleared_count = metrics_buffer.clear_session(session_id, keep_recovered=keep_recovered)
            logger.info(f"Cleaned up {cleared_count} metrics for session {session_id} (keep_recovered={keep_recovered})")

        return True

    except Exception as e:
        logger.error(f"Failed to cleanup metrics for session {session_id}: {e}")
        return False


def get_metrics_statistics() -> Dict[str, Any]:
    """
    Get comprehensive statistics about the metrics tracking systems.

    Returns:
        Statistics from both streaming tracker and metrics buffer
    """
    try:
        streaming_tracker = get_streaming_metrics_tracker()
        metrics_buffer = get_metrics_buffer()

        # Return empty stats if modules not available
        if not streaming_tracker or not metrics_buffer:
            logger.debug("Metrics tracking unavailable, returning empty statistics")
            return {
                "active_sessions": [],
                "buffered_metrics": 0,
                "recovered_metrics": 0,
                "pending_recovery": 0
            }

        # Get active sessions
        active_sessions = streaming_tracker.get_all_active_sessions()

        # Get buffer statistics
        buffer_stats = metrics_buffer.get_statistics()
        buffer_summary = metrics_buffer.get_buffer_summary()

        return {
            "streaming_tracker": {
                "active_sessions": len(active_sessions),
                "session_ids": active_sessions,
                "total_sessions_tracked": len(active_sessions)
            },
            "metrics_buffer": {
                "total_buffered": buffer_stats.total_buffered,
                "pending_recoveries": buffer_stats.pending_recoveries,
                "successful_recoveries": buffer_stats.successful_recoveries,
                "failed_recoveries": buffer_stats.failed_recoveries,
                "buffer_size_mb": buffer_stats.buffer_size_bytes / (1024 * 1024),
                "sessions_count": buffer_summary["total_sessions"]
            },
            "health": {
                "healthy": len(active_sessions) < 50 and buffer_stats.buffer_size_bytes < 50 * 1024 * 1024,  # Less than 50MB
                "warnings": []
            }
        }

    except Exception as e:
        logger.error(f"Failed to get metrics statistics: {e}")
        return {
            "error": str(e),
            "healthy": False
        }
