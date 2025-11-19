# Planning Agent Documentation

## Overview

The Planning Agent is a Strands-based AI agent that uses OpenRouter's API to generate detailed execution plans for other agents. It features:

- **Streaming responses** via Server-Sent Events (SSE)
- **Tool calling** with file system and web search capabilities
- **MCP (Model Context Protocol) integration** for advanced reasoning and documentation fetching
- **Custom OpenRouter model provider** for Strands Agents
- **RESTful API** endpoints via FastAPI

## Setup

### 1. Install Dependencies

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Install MCP Servers (Optional but Recommended)

The agent supports MCP (Model Context Protocol) tools for enhanced capabilities. Install them using:

```bash
# Install uvx (if not already installed)
pip install uvx

# MCP servers will be auto-invoked via uvx/npx when enabled
# No manual installation needed - they're fetched on-demand
```

**MCP Servers Supported:**
- **Sequential Thinking** - Advanced step-by-step reasoning for complex problems
- **Context7** - Up-to-date library documentation fetching

### 3. Configure Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and add your OpenRouter API key:

```env
OPENROUTER_API_KEY=your_actual_api_key_here
DEFAULT_PLANNING_MODEL=openai/gpt-4-turbo
FALLBACK_MODEL=openai/gpt-4-turbo
AGENT_TEMPERATURE=0.7
AGENT_MAX_TOKENS=4000
APP_NAME=Godot-Assistant
APP_URL=http://localhost:8000

# MCP Configuration (Optional)
ENABLE_MCP_TOOLS=true
MCP_FAIL_SILENTLY=true
ENABLE_SEQUENTIAL_THINKING=true
ENABLE_CONTEXT7=true
SEQUENTIAL_THINKING_COMMAND=uvx
SEQUENTIAL_THINKING_ARGS=mcp-server-sequential-thinking
CONTEXT7_COMMAND=npx
CONTEXT7_ARGS=-y,@context7/mcp-server
```

**Note:** The model `openai/gpt-5.1-codex` was specified but may not be available yet. The configuration defaults to `openai/gpt-4-turbo` as a reliable alternative.

### 4. Run the Application

```bash
python main.py
```

The FastAPI server will start on `http://127.0.0.1:8000`

## API Endpoints

### Health Check

Check if the agent is ready:

```bash
GET /api/agent/health
```

**Response:**
```json
{
  "status": "healthy",
  "agent_ready": true,
  "model": "openai/gpt-4-turbo"
}
```

### Create Plan (Non-Streaming)

Generate a plan without streaming:

```bash
POST /api/agent/plan
Content-Type: application/json

{
  "prompt": "Create a plan for building a 2D platformer game in Godot",
  "reset_conversation": false
}
```

**Response:**
```json
{
  "status": "success",
  "plan": "# Plan for 2D Platformer Game...",
  "metadata": null
}
```

### Create Plan (Streaming)

Generate a plan with real-time streaming:

```bash
POST /api/agent/plan/stream
Content-Type: application/json

{
  "prompt": "Create a plan for implementing user authentication",
  "reset_conversation": false
}
```

**Response:** Server-Sent Events (SSE)

Events you'll receive:
- `event: start` - Plan generation started
- `event: message_start` - Message started
- `event: data` - Text chunks as they're generated
- `event: tool_use_start` - Agent is using a tool
- `event: tool_use_delta` - Tool input being sent
- `event: metadata` - Token usage information
- `event: end` - Plan generation completed
- `event: done` - Stream finished

### Reset Conversation

Clear the conversation history:

```bash
POST /api/agent/reset
```

**Response:**
```json
{
  "status": "success",
  "message": "Conversation history reset"
}
```

### Get Configuration

View current agent configuration:

```bash
GET /api/agent/config
```

**Response:**
```json
{
  "status": "success",
  "config": {
    "model_id": "openai/gpt-4-turbo",
    "model_config": {
      "temperature": 0.7,
      "max_tokens": 4000
    },
    "tools": [
      "read_file",
      "list_files",
      "search_codebase",
      "search_documentation",
      "fetch_webpage",
      "get_godot_api_reference"
    ],
    "conversation_manager": "SlidingWindowConversationManager"
  }
}
```

## Available Tools

The planning agent has access to the following tools:

### MCP Tools (Optional)

When MCP integration is enabled, the agent gains access to:

#### Sequential Thinking Tool

**Purpose:** Provides advanced step-by-step reasoning for complex, multi-step problems.

**When to Use:**
- Complex architectural decisions
- Multi-step algorithm design
- Debugging intricate issues
- Breaking down ambiguous requirements
- Exploring alternative approaches

**Capabilities:**
- Hypothesis generation and verification
- Iterative problem-solving with course correction
- Exploring edge cases and dependencies
- Adjustable reasoning depth

