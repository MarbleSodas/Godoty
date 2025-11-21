"""
OpenRouter Custom Model Provider for Strands Agents

This module provides a custom model provider that integrates OpenRouter's API
with the Strands Agents framework, enabling streaming and tool calling.
"""

import json
import logging
from typing import AsyncIterable, Optional, Any, Dict, List, Type, TypeVar, Union, AsyncGenerator, TypedDict
from typing_extensions import Unpack
import httpx

from pydantic import BaseModel
from strands.models import Model
from strands.types.content import Messages, SystemContentBlock
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolSpec

logger = logging.getLogger(__name__)


# Custom exception for rate limiting
class ModelThrottledException(Exception):
    """Exception raised when the model API rate limit is exceeded."""
    pass

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
    Custom model provider for OpenRouter API with Strands Agents.

    Supports:
    - Streaming responses via Server-Sent Events (SSE)
    - Tool calling with automatic format conversion
    - Error handling and retries
    - Multiple model selection
    """

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        api_key: str,
        **model_config: Unpack[ModelConfig]
    ) -> None:
        """
        Initialize OpenRouter model provider.

        Args:
            api_key: OpenRouter API key
            **model_config: Model configuration including model_id, app_name, app_url,
                          timeout, temperature, max_tokens, params
        """
        self.api_key = api_key

        # Store configuration with defaults
        self._config: ModelConfig = {
            "model_id": "openai/gpt-4-turbo",
            "app_name": "Godot-Assistant",
            "app_url": "http://localhost:8000",
            "timeout": 120,
            "temperature": 0.7,
            "max_tokens": 4000,
            **model_config  # type: ignore
        }

        # Initialize HTTP client
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._config.get("timeout", 120)),
            headers=self._get_headers()
        )

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for OpenRouter API requests."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": self._config.get("app_url", "http://localhost:8000"),
            "X-Title": self._config.get("app_name", "Godot-Assistant"),
            "Content-Type": "application/json"
        }

    def _convert_tool_to_openai_format(self, tool_spec: Dict) -> Dict:
        """
        Convert Strands tool spec (Bedrock format) to OpenAI function format.

        Args:
            tool_spec: Strands tool specification

        Returns:
            OpenAI function specification
        """
        return {
            "type": "function",
            "function": {
                "name": tool_spec.get("name"),
                "description": tool_spec.get("description", ""),
                "parameters": tool_spec.get("input_schema", {})
            }
        }

    def _convert_messages_to_openai_format(self, messages: Messages) -> List[Dict]:
        """
        Convert Strands messages format to OpenAI format.

        Args:
            messages: Strands messages

        Returns:
            OpenAI formatted messages
        """
        openai_messages = []

        for message in messages:
            role = message.get("role")
            content = message.get("content", [])

            # Handle different content types
            if isinstance(content, str):
                openai_messages.append({
                    "role": role,
                    "content": content
                })
            elif isinstance(content, list):
                # Process content blocks
                text_parts = []
                tool_calls = []

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
                        # Tool result from previous execution
                        tool_result = block["toolResult"]
                        openai_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_result.get("toolUseId", ""),
                            "content": json.dumps(tool_result.get("content", []))
                        })

                # Add message with text and/or tool calls
                if text_parts or tool_calls:
                    msg = {"role": role}
                    if text_parts:
                        msg["content"] = "\n".join(text_parts)
                    if tool_calls:
                        msg["tool_calls"] = tool_calls
                    openai_messages.append(msg)

        return openai_messages

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
        Stream chat completion from OpenRouter API.

        Args:
            messages: Conversation messages
            tool_specs: Optional tool specifications
            system_prompt: Optional system prompt
            tool_choice: Optional tool choice strategy ('auto', 'none', or specific function)
            system_prompt_content: Optional system prompt content blocks
            **kwargs: Additional parameters

        Yields:
            StreamEvent objects
        """
        print("\n" + "=" * 80)
        print("[OPENROUTER] MODEL.STREAM() CALLED!")
        print(f"[OPENROUTER] Messages: {messages}")
        print(f"[OPENROUTER] Tool specs count: {len(tool_specs) if tool_specs else 0}")
        print(f"[OPENROUTER] System prompt: {system_prompt[:100] if system_prompt else 'None'}...")
        print("=" * 80 + "\n")
        try:
            # Convert messages to OpenAI format
            openai_messages = self._convert_messages_to_openai_format(messages)

            # Add system prompt if provided
            if system_prompt:
                openai_messages.insert(0, {
                    "role": "system",
                    "content": system_prompt
                })

            # Prepare request payload
            payload = {
                "model": self._config.get("model_id", "openai/gpt-4-turbo"),
                "messages": openai_messages,
                "stream": True,
                "temperature": self._config.get("temperature", 0.7),
                "max_tokens": self._config.get("max_tokens", 4000)
            }

            # Add tools if provided
            if tool_specs:
                payload["tools"] = [
                    self._convert_tool_to_openai_format(spec)
                    for spec in tool_specs
                ]
                # Use provided tool_choice or default to "auto"
                payload["tool_choice"] = tool_choice if tool_choice is not None else "auto"

            # Make streaming request
            print(f"[OPENROUTER] Making HTTP request to OpenRouter...")
            print(f"[OPENROUTER] Payload model: {payload.get('model')}")
            print(f"[OPENROUTER] Payload has tools: {bool(payload.get('tools'))}")
            print(f"[OPENROUTER] Payload max_tokens: {payload.get('max_tokens')}")
            print(f"[OPENROUTER] Payload stream: {payload.get('stream')}")

            # Check if payload is too large
            import json
            payload_size = len(json.dumps(payload))
            print(f"[OPENROUTER] Payload size: {payload_size} bytes")
            if payload_size > 100000:
                print(f"[OPENROUTER] WARNING: Very large payload!")
            async with self._client.stream(
                "POST",
                f"{self.BASE_URL}/chat/completions",
                json=payload
            ) as response:
                print(f"[OPENROUTER] Got response! Status: {response.status_code}")
                response.raise_for_status()

                # Parse SSE stream and convert to Strands events
                chunk_count = 0
                async for event in self._parse_sse_stream(response):
                    chunk_count += 1
                    print(f"[OPENROUTER] Yielding SSE event #{chunk_count}: {list(event.keys())}")
                    yield event

                print(f"[OPENROUTER] Stream completed. Total chunks: {chunk_count}")

        except httpx.HTTPStatusError as e:
            # Handle rate limiting
            if e.response.status_code == 429:
                logger.error("OpenRouter rate limit exceeded")
                raise ModelThrottledException("Rate limit exceeded")

            logger.error(f"OpenRouter API error: {e}")
            # Yield error event
            yield {
                "messageStop": {
                    "stopReason": "error"
                }
            }
        except httpx.HTTPError as e:
            logger.error(f"OpenRouter HTTP error: {e}")
            yield {
                "messageStop": {
                    "stopReason": "error"
                }
            }
        except Exception as e:
            logger.error(f"Unexpected error in stream: {e}")
            yield {
                "messageStop": {
                    "stopReason": "error"
                }
            }

    async def _parse_sse_stream(
        self,
        response: httpx.Response
    ) -> AsyncIterable[StreamEvent]:
        """
        Parse Server-Sent Events stream and convert to Strands StreamEvents.

        This method follows the Strands OpenAI model pattern:
        1. Accumulate tool calls during streaming
        2. Yield tool call events AFTER text content streaming completes
        3. Use correct nested structure for toolUse events

        Args:
            response: HTTPX streaming response

        Yields:
            StreamEvent objects
        """
        message_started = False
        content_block_started = False
        accumulated_text = ""
        finish_reason = None
        usage_data = None

        # Accumulate tool calls indexed by their index (for multiple tool calls)
        tool_calls: dict[int, list[dict]] = {}

        lines_processed = 0
        chunks_processed = 0

        print(f"[OPENROUTER] Starting SSE parsing...")
        async for line in response.aiter_lines():
            line = line.strip()
            lines_processed += 1
            if line:  # Only log non-empty lines
                print(f"[OPENROUTER] SSE line #{lines_processed}: {line[:200]}")

            # Skip empty lines and comments
            if not line or line.startswith(":"):
                continue

            # Parse SSE data
            if line.startswith("data: "):
                data = line[6:]  # Remove "data: " prefix

                # Check for end of stream
                if data == "[DONE]":
                    logger.info(f"[STREAM] Received [DONE] marker after {chunks_processed} chunks")
                    break

                try:
                    chunk = json.loads(data)
                    chunks_processed += 1

                    # Log first chunk for debugging
                    if chunks_processed == 1:
                        logger.info(f"[STREAM] First chunk: {json.dumps(chunk)[:500]}")
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse SSE data: {data}")
                    continue

                # Capture usage metadata if present
                if "usage" in chunk:
                    usage_data = chunk["usage"]

                # Handle error responses
                if "error" in chunk:
                    logger.error(f"OpenRouter error: {chunk['error']}")
                    yield {
                        "messageStop": {
                            "stopReason": "error",
                            "error": chunk["error"].get("message", "Unknown error")
                        }
                    }
                    break

                # Process chunks
                print(f"[OPENROUTER DEBUG] Raw Chunk: {json.dumps(chunk)}")
                choices = chunk.get("choices", [])
                if not choices:
                    logger.warning(f"[STREAM] Chunk has no choices: {chunk}")
                    continue

                delta = choices[0].get("delta", {})
                # DEBUG: Print delta to debug tool calls
                if "tool_calls" in delta or "function_call" in delta:
                    print(f"[OPENROUTER DEBUG] Tool/Function Delta: {delta}")
                
                choice_finish_reason = choices[0].get("finish_reason")

                # Log finish reasons when they appear
                if choice_finish_reason:
                    logger.info(f"[STREAM] Received finish_reason: {choice_finish_reason}")

                # Debug: Log delta structure to understand tool call format
                if "tool_calls" in delta or "function_call" in delta:
                    logger.info(f"[STREAM] Tool call delta received: {json.dumps(delta)}")

                # Start message if not started
                if not message_started:
                    yield {"messageStart": {"role": "assistant"}}
                    message_started = True

                # Handle content (text)
                if "content" in delta and delta["content"]:
                    if not content_block_started:
                        yield {"contentBlockStart": {"start": {}}}
                        content_block_started = True

                    text_chunk = delta["content"]
                    accumulated_text += text_chunk

                    yield {
                        "contentBlockDelta": {
                            "delta": {"text": text_chunk}
                        }
                    }

                # Accumulate tool calls (following OpenAI model pattern)
                # We'll yield them AFTER streaming completes
                if "tool_calls" in delta:
                    for tool_call in delta["tool_calls"]:
                        index = tool_call.get("index", 0)
                        tool_calls.setdefault(index, []).append(tool_call)
                
                # Handle function_call (legacy/alternative format)
                elif "function_call" in delta:
                    fc = delta["function_call"]
                    # Treat as tool_call index 0
                    index = 0
                    
                    # Convert to tool_call format
                    tool_call = {"index": index, "function": {}}
                    if "name" in fc:
                        tool_call["function"]["name"] = fc["name"]
                        # Also set id if this is the first chunk with name
                        tool_call["id"] = f"call_{hash(fc['name'])}"
                    if "arguments" in fc:
                        tool_call["function"]["arguments"] = fc["arguments"]
                        
                    tool_calls.setdefault(index, []).append(tool_call)

                # Handle finish
                if choice_finish_reason:
                    finish_reason = choice_finish_reason
                    if content_block_started:
                        yield {"contentBlockStop": {}}
                        content_block_started = False
                    break

        # After loop completes, check if we have a finish_reason
        # If not, assume 'stop' if we received at least one chunk (successful completion)
        print(f"[OPENROUTER] SSE loop completed!")
        print(f"[OPENROUTER] Lines processed: {lines_processed}")
        print(f"[OPENROUTER] Chunks processed: {chunks_processed}")
        print(f"[OPENROUTER] Finish reason: {finish_reason}")
        print(f"[OPENROUTER] Message started: {message_started}")
        print(f"[OPENROUTER] Accumulated text length: {len(accumulated_text)}")
        if not finish_reason:
            if chunks_processed > 0:
                logger.warning(f"[STREAM] Stream ended without finish_reason after {chunks_processed} chunks - assuming 'stop'")
                finish_reason = "stop"
            else:
                logger.error(f"[STREAM] Stream ended without any chunks - genuine error")
                yield {
                    "messageStop": {
                        "stopReason": "error",
                        "error": "Stream ended without producing any content"
                    }
                }
                return

        # After streaming completes, yield accumulated tool calls
        # This follows the Strands OpenAI model pattern
        print(f"[OPENROUTER] Processing {len(tool_calls)} accumulated tool calls")
        print(f"[OPENROUTER] Tool calls dict keys: {list(tool_calls.keys())}")
        print(f"[OPENROUTER] Tool calls dict: {tool_calls}")
        logger.info(f"[STREAM] Processing {len(tool_calls)} accumulated tool calls")
        for tool_deltas in tool_calls.values():
            if not tool_deltas:
                continue

            # Get the first delta which has the tool info
            first_delta = tool_deltas[0]
            function = first_delta.get("function", {})
            tool_id = first_delta.get("id", "")
            tool_name = function.get("name", "")

            # Generate tool ID if not provided
            if tool_name and not tool_id:
                import hashlib
                tool_id = f"toolu_{hashlib.md5(tool_name.encode()).hexdigest()[:24]}"
                logger.debug(f"Generated tool ID: {tool_id} for tool: {tool_name}")

            # Yield contentBlockStart with correct nested structure
            # This matches the Strands OpenAI model format
            logger.info(f"[STREAM] Yielding contentBlockStart for tool: {tool_name} (ID: {tool_id})")
            yield {
                "contentBlockStart": {
                    "start": {
                        "toolUse": {  # <-- Key difference: nested under "toolUse"
                            "name": tool_name,
                            "toolUseId": tool_id,
                        }
                    }
                }
            }

            # Yield deltas for tool arguments
            for tool_delta in tool_deltas:
                function = tool_delta.get("function", {})
                if "arguments" in function and function["arguments"]:
                    yield {
                        "contentBlockDelta": {
                            "delta": {
                                "toolUse": {"input": function["arguments"]}
                            }
                        }
                    }

            # Close the tool use content block
            yield {"contentBlockStop": {}}

        # Map OpenAI finish reasons to Strands stop reasons
        stop_reason_map = {
            "stop": "end_turn",
            "length": "max_tokens",
            "tool_calls": "tool_use",
            "content_filter": "content_filtered"
        }

        # If we have tool calls but no explicit tool_calls finish reason,
        # set it to tool_use
        final_stop_reason = stop_reason_map.get(finish_reason, "end_turn")
        if tool_calls and final_stop_reason == "end_turn":
            logger.info(f"Tool calls present but finish_reason was '{finish_reason}', setting stop_reason to 'tool_use'")
            final_stop_reason = "tool_use"

        logger.info(f"[STREAM] Finish reason: {finish_reason}, mapped stop_reason: {final_stop_reason}, tool_calls count: {len(tool_calls)}")

        yield {
            "messageStop": {
                "stopReason": final_stop_reason
            }
        }

        # Yield metadata if we collected it
        if usage_data:
            yield {
                "metadata": {
                    "usage": {
                        "inputTokens": usage_data.get("prompt_tokens", 0),
                        "outputTokens": usage_data.get("completion_tokens", 0),
                        "totalTokens": usage_data.get("total_tokens", 0)
                    }
                }
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

        Args:
            output_model: Pydantic model class
            prompt: Conversation messages
            system_prompt: Optional system prompt
            **kwargs: Additional parameters

        Yields:
            Dictionary containing validated model instance or partial data
        """
        # Collect full response
        full_response = ""
        async for event in self.stream(prompt, system_prompt=system_prompt, **kwargs):
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"]["delta"]
                if "text" in delta:
                    full_response += delta["text"]
                    # Optionally yield partial data for streaming
                    yield {"partial": delta["text"]}

        # Parse as JSON and validate with Pydantic
        try:
            data = json.loads(full_response)
            validated_model = output_model(**data)
            yield {"result": validated_model}
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse structured output: {e}")
            yield {"error": str(e)}
            raise

    def update_config(self, **model_config: Unpack[ModelConfig]) -> None:
        """Update model configuration."""
        self._config.update(model_config)  # type: ignore

    def get_config(self) -> ModelConfig:
        """Get current model configuration."""
        return self._config.copy()  # type: ignore

    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

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
        Get a complete (non-streaming) chat completion from OpenRouter API.

        This method bypasses the streaming functionality to avoid the toolUseId error
        in the Strands framework streaming handler.

        Args:
            messages: Conversation messages
            tool_specs: Optional tool specifications
            system_prompt: Optional system prompt
            tool_choice: Optional tool choice strategy ('auto', 'none', or specific function)
            system_prompt_content: Optional system prompt content blocks
            **kwargs: Additional parameters

        Returns:
            Complete response dictionary with content and tool calls
        """
        try:
            # Convert messages to OpenAI format
            openai_messages = self._convert_messages_to_openai_format(messages)

            # Add system prompt if provided
            if system_prompt:
                openai_messages.insert(0, {
                    "role": "system",
                    "content": system_prompt
                })

            # Prepare request payload (non-streaming)
            payload = {
                "model": self._config.get("model_id", "openai/gpt-4-turbo"),
                "messages": openai_messages,
                "stream": False,  # Non-streaming request
                "temperature": self._config.get("temperature", 0.7),
                "max_tokens": self._config.get("max_tokens", 4000)
            }

            # Add tools if provided
            if tool_specs:
                payload["tools"] = [
                    self._convert_tool_to_openai_format(spec)
                    for spec in tool_specs
                ]
                # Use provided tool_choice or default to "auto"
                payload["tool_choice"] = tool_choice if tool_choice is not None else "auto"

            # Make non-streaming request
            response = await self._client.post(
                f"{self.BASE_URL}/chat/completions",
                json=payload
            )
            response.raise_for_status()

            result = response.json()

            # Convert OpenAI response format to Strands-compatible format
            return self._convert_openai_response_to_strands(result)

        except httpx.HTTPStatusError as e:
            # Handle rate limiting
            if e.response.status_code == 429:
                logger.error("OpenRouter rate limit exceeded")
                raise ModelThrottledException("Rate limit exceeded")

            logger.error(f"OpenRouter API error: {e}")
            raise Exception(f"OpenRouter API error: {e}")
        except httpx.HTTPError as e:
            logger.error(f"OpenRouter HTTP error: {e}")
            raise Exception(f"OpenRouter HTTP error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in complete: {e}")
            raise Exception(f"Unexpected error in complete: {e}")

    def _convert_openai_response_to_strands(self, openai_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert OpenAI response format to Strands-compatible format.

        Args:
            openai_response: OpenAI API response

        Returns:
            Strands-compatible response dictionary with usage metrics
        """
        try:
            choices = openai_response.get("choices", [])
            if not choices:
                return {
                    "message": {"content": [{"text": "No response generated"}]},
                    "usage": openai_response.get("usage", {}),
                    "id": openai_response.get("id")
                }

            choice = choices[0]
            message = choice.get("message", {})

            # Extract content
            content = message.get("content", "")

            # Extract tool calls
            tool_calls = message.get("tool_calls", [])
            
            # Check for legacy function_call if no tool_calls
            if not tool_calls and message.get("function_call"):
                fc = message.get("function_call")
                tool_calls = [{
                    "id": f"call_{hash(fc.get('name', ''))}",
                    "type": "function",
                    "function": fc
                }]
                
            content_blocks = []

            # Add text content if present
            if content:
                content_blocks.append({"text": content})

            # Add tool calls if present
            for tool_call in tool_calls:
                function = tool_call.get("function", {})
                tool_name = function.get("name", "")
                tool_args = function.get("arguments", "{}")

                try:
                    tool_input = json.loads(tool_args) if tool_args else {}
                except json.JSONDecodeError:
                    tool_input = {"raw_arguments": tool_args}

                content_blocks.append({
                    "toolUse": {
                        "toolUseId": tool_call.get("id", f"tool_{hash(tool_name)}"),
                        "name": tool_name,
                        "input": tool_input
                    }
                })

            return {
                "message": {
                    "content": content_blocks,
                    "role": "assistant"
                },
                "stop_reason": choice.get("finish_reason", "end_turn"),
                "usage": openai_response.get("usage", {}),
                "id": openai_response.get("id"),  # OpenRouter generation ID
                "model": openai_response.get("model")  # Actual model used
            }

        except Exception as e:
            logger.error(f"Error converting OpenAI response: {e}")
            return {
                "message": {"content": [{"text": f"Error processing response: {str(e)}"}]},
                "usage": openai_response.get("usage", {}),
                "id": openai_response.get("id")
            }
