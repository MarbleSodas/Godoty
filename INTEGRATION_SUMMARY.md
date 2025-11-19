# Strands Agent Loop Integration with OpenRouter - Implementation Summary

## Overview
Successfully integrated the Strands Agent Loop with OpenRouter to enable multi-step reasoning and tool execution in async and streaming contexts.

## Completed Work

### 1. **Refactored `plan_async` Method** (planning_agent.py:321-363)
- **Before**: Bypassed Strands Agent Loop by calling `self.model.complete()` directly
- **After**: Now uses `self.agent.invoke_async(prompt)` to leverage the full Agent Loop
- **Benefits**:
  - Enables multi-step reasoning
  - Supports recursive tool execution
  - Proper conversation management

### 2. **Refactored `plan_stream` Method** (planning_agent.py:365-453)
- **Before**: Bypassed Strands Agent Loop by calling `self.model.complete()` directly
- **After**: Now uses `self.agent.stream_async(prompt)` with event conversion
- **Benefits**:
  - Real-time streaming of text, tool calls, and results
  - Multi-step reasoning with tool execution
  - Proper event handling and conversation management

### 3. **Improved OpenRouter Streaming** (openrouter.py:351-423)
- Fixed toolUseId propagation in `_parse_sse_stream`
- Added support for complete tool call inputs in `contentBlockStart` event
- Implemented proper tool ID generation when OpenRouter doesn't provide one
- Added debug logging to track tool call format

### 4. **Test Suite** (reproduce_agent_loop.py)
- Created comprehensive test suite with 3 test scenarios
- Test 2 (streaming without tool use) **PASSES**
- Tests 1 and 3 (with tool execution) still have issues

## Current Status

### ✅ Working
- Streaming responses without tool use works perfectly
- Agent Loop is properly integrated for text-only responses
- Event conversion from Strands to expected format works correctly

### ⚠️ Issues Remaining
- **toolUseId Error**: When the model attempts to use tools, Strands' `handle_content_block_stop` function cannot find `toolUseId` in `current_tool_use`
- **Root Cause**: OpenRouter sends complete tool calls in a single delta, and Strands may not process the `contentBlockStart` event before receiving subsequent events
- **Multiple Tool Calls**: The model sometimes requests multiple tools simultaneously (indices 0, 1, etc.), which may complicate state tracking

## Technical Details

### OpenRouter Tool Call Format
OpenRouter returns tool calls in OpenAI-compatible JSON format:
```json
{
  "role": "assistant",
  "content": null,
  "tool_calls": [{
    "id": "31265636-446d-4a7d-a5dd-a7f9db369de2",
    "function": {
      "name": "list_files",
      "arguments": "{}"
    },
    "index": 0,
    "type": "function"
  }]
}
```

### ContentBlockStart Event Structure
We yield the following structure for tool use:
```python
{
  "contentBlockStart": {
    "start": {
      "type": "toolUse",
      "toolUseId": "31265636-446d-4a7d-a5dd-a7f9db369de2",
      "name": "list_files",
      "input": {}  # Included when complete arguments are available
    }
  }
}
```

## Next Steps

### Option 1: Debug Strands Event Processing
- Add more logging to understand how Strands processes `contentBlockStart`
- Verify that Strands extracts `toolUseId` from the correct path
- Check if there's a timing issue with event processing

### Option 2: Use Non-Streaming for Tool Calls
- Keep streaming for text responses
- Fall back to non-streaming (`complete()`) when tool calls are detected
- This would work around the streaming issue while maintaining most benefits

### Option 3: Investigate Strands Bedrock Implementation
- Review how Bedrock model handles tool calls in streaming
- Compare event structure and timing
- Adapt OpenRouter implementation to match

## Files Modified

1. `backend/agents/planning_agent.py`:
   - Lines 321-363: `plan_async` method
   - Lines 365-453: `plan_stream` method

2. `backend/agents/models/openrouter.py`:
   - Lines 282-287: Added `current_tool_id` tracking
   - Lines 333-334: Added debug logging
   - Lines 346-354: Added XML format detection
   - Lines 360-423: Improved tool call handling

3. `backend/reproduce_agent_loop.py`:
   - Complete rewrite as comprehensive test suite

4. `backend/test_openrouter_debug.py`:
   - New debug script (can be deleted)

## Recommendations

1. **Short Term**: Use Option 2 (non-streaming for tool calls) as a temporary workaround
2. **Medium Term**: Investigate Strands Bedrock implementation to understand proper event structure
3. **Long Term**: Consider contributing a fix to Strands or creating custom streaming handler

## Testing

To test the current implementation:
```bash
cd backend
python reproduce_agent_loop.py
```

Expected results:
- Test 1: FAIL (toolUseId error)
- Test 2: PASS ✓
- Test 3: FAIL (toolUseId error)

## References

- [Strands Agent Loop Documentation](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/agents/agent-loop/)
- OpenRouter API: https://openrouter.ai/docs
- Strands Agents GitHub: https://github.com/anthropics/strands-agents