**Example Usage:**
```python
# Agent automatically uses this tool when facing complex problems
# that require deep analysis and iterative reasoning
```

#### Context7 Documentation Tools

**Purpose:** Fetch up-to-date library documentation and code examples.

**Available Tools:**
1. **resolve-library-id(library_name: str)**
   - Resolve library name to Context7 ID
   - Example: "fastapi" → "/tiangolo/fastapi"

2. **get-library-docs(library_id: str, topic: str, tokens: int)**
   - Fetch documentation for a specific library
   - Parameters:
     - `library_id`: Context7 library identifier (from resolve-library-id)
     - `topic`: Specific area to focus on (e.g., "routing", "authentication")
     - `tokens`: Documentation depth (default: 5000)

**Example Usage:**
```python
# 1. Resolve library
resolve-library-id("fastapi")  # Returns: "/tiangolo/fastapi"

# 2. Get documentation
get-library-docs(
    library_id="/tiangolo/fastapi",
    topic="routing",
    tokens=5000
)
```

### File System Tools

1. **read_file(file_path: str)**
   - Read contents of a file
   - Example: `read_file("./main.py")`

2. **list_files(directory: str, pattern: str)**
   - List files in a directory with optional glob pattern
   - Example: `list_files("./agents", "*.py")`

3. **search_codebase(pattern: str, directory: str, file_pattern: str, max_results: int)**
   - Search for regex patterns in the codebase
   - Example: `search_codebase("class.*Agent", ".", "*.py")`

### Web Tools

4. **search_documentation(query: str, source: str)**
   - Search for documentation on a topic
   - Sources: "general", "godot", "python", "fastapi", "strands"
   - Example: `search_documentation("Node2D", "godot")`

5. **fetch_webpage(url: str, extract_text: bool)**
   - Fetch and extract content from a webpage
   - Example: `fetch_webpage("https://docs.godotengine.org", True)`

6. **get_godot_api_reference(class_name: str)**
   - Get Godot API documentation for a specific class
   - Example: `get_godot_api_reference("CharacterBody2D")`

## Testing with cURL

### Non-Streaming Request

```bash
curl -X POST http://localhost:8000/api/agent/plan \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a plan for implementing a save/load system in Godot",
    "reset_conversation": false
  }'
```

### Streaming Request

```bash
curl -X POST http://localhost:8000/api/agent/plan/stream \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a plan for adding multiplayer support to a game",
    "reset_conversation": false
  }' \
  --no-buffer
```

## Testing with Python

```python
import httpx
import asyncio
import json

async def test_streaming():
    url = "http://localhost:8000/api/agent/plan/stream"
    data = {
        "prompt": "Create a plan for building a physics-based puzzle game",
        "reset_conversation": False
    }

    async with httpx.AsyncClient() as client:
        async with client.stream("POST", url, json=data, timeout=120.0) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    event_data = line[6:]  # Remove "data: " prefix
                    if event_data and event_data != "{}":
                        data = json.loads(event_data)
                        if "text" in data:
                            print(data["text"], end="", flush=True)
            print()  # New line at end

asyncio.run(test_streaming())
```

## Architecture

### Project Structure

```
backend/
├── agents/                      # Agent module
│   ├── __init__.py
│   ├── config/                 # Modular configuration (NEW)
│   │   ├── __init__.py        # Unified config interface
│   │   ├── model_config.py    # Model settings
│   │   ├── tool_config.py     # Tool & MCP settings
│   │   ├── prompts.py         # System prompts
│   │   └── validators.py      # Configuration validation
│   ├── planning_agent.py       # Main planning agent
│   ├── models/                 # Custom model providers
│   │   ├── __init__.py
│   │   └── openrouter.py      # OpenRouter integration
│   └── tools/                  # Agent tools
│       ├── __init__.py
│       ├── file_system_tools.py
│       ├── web_tools.py
│       └── mcp_tools.py       # MCP integration
├── api/                        # API routes
│   ├── __init__.py
│   └── agent_routes.py        # Agent endpoints
├── tests/                      # Test suite (NEW)
│   ├── __init__.py
│   ├── conftest.py            # Shared pytest fixtures
│   ├── test_planning_agent.py # Planning agent tests
│   ├── test_executor_agent.py # Executor agent tests
│   ├── test_api_endpoints.py  # API integration tests
│   ├── test_mcp_integration.py # MCP tests
│   ├── test_multi_agent.py    # Multi-agent tests
│   └── README.md              # Testing guide
├── main.py                     # Application entry point
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (gitignored)
└── .env.example               # Environment template
```

### Key Components

