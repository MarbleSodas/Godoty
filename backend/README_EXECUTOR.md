# Executor Agent for Godot Assistant

An executor agent that works directly with structured data from the planning agent, without complex parsing or validation.

## Overview

The executor agent follows these principles:
- **Direct Integration**: Works with structured ExecutionPlan objects from the planning agent
- **Minimal Complexity**: No text parsing, no complex validation, no MCP integration
- **Streaming Support**: Real-time execution progress via Server-Sent Events
- **Core Tools**: Essential Godot and file management tools only

## Components

### Core Files

1. **Execution Models** (`execution_models.py`)
   - Basic data structures: ExecutionPlan, ExecutionStep, ToolCall
   - Simple status enums and result types
   - No complex validation or risk assessment

2. **Execution Engine** (`execution_engine.py`)
   - Basic dependency resolution
   - Tool execution with timeout
   - Streaming event generation
   - No rollback or advanced features

3. **Executor Agent** (`executor_agent.py`)
   - Main executor interface
   - Global instance management
   - Basic execution methods
   - Model configuration with fallback support (openrouter/sherlock-dash-alpha default, minimax/minimax-m2 fallback)

4. **API Routes** (`executor_routes.py`)
   - Clean FastAPI endpoints
   - Server-Sent Events for streaming
   - Basic status management

## Usage

### Basic Execution

```python
from agents.executor_agent import get_executor_agent
from agents.execution_models import ExecutionPlan, ExecutionStep, ToolCall

# Create executor agent
agent = get_executor_agent()

# Create a simple plan (from planning agent)
plan = ExecutionPlan(
    title="Create Player",
    description="Create a player character",
    steps=[
        ExecutionStep(
            title="Create Node",
            description="Create player node",
            tool_calls=[
                ToolCall(
                    name="create_node",
                    parameters={"node_type": "CharacterBody2D", "parent_path": "Root"}
                )
            ]
        )
    ]
)

# Execute with streaming
async for event in agent.execute_plan(plan):
    print(f"Event: {event.type}")
    print(f"Data: {event.data}")
```

### API Usage

```python
import requests

# Execute plan via API
response = requests.post(
    "http://localhost:8000/api/executor/execute",
    json={
        "plan": {
            "title": "Create Player",
            "description": "Create a player character",
            "steps": [
                {
                    "title": "Create Node",
                    "description": "Create player node",
                    "tool_calls": [
                        {
                            "name": "create_node",
                            "parameters": {
                                "node_type": "CharacterBody2D",
                                "parent_path": "Root"
                            }
                        }
                    ]
                }
            ]
        }
    },
    stream=True
)

# Process streaming response
for line in response.iter_lines():
    if line:
        event = json.loads(line.decode('utf-8'))
        print(f"Event: {event['event_type']}")
```

## Available Tools

### Godot Tools
- `create_node` - Create nodes in scene tree
- `delete_node` - Delete nodes
- `modify_node_property` - Modify node properties
- `create_scene` - Create new scenes
- `open_scene` - Open scenes
- `play_scene` - Start playing scene
- `stop_playing` - Stop playing

### File Tools
- `write_file` - Write files with backup
- `read_file` - Read files
- `delete_file` - Delete files

## API Endpoints

- `POST /api/executor/execute` - Execute plan with streaming
- `GET /api/executor/status/{execution_id}` - Get execution status
- `POST /api/executor/cancel/{execution_id}` - Cancel execution
- `GET /api/executor/active` - List active executions
- `GET /api/executor/health` - Health check

## Stream Events

- `execution_started` - Execution initiated
- `step_started` - Step execution started
- `tool_started` - Tool call initiated
- `tool_completed` - Tool call completed
- `tool_failed` - Tool call failed
- `step_completed` - Step execution finished
- `execution_completed` - Execution finished
- `execution_error` - Unexpected error

## Integration with Planning Agent

The planning agent should output structured plans that match the ExecutionPlan format:

```python
# Planning agent output (structured, not text)
plan_data = {
    "title": "Create Player Character",
    "description": "Create a player character with sprite",
    "steps": [
        {
            "title": "Create Player Node",
            "description": "Create CharacterBody2D node",
            "tool_calls": [
                {
                    "name": "create_node",
                    "parameters": {
                        "node_type": "CharacterBody2D",
                        "parent_path": "Root",
                        "node_name": "Player"
                    }
                }
            ]
        },
        {
            "title": "Add Sprite",
            "description": "Add Sprite2D as child",
            "tool_calls": [
                {
                    "name": "create_node",
                    "parameters": {
                        "node_type": "Sprite2D",
                        "parent_path": "Root/Player"
                    }
                }
            ],
            "depends_on": ["create_node"]
        }
    ]
}
```

## Model Configuration

The executor agent uses dedicated model configuration separate from the planning agent:

### Default Models
- **Primary Model**: `openrouter/sherlock-dash-alpha`
- **Fallback Model**: `minimax/minimax-m2`

### Configuration Variables
Add these to your `.env` file:
```bash
# Executor Model Configuration
DEFAULT_EXECUTOR_MODEL=openrouter/sherlock-dash-alpha
EXECUTOR_FALLBACK_MODEL=minimax/minimax-m2
```

### Fallback Behavior
The executor agent automatically falls back to the secondary model if:
- The primary model fails to initialize
- The primary model encounters rate limits
- The primary model experiences API errors

This ensures reliable execution even when the preferred model is unavailable.

## Testing

Run the test:
```bash
python test_executor.py
```

This demonstrates:
- Plan creation from structured data
- Dependency resolution
- Tool execution
- Streaming events

## Key Features

- ✅ **Direct Integration**: Works with structured ExecutionPlan objects from planning agent
- ✅ **Basic Dependency Resolution**: Handles step dependencies correctly
- ✅ **Streaming Execution**: Real-time progress feedback via Server-Sent Events
- ✅ **Essential Godot Tools**: Node creation, deletion, property modification, scene management
- ✅ **File Operations**: Read, write, and delete files with backup support
- ✅ **Error Handling**: Graceful error handling and clear feedback
- ✅ **API Endpoints**: RESTful API with streaming support
- ✅ **Model Configuration**: Dedicated models with fallback support (openrouter/sherlock-dash-alpha, minimax/minimax-m2)
- ✅ **Minimal Complexity**: No unnecessary parsing or validation overhead

## Benefits

1. **Simplicity**: Easy to understand and maintain
2. **Reliability**: Fewer moving parts, fewer failure points
3. **Performance**: No parsing overhead, direct execution
4. **Integration**: Works directly with structured planning agent output
5. **Flexibility**: Easy to extend with new tools as needed

## Usage

Use this executor agent when:
- You need reliable plan execution
- Planning agent can output structured data
- You want efficient execution with proper model configuration
- You need streaming progress feedback
- You want fallback model support for reliability

---

The executor agent provides a clean, straightforward way to execute AI-generated plans in Godot projects with proper model configuration and fallback support.