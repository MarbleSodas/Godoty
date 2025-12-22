"""Patches for Agno library bugs.

This module applies monkey-patches to fix known issues in the Agno library.
Apply patches by calling apply_patches() early in application startup.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def apply_patches() -> None:
    """Apply all Agno patches."""
    _patch_litellm_tool_message_name()
    logger.info("[Patches] Applied Agno LiteLLM tool message name fix")


def _patch_litellm_tool_message_name() -> None:
    """Fix: Tool messages must have 'name' field for OpenRouter/Google AI Studio.
    
    Bug: Agno sets tool_name (metadata) but not name (sent to API).
    This causes "Tool message must have either name or tool_call_id" errors.
    
    Fix: Use tool_name as fallback when name is not set.
    """
    try:
        from agno.models.litellm.chat import LiteLLM
        from agno.utils.openai import images_to_message, audio_to_message, _format_file_for_message
        from agno.models.message import Message
        from agno.utils.log import log_warning
        
        original_format_messages = LiteLLM._format_messages
        
        def patched_format_messages(self, messages: List[Message], compress_tool_results: bool = False) -> List[Dict[str, Any]]:
            """Format messages with tool_name fallback fix."""
            formatted_messages = []
            for m in messages:
                # Use compressed content for tool messages if compression is active
                if m.role == "tool":
                    content = m.get_content(use_compressed_content=compress_tool_results)
                else:
                    content = m.content if m.content is not None else ""

                msg: Dict[str, Any] = {"role": m.role, "content": content}

                # Handle media (images/audio)
                if (m.images is not None and len(m.images) > 0) or (m.audio is not None and len(m.audio) > 0):
                    if isinstance(m.content, str):
                        content_list: List[Any] = [{"type": "text", "text": m.content}]
                        if m.images is not None:
                            content_list.extend(images_to_message(images=m.images))
                        if m.audio is not None:
                            content_list.extend(audio_to_message(audio=m.audio))
                        msg["content"] = content_list

                # Handle videos
                if m.videos is not None and len(m.videos) > 0:
                    log_warning("Video input is currently unsupported by LLM providers.")

                # Handle files
                if m.files is not None:
                    if isinstance(msg["content"], str):
                        content_list = [{"type": "text", "text": msg["content"]}]
                    else:
                        content_list = msg["content"] if isinstance(msg["content"], list) else []
                    for file in m.files:
                        file_part = _format_file_for_message(file)
                        if file_part:
                            content_list.append(file_part)
                    msg["content"] = content_list

                # Handle tool calls in assistant messages
                if m.role == "assistant" and m.tool_calls:
                    msg["tool_calls"] = [
                        {
                            "id": tc.get("id", f"call_{i}"),
                            "type": "function",
                            "function": {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]},
                        }
                        for i, tc in enumerate(m.tool_calls)
                    ]

                # Handle tool responses - THIS IS THE FIX
                if m.role == "tool":
                    msg["tool_call_id"] = m.tool_call_id or ""
                    # FIX: Use tool_name as fallback when name is not set
                    # This fixes "Tool message must have either name or tool_call_id" errors
                    msg["name"] = m.name or getattr(m, 'tool_name', None) or ""

                    if m.audio is not None and len(m.audio) > 0:
                        log_warning("Audio input is currently unsupported.")
                    if m.images is not None and len(m.images) > 0:
                        log_warning("Image input is currently unsupported.")
                    if m.videos is not None and len(m.videos) > 0:
                        log_warning("Video input is currently unsupported.")
                        
                formatted_messages.append(msg)

            return formatted_messages
        
        LiteLLM._format_messages = patched_format_messages
        
    except Exception as e:
        logger.warning(f"[Patches] Failed to apply LiteLLM tool message patch: {e}")