1. **OpenRouterModel** (`agents/models/openrouter.py`)
   - Custom Strands model provider
   - Handles OpenAI SSE format → Strands StreamEvents conversion
   - Tool calling format conversion
   - Error handling and retries

2. **PlanningAgent** (`agents/planning_agent.py`)
   - Main agent implementation
   - Integrates model, tools, and conversation management
   - Provides sync, async, and streaming interfaces

3. **Tools** (`agents/tools/`)
   - File system operations
   - Web search and documentation fetching
   - Godot-specific API reference
   - MCP tools integration (optional)

4. **MCPToolManager** (`agents/tools/mcp_tools.py`)
   - Singleton manager for MCP connections
   - Handles initialization and lifecycle of MCP servers
   - Provides graceful degradation if servers unavailable
   - Supports multiple concurrent MCP servers

5. **API Routes** (`api/agent_routes.py`)
   - FastAPI endpoints
   - SSE streaming support
   - Request/response models

## Troubleshooting

### Agent won't start

- Check that `OPENROUTER_API_KEY` is set in `.env`
- Verify the model ID is correct and available on OpenRouter
- Check logs for initialization errors

### Streaming not working

- Ensure your client supports Server-Sent Events
- Check that nginx or proxy doesn't buffer responses
- Verify `X-Accel-Buffering: no` header is set

### Tool calls failing

- Check file permissions for file system tools
- Verify network connectivity for web tools
- Review tool execution logs in console

### High token usage

- Reduce `AGENT_MAX_TOKENS` in `.env`
- Use conversation reset more frequently
- Consider using a cheaper model for simple plans

### MCP tools not working

**Symptoms:**
- Agent starts but MCP tools not listed in `/api/agent/config`
- Logs show "No MCP servers connected successfully"
- Tool calls to sequential-thinking or context7 fail

**Solutions:**

1. **Install required dependencies:**
   ```bash
   # For sequential-thinking
   pip install uvx

   # For context7 (requires Node.js)
   node --version  # Should be v18+
   npm --version
   ```

2. **Test MCP servers manually:**
   ```bash
   # Test sequential-thinking
   uvx mcp-server-sequential-thinking

   # Test context7
   npx -y @context7/mcp-server
   ```

3. **Check environment variables:**
   ```bash
   # Verify in .env
   ENABLE_MCP_TOOLS=true
   ENABLE_SEQUENTIAL_THINKING=true
   ENABLE_CONTEXT7=true
   ```

4. **Review logs for specific errors:**
   ```bash
   # Look for MCP initialization messages
   python main.py 2>&1 | grep -i mcp
   ```

5. **Try disabling individual servers:**
   ```env
   # In .env, test one at a time
   ENABLE_SEQUENTIAL_THINKING=true
   ENABLE_CONTEXT7=false  # Disable to isolate issues
   ```

6. **Graceful degradation:**
   If MCP servers are optional for your use case:
   ```env
   MCP_FAIL_SILENTLY=true  # Agent continues without MCP
   ```

### MCP server connection timeout

**Symptoms:**
- Agent takes long to start
- First request hangs
- Connection timeout errors

**Solutions:**

1. **MCP servers initialize lazily** - First request will be slower
2. **Pre-warm the agent:**
   ```bash
   # Make a test request after starting
   curl http://localhost:8000/api/agent/health
   ```
3. **Check network connectivity** for npm/uvx package downloads
4. **Increase timeout in client:**
   ```python
   async with httpx.AsyncClient(timeout=120.0) as client:
       # Longer timeout for first request
   ```

### Sequential thinking using too many tokens

**Symptoms:**
- High token usage with complex plans
- Cost higher than expected

**Solutions:**

1. **Disable sequential-thinking for simple tasks:**
   ```env
   ENABLE_SEQUENTIAL_THINKING=false
   ```

2. **Use it selectively** - Only enable when needed for complex planning

3. **Monitor usage:**
   ```bash
   # Check metadata in streaming responses
   # Look for token counts
   ```

## Recent Enhancements

- [x] **MCP Integration** - Sequential thinking and Context7 tools
- [x] **Graceful Degradation** - Agent works even if MCP servers unavailable
- [x] **Lazy Initialization** - MCP tools load on-demand
- [x] **Comprehensive Testing** - MCP-specific test suite

## Future Enhancements

- [ ] Add support for more models (Anthropic, Google, etc.)
- [ ] Implement persistent session storage (Redis/SQLite)
- [ ] Add rate limiting and cost tracking
- [ ] Create frontend UI for agent interaction
- [ ] Add more Godot-specific tools
- [ ] Implement plan validation and execution
- [ ] Add structured output for plans (JSON schema)
- [ ] Create agent swarms for complex planning
- [ ] Add more MCP servers (e.g., code analysis, testing tools)
- [ ] Implement MCP tool caching for better performance
