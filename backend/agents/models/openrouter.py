"""
OpenRouter Custom Model Provider for Strands Agents

This module provides a custom model provider that integrates the official OpenRouter Python SDK
with the Strands Agents framework, enabling streaming and tool calling.
"""

import json
import logging
import httpx
from typing import AsyncIterable, Optional, Any, Dict, List, Type, TypeVar, Union, AsyncGenerator, TypedDict, cast
from typing_extensions import Unpack
import re

from pydantic import BaseModel
from strands.models import Model
from strands.types.content import Messages, SystemContentBlock
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolSpec

from openrouter import OpenRouter
from openrouter import components
from openrouter.utils import eventstreaming

logger = logging.getLogger(__name__)

# TypeVar for structured output
T = TypeVar('T', bound=BaseModel)

class ModelConfig(TypedDict, total=False):
    """Configuration for OpenRouter model."""
    model_id: str
    app_name: str
    app_url: str
    timeout: int
    temperature: float
    max_tokens: int
    params: Optional[Dict[str, Any]]

class OpenRouterModel(Model):
    """
    Custom model provider for OpenRouter API with Strands Agents using the official OpenRouter SDK.
    
    Acts as an adapter between Strands 'Model' interface and OpenRouter SDK.

    Supports:
    - Streaming responses
    - Tool calling
    - Error handling
    """

    def __init__(
        self,
        api_key: str,
        **model_config: Unpack[ModelConfig]
    ) -> None:
        """
        Initialize OpenRouter model provider.

        Args:
            api_key: OpenRouter API key
            **model_config: Model configuration
        """
        if not api_key or not api_key.strip():
            raise ValueError("OpenRouter API key cannot be empty.")
        
        self.api_key = api_key.strip()

        # Store configuration with defaults
        self._config: ModelConfig = {
            "model_id": "openai/gpt-4-turbo",
            "app_name": "Godoty",
            "app_url": "http://localhost:8000",
            "timeout": 120,
            "temperature": 0.7,
            "max_tokens": 4000,
            **model_config  # type: ignore
        }

        # Initialize HTTP client with headers
        headers = {
            "HTTP-Referer": self._config.get("app_url", "http://localhost:8000"),
            "X-Title": self._config.get("app_name", "Godoty"),
        }
        
        # Initialize Async Client for the SDK
        self._async_http_client = httpx.AsyncClient(
            headers=headers,
            timeout=float(self._config.get("timeout", 120))
        )

        # Initialize OpenRouter SDK Client
        self._client = OpenRouter(
            api_key=self.api_key,
            async_client=self._async_http_client
        )
        
        logger.info(f"OpenRouterModel initialized with model: {self._config.get('model_id')}")

    def _convert_tool_to_sdk_format(self, tool_spec: Dict) -> Dict:
        """
        Convert Strands tool spec to OpenRouter SDK tool format (standard OpenAI schema).
        """
        # Strands uses 'inputSchema' or 'input_schema' depending on version/context
        schema = tool_spec.get("inputSchema") or tool_spec.get("input_schema") or {}
        
        # Strands wraps the actual JSON schema in a 'json' key
        if "json" in schema:
            parameters = schema["json"]
        else:
            parameters = schema

        return {
            "type": "function",
            "function": {
                "name": tool_spec.get("name"),
                "description": tool_spec.get("description", ""),
                "parameters": parameters
            }
        }

    def _convert_messages_to_sdk_format(self, messages: Messages) -> List[Dict]:
        """
        Convert Strands messages format to OpenRouter SDK format.
        """
        sdk_messages = []

        for message in messages:
            role = message.get("role")
            content = message.get("content", [])

            if isinstance(content, str):
                sdk_messages.append({
                    "role": role,
                    "content": content
                })
            elif isinstance(content, list):
                # Process content blocks
                text_parts = []
                tool_calls = []
                
                # Keep track of tool results to add as separate messages if needed
                # But Strands usually puts tool results in "user" or "tool" role messages.
                # Here we are processing a single message's content list.
                
                for block in content:
                    if "text" in block:
                        text_parts.append(block["text"])
                    elif "toolUse" in block:
                        tool_use = block["toolUse"]
                        tool_calls.append({
                            "id": tool_use.get("toolUseId", ""),
                            "type": "function",
                            "function": {
                                "name": tool_use.get("name", ""),
                                "arguments": json.dumps(tool_use.get("input", {}))
                            }
                        })
                    elif "toolResult" in block:
                        # Tool result is a separate message in OpenAI format usually
                        # If we encounter it here, it means Strands grouped it.
                        # We should probably handle it by appending a tool message to sdk_messages
                        tool_result = block["toolResult"]
                        sdk_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_result.get("toolUseId", ""),
                            "content": json.dumps(tool_result.get("content", []))
                        })

                # Add the main message part (text + tool_calls)
                if text_parts or tool_calls:
                    msg = {"role": role}
                    if text_parts:
                        msg["content"] = "\n".join(text_parts)
                    if tool_calls:
                        msg["tool_calls"] = tool_calls
                    
                    # Avoid adding empty assistant message if we only added tool results above
                    if role != "tool": 
                        sdk_messages.append(msg)

        return sdk_messages

    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        *,
        tool_choice: Optional[str] = None,
        system_prompt_content: Optional[list[SystemContentBlock]] = None,
        **kwargs: Any
    ) -> AsyncIterable[StreamEvent]:
        """
        Stream chat completion from OpenRouter API using the SDK.
        """
        try:
            # Convert messages
            sdk_messages = self._convert_messages_to_sdk_format(messages)

            # Add system prompt
            if system_prompt:
                sdk_messages.insert(0, {
                    "role": "system",
                    "content": system_prompt
                })

            # Prepare tools
            tools = None
            if tool_specs:
                tools = [
                    self._convert_tool_to_sdk_format(spec)
                    for spec in tool_specs
                ]

            # Call SDK
            # Note: extra_body params can be passed via specific SDK args if available or 
            # we might need to check if the SDK supports extra_body passthrough.
            # The `send_async` method in generated SDK often has specific named parameters.
            
            params = self._config.get("params", {})
            
            # Using the SDK's send_async method
            # We cast to Any to avoid strict type checking issues with the generated SDK types vs dicts
            stream_response = await self._client.chat.send_async(
                model=self._config.get("model_id"),
                messages=cast(Any, sdk_messages),
                stream=True,
                temperature=self._config.get("temperature"),
                max_tokens=self._config.get("max_tokens"),
                tools=cast(Any, tools) if tools else None,
                tool_choice=tool_choice if tools and tool_choice else ("auto" if tools else None),
                extra_body={"usage": {"include": True}}
            )
            
            # Process the stream
            async for event in self._process_sdk_stream(stream_response):
                yield event

        except Exception as e:
            logger.error(f"Error in OpenRouter SDK stream: {e}")
            yield {
                "messageStop": {
                    "stopReason": "error",
                    "error": str(e)
                }
            }

    async def _process_sdk_stream(self, stream) -> AsyncIterable[StreamEvent]:
        """
        Process OpenRouter SDK EventStream.
        """
        message_started = False
        content_block_started = False
        final_finish_reason = "end_turn"
        
        # Track active tool state
        # Key: index. Value: {id: str, name: str, has_started: bool}
        active_tools = {}
        
        async for chunk in stream:
            # Chunk is ChatStreamingResponseChunk
            
            # DEBUG LOGGING
            if chunk.choices and chunk.choices[0].delta.tool_calls:
                 logger.info(f"🛠️ SDK TOOL CALL CHUNK: {chunk.choices[0].delta.tool_calls}")
            
            if not chunk.choices:
                continue
                
            choice = chunk.choices[0]
            delta = choice.delta
            finish_reason = choice.finish_reason

            if not message_started:
                yield {"messageStart": {"role": "assistant"}}
                message_started = True
            
            # Capture finish reason
            if finish_reason:
                logger.info(f"SDK Finish Reason: {finish_reason}")
                # Map OpenAI/OpenRouter reasons to Strands reasons
                if finish_reason == "tool_calls":
                    final_finish_reason = "tool_use"
                elif finish_reason == "stop":
                    final_finish_reason = "end_turn"
                else:
                    final_finish_reason = finish_reason

            # Handle content
            if delta.content:
                if not content_block_started:
                    yield {"contentBlockStart": {"start": {}}}
                    content_block_started = True
                
                yield {
                    "contentBlockDelta": {
                        "delta": {"text": delta.content}
                    }
                }

            # Handle tool calls
            if delta.tool_calls:
                # If we were in a text block, close it
                if content_block_started:
                    yield {"contentBlockStop": {}}
                    content_block_started = False
                
                for tool_call in delta.tool_calls:
                    idx = tool_call.index
                    
                    if idx not in active_tools:
                        active_tools[idx] = {"id": "", "name": "", "has_started": False}
                    
                    state = active_tools[idx]
                    
                    # Update state
                    if tool_call.id:
                        state["id"] = tool_call.id
                    if tool_call.function and tool_call.function.name:
                        state["name"] = tool_call.function.name
                    
                    # If we have Name and ID, start block
                    if not state["has_started"] and state["name"] and state["id"]:
                        event = {
                            "contentBlockStart": {
                                "start": {
                                    "toolUse": {
                                        "name": state["name"],
                                        "toolUseId": state["id"]
                                    }
                                }
                            }
                        }
                        logger.info(f"Yielding Tool Start: {event}")
                        yield event
                        state["has_started"] = True
                    
                    # Yield arguments delta if started
                    # We only check if arguments are present (not None)
                    if state["has_started"] and tool_call.function and tool_call.function.arguments is not None:
                        # Only yield if there is actual content
                        if tool_call.function.arguments:
                            event = {
                                "contentBlockDelta": {
                                    "delta": {
                                        "toolUse": {
                                            "input": tool_call.function.arguments
                                        }
                                    }
                                }
                            }
                            logger.info(f"Yielding Tool Args: {event}")
                            yield event

            # Handle finish
            if finish_reason:
                if content_block_started:
                    yield {"contentBlockStop": {}}
                    content_block_started = False
                
                # Close any open tool blocks
                for idx, state in active_tools.items():
                    if state["has_started"]:
                        event = {"contentBlockStop": {}}
                        logger.info(f"Yielding Tool Stop (finish_reason): {event}")
                        yield event
                        state["has_started"] = False

        # Ensure we close any lingering blocks if finish_reason wasn't sent (e.g. error)
        if content_block_started:
             yield {"contentBlockStop": {}}
        for idx, state in active_tools.items():
             if state["has_started"]:
                 event = {"contentBlockStop": {}}
                 logger.info(f"Yielding Tool Stop (cleanup): {event}")
                 yield event

        yield {"messageStop": {"stopReason": final_finish_reason}}

    async def complete(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        *,
        tool_choice: Optional[str] = None,
        system_prompt_content: Optional[list[SystemContentBlock]] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Get a complete (non-streaming) chat completion.
        """
        # Convert messages
        sdk_messages = self._convert_messages_to_sdk_format(messages)
        if system_prompt:
            sdk_messages.insert(0, {"role": "system", "content": system_prompt})

        tools = None
        if tool_specs:
             tools = [self._convert_tool_to_sdk_format(spec) for spec in tool_specs]

        response = await self._client.chat.send_async(
            model=self._config.get("model_id"),
            messages=cast(Any, sdk_messages),
            stream=False,
            temperature=self._config.get("temperature"),
            max_tokens=self._config.get("max_tokens"),
            tools=cast(Any, tools) if tools else None,
            tool_choice=tool_choice if tools and tool_choice else ("auto" if tools else None),
            extra_body={"usage": {"include": True}}
        )
        
        # Convert response to Strands format
        # Response is components.ChatResponse
        # We need to convert it to dict
        
        # Using basic conversion logic
        choice = response.choices[0]
        message = choice.message
        
        content_blocks = []
        if message.content:
            content_blocks.append({"text": message.content})
            
        if message.tool_calls:
            for tc in message.tool_calls:
                content_blocks.append({
                    "toolUse": {
                        "toolUseId": tc.id,
                        "name": tc.function.name,
                        "input": json.loads(tc.function.arguments)
                    }
                })
                
        return {
            "message": {
                "content": content_blocks,
                "role": "assistant"
            },
            "stop_reason": choice.finish_reason,
            "usage": response.usage.__dict__ if response.usage else {},
            "id": response.id,
            "model": response.model
        }

    async def structured_output(
        self,
        output_model: Type[T],
        prompt: Messages,
        system_prompt: Optional[str] = None,
        **kwargs: Any
    ) -> AsyncGenerator[dict[str, Union[T, Any]], None]:
        """
        Generate structured output using Pydantic model.
        """
        full_response = ""
        # Use self.stream to get the response
        async for event in self.stream(prompt, system_prompt=system_prompt, **kwargs):
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"]["delta"]
                if "text" in delta:
                    full_response += delta["text"]
                    yield {"partial": delta["text"]}
        
        # Parse and validate
        try:
            data = json.loads(full_response)
            validated_model = output_model(**data)
            yield {"result": validated_model}
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse structured output: {e}")
            yield {"error": str(e)}
            raise

    def update_config(self, **model_config: Unpack[ModelConfig]) -> None:
        self._config.update(model_config)  # type: ignore

    def get_config(self) -> ModelConfig:
        return self._config.copy()  # type: ignore

    async def close(self):
        await self._async_http_client.aclose()