# Godot Agent Integration Tools

This module provides comprehensive tools for AI agents to interact with Godot projects through a secure WebSocket-based connection to the Godot Editor plugin.

## Overview

The Godot integration consists of three main components:

1. **Godot Bridge** (`godot_bridge.py`) - WebSocket connection manager
2. **Godot Debug Tools** (`godot_debug_tools.py`) - Comprehensive debugging and analysis tools
3. **Godot Executor Tools** (`godot_executor_tools.py`) - Action and automation tools

## Comprehensive Debugging Tools

The Godot Debug Tools provide agents with extensive debugging capabilities for visual input, logging, scene analysis, and runtime debugging.

### **1. Visual Input Tools**

#### `capture_visual_context(include_3d=True)`
- **Purpose**: Capture comprehensive visual context from the Godot viewport
- **Returns**: `VisualSnapshot` with screenshot path and viewport metadata
- **Use Case**: Get complete visual understanding of current editor state

#### `capture_editor_viewport(include_3d=True, include_2d=True)`
- **Purpose**: Capture focused editor viewport screenshot with detailed metadata
- **Returns**: Dict containing screenshot path, viewport info, and editor state
- **Use Case**: Precise visual analysis of specific editor viewports

#### `capture_game_viewport(wait_frames=3)`
- **Purpose**: Capture in-game viewport screenshot with timing control
- **Returns**: Dict containing screenshot path and game state information
- **Use Case**: Capture gameplay screenshots for debugging or documentation

#### `get_visual_debug_info()`
- **Purpose**: Get visual debugging overlays and information
- **Returns**: Dict containing debug overlays, collision shapes, navigation data
- **Use Case**: Analyze debug visualizations and collision/navigation information

### **2. Enhanced Log Access Tools**

#### `get_debug_output(lines=100, severity_filter=None)`
- **Purpose**: Get parsed debug output with severity analysis
- **Parameters**:
  - `lines`: Number of recent lines to retrieve
  - `severity_filter`: Filter by 'error', 'warning', 'info'
- **Returns**: Dict containing parsed messages, severity counts, and metadata
- **Use Case**: Quick access to recent debug messages with analysis

#### `get_debug_logs(severity_filter=None, time_range=None, limit=200)`
- **Purpose**: Get filtered debug logs with advanced parsing and analytics
- **Parameters**:
  - `severity_filter`: Filter by severity level
  - `time_range`: Filter by time ('recent', 'last_minute', 'last_hour')
  - `limit`: Maximum number of log entries
- **Returns**: Dict containing filtered logs, analytics, and common errors
- **Use Case**: Comprehensive log analysis with time-based filtering

#### `search_debug_logs(pattern, case_sensitive=False, regex=False)`
- **Purpose**: Search debug logs for specific patterns
- **Parameters**:
  - `pattern`: Search pattern
  - `case_sensitive`: Whether search is case sensitive
  - `regex`: Use regex pattern matching
- **Returns**: Dict containing matching log entries and search metadata
- **Use Case**: Find specific errors, warnings, or patterns in debug logs

#### `monitor_debug_output(duration=10, severity_filter=None)`
- **Purpose**: Monitor debug output in real-time
- **Parameters**:
  - `duration`: Monitoring duration in seconds
  - `severity_filter`: Optional severity filter
- **Returns**: Dict containing captured debug output during monitoring
- **Use Case**: Real-time debugging and log monitoring

### **3. Scene Analysis Tools**

#### `analyze_scene_tree(detailed=False)`
- **Purpose**: Analyze current scene tree structure
- **Parameters**: `detailed`: Include detailed node properties
- **Returns**: Dict containing scene tree hierarchy and complexity analysis
- **Use Case**: Scene structure analysis and optimization recommendations

#### `get_project_overview()`
- **Purpose**: Get comprehensive project information
- **Returns**: Dict containing project structure, scenes, resources, metadata
- **Use Case**: Project-wide analysis and documentation

#### `inspect_scene_file(scene_path)`
- **Purpose**: Inspect scene file without loading it
- **Parameters**: `scene_path`: Path to scene file
- **Returns**: Dict containing scene structure and metadata
- **Use Case**: Static scene analysis without loading

#### `search_nodes(search_type, query, scene_root=None)`
- **Purpose**: Search for nodes in the scene tree
- **Parameters**:
  - `search_type`: 'name', 'type', 'group', 'script'
  - `query`: Search query
  - `scene_root`: Optional scene root to limit scope
- **Returns**: List of `NodeInfo` objects
- **Use Case**: Find specific nodes or analyze scene structure

### **4. Advanced Scene Analysis Tools**

#### `analyze_node_performance(node_path)`
- **Purpose**: Analyze performance metrics for a specific node
- **Parameters**: `node_path`: Path to node to analyze
- **Returns**: Dict containing performance data and optimization suggestions
- **Use Case**: Node-specific performance analysis and optimization

#### `get_scene_debug_overlays(scene_path=None)`
- **Purpose**: Get scene debug overlays and visualization information
- **Parameters**: `scene_path`: Optional specific scene path
- **Returns**: Dict containing debug overlays, collision shapes, navigation meshes
- **Use Case**: Visual debugging information and overlay analysis

#### `compare_scenes(scene_path_a, scene_path_b)`
- **Purpose**: Compare two scenes and highlight differences
- **Parameters**: Paths to both scenes to compare
- **Returns**: Dict containing comparison results and differences
- **Use Case**: Scene versioning, diff analysis, and change tracking

### **5. Runtime Debugging Tools**

#### `get_debugger_state()`
- **Purpose**: Get current debugger state and information
- **Returns**: Dict containing debugger state, breakpoints, debugging context
- **Use Case**: Check debugger status and breakpoint information

#### `access_debug_variables(variable_filter=None)`
- **Purpose**: Access debug variables and watches from debugging context
- **Parameters**: `variable_filter`: Optional filter by name or type
- **Returns**: Dict containing organized debug variables and metadata
- **Use Case**: Inspect variable values during debugging sessions

#### `get_call_stack_info(max_depth=10)`
- **Purpose**: Get current call stack information
- **Parameters**: `max_depth`: Maximum call stack depth
- **Returns**: Dict containing call stack frames and debugging information
- **Use Case**: Analyze call stack for debugging and code analysis

### **6. Performance Monitoring**

#### `get_performance_metrics()`
- **Purpose**: Get current performance metrics from Godot
- **Returns**: Dict containing FPS, memory usage, frame time, draw calls
- **Use Case**: Performance analysis and optimization

## Quick Start

### Basic Usage

```python
from agents.tools import (
    get_project_overview,
    analyze_scene_tree,
    capture_visual_context,
    get_debug_logs,
    create_node,
    play_scene,
    ensure_godot_connection
)

# Ensure connection to Godot
await ensure_godot_connection()

# Get project overview
overview = await get_project_overview()

# Capture visual context
visual = await capture_visual_context()

# Get recent debug logs with error filtering
errors = await get_debug_logs(severity_filter="error")

# Analyze scene tree
scene_analysis = await analyze_scene_tree(detailed=True)
print(f"Project: {overview['project_info']['name']}")

# Analyze current scene
scene_analysis = await analyze_scene_tree(detailed=True)
print(f"Total nodes: {scene_analysis['analysis']['total_nodes']}")

# Create a new node
from agents.tools import CreationResult
result: CreationResult = await create_node("Node2D", "Root", "NewNode")
if result.success:
    print(f"Created node at: {result.created_path}")
```

### Configuration

Add these environment variables to your `.env` file:

```bash
# Godot Integration
ENABLE_GODOT_TOOLS=true
GODOT_BRIDGE_HOST=localhost
GODOT_BRIDGE_PORT=9001
GODOT_CONNECTION_TIMEOUT=10.0
GODOT_MAX_RETRIES=3
GODOT_RETRY_DELAY=2.0
GODOT_COMMAND_TIMEOUT=30.0
GODOT_SCREENSHOT_DIR=.godoty/screenshots
```

## Components

### 1. Godot Bridge (`godot_bridge.py`)

The core WebSocket connection manager that handles communication with the Godot Editor plugin.

#### Key Features:
- Robust connection management with automatic reconnection
- Command/response handling with timeout management
- Project path detection and validation
- Message routing and error handling

#### Usage:

```python
from agents.tools.godot_bridge import GodotBridge, get_godot_bridge

# Get global bridge instance
bridge = get_godot_bridge()

# Send custom command
response = await bridge.send_command("custom_command", param1="value")
if response.success:
    print(f"Command result: {response.data}")
```

### 2. Godot Debug Tools (`godot_debug_tools.py`)

Tools for planning agents to analyze and understand Godot projects.

#### Key Functions:

##### `get_project_overview()`
Get comprehensive project information.

```python
from agents.tools import get_project_overview

overview = await get_project_overview()
print(f"Project path: {overview['project_info']['path']}")
print(f"Current scene: {overview['current_scene']['name']}")
```

##### `analyze_scene_tree(detailed=False)`
Analyze the current scene tree structure.

```python
from agents.tools import analyze_scene_tree

# Basic analysis
analysis = await analyze_scene_tree()
print(f"Scene depth: {analysis['analysis']['depth']}")

# Detailed analysis with recommendations
detailed = await analyze_scene_tree(detailed=True)
for recommendation in detailed['recommendations']:
    print(f"- {recommendation}")
```

##### `capture_visual_context(include_3d=True)`
Capture screenshots and viewport information.

```python
from agents.tools import capture_visual_context, VisualSnapshot

snapshot: VisualSnapshot = await capture_visual_context()
if snapshot.screenshot_path:
    print(f"Screenshot saved to: {snapshot.screenshot_path}")
print(f"Viewport size: {snapshot.viewport_size}")
```

##### `search_nodes(search_type, query, scene_root=None)`
Search for nodes in the scene tree.

```python
from agents.tools import search_nodes

# Search by type
nodes = await search_nodes("type", "Node2D")
for node in nodes:
    print(f"Found Node2D: {node.name} at {node.path}")

# Search by name
nodes = await search_nodes("name", "Player")

# Search by group
nodes = await search_nodes("group", "enemies")
```

### 3. Godot Executor Tools (`godot_executor_tools.py`)

Tools for executor agents to perform actions and make changes.

#### Key Functions:

##### `create_node(node_type, parent_path, **kwargs)`
Create a new node in the scene tree.

```python
from agents.tools import create_node, CreationResult

result: CreationResult = await create_node(
    node_type="Sprite2D",
    parent_path="Root",
    node_name="PlayerSprite",
    properties={"texture": "res://player.png"}
)

if result.success:
    print(f"Created node: {result.created_path}")
else:
    print(f"Error: {result.error}")
```

##### `modify_node_property(node_path, property_name, new_value)`
Modify a property of a node.

```python
from agents.tools import modify_node_property, ModificationResult

result: ModificationResult = await modify_node_property(
    node_path="Root/PlayerSprite",
    property_name="position",
    new_value={"x": 100, "y": 50}
)

if result.success:
    print(f"Changed position from {result.old_value} to {result.new_value}")
```

##### `create_scene(scene_name, **kwargs)`
Create a new scene.

```python
from agents.tools import create_scene, CreationResult

result: CreationResult = await create_scene(
    scene_name="PlayerScene",
    root_node_type="Node2D",
    save_path="res://scenes/player.tscn"
)

if result.success:
    print(f"Created scene: {result.created_path}")
```

##### `play_scene()` and `stop_playing()`
Control scene playback.

```python
from agents.tools import play_scene, stop_playing

# Start playing the current scene
if await play_scene():
    print("Scene started playing")

# Stop playing
if await stop_playing():
    print("Scene stopped")
```

### 4. Godot Security (`godot_security.py`)

Security validation and safeguards for all operations.

#### Key Features:
- Operation risk assessment (SAFE, LOW, MEDIUM, HIGH, CRITICAL)
- Path validation to prevent directory traversal
- Parameter validation and sanitization
- Configurable security context

#### Usage:

```python
from agents.tools.godot_security import (
    SecurityContext, OperationRisk, validate_operation
)

# Create custom security context
context = SecurityContext(project_path="/path/to/project")
context.set_risk_threshold(OperationRisk.LOW)  # Only allow low-risk operations

# Validate an operation manually
result = await validate_operation("delete_node", {"node_path": "Root/Node"})
if not result.allowed:
    print(f"Operation blocked: {result.reason}")
```

## Security Model

### Risk Levels

- **SAFE**: Read-only operations (get info, search, screenshots)
- **LOW**: Non-destructive operations (select, focus, play)
- **MEDIUM**: Reversible modifications (create, modify properties)
- **HIGH**: Destructive operations (delete nodes)
- **CRITICAL**: Potentially dangerous operations (modify project settings)

### Security Rules

1. **Path Validation**: All paths are validated against the project directory
2. **Operation Filtering**: Operations are filtered by risk level
3. **Parameter Validation**: All parameters are validated before execution
4. **Audit Logging**: All operations are logged with success/failure status

### Default Security Context

The default security context allows:
- All SAFE operations
- LOW and MEDIUM risk operations
- Blocks HIGH and CRITICAL operations

## Error Handling

All functions return structured result objects:

```python
from agents.tools import CreationResult, ModificationResult

# Handle creation results
result: CreationResult = await create_node("Node2D", "Root")
if result.success:
    print(f"Success: {result.created_path}")
else:
    print(f"Error: {result.error}")

# Handle modification results
result: ModificationResult = await modify_node_property("Root/Node", "visible", False)
if result.success:
    print(f"Changed {result.old_value} to {result.new_value}")
else:
    print(f"Error: {result.error}")
```

## Integration with Agents

### Planning Agent Usage

Planning agents should primarily use debug tools:

```python
# Analyze current state
overview = await get_project_overview()
scene_analysis = await analyze_scene_tree(detailed=True)
visual_context = await capture_visual_context()

# Search for specific nodes
player_nodes = await search_nodes("name", "Player")
enemy_nodes = await search_nodes("group", "enemies")

# Generate insights and recommendations
recommendations = scene_analysis['recommendations']
```

### Executor Agent Usage

Executor agents should use executor tools with proper error handling:

```python
# Execute operations with validation
try:
    # Create a new player
    player_result = await create_node("CharacterBody2D", "Root", "Player")
    if not player_result.success:
        raise Exception(f"Failed to create player: {player_result.error}")

    # Add sprite to player
    sprite_result = await create_node("Sprite2D", player_result.created_path, "Sprite")
    if sprite_result.success:
        await modify_node_property(
            sprite_result.created_path,
            "texture",
            "res://player.png"
        )

except Exception as e:
    logger.error(f"Executor error: {e}")
    # Handle error appropriately
```

## Best Practices

### 1. Connection Management

```python
# Always ensure connection before operations
if not await ensure_godot_connection():
    raise Exception("Failed to connect to Godot")

# Check project readiness
bridge = get_godot_bridge()
if not bridge.is_project_ready():
    raise Exception("Godot project not ready")
```

### 2. Error Handling

```python
# Use structured error handling
result = await create_node("Node2D", "Root")
if not result.success:
    logger.error(f"Node creation failed: {result.error}")
    return False

# Log successful operations
logger.info(f"Created node: {result.created_path}")
```

### 3. Security

```python
# Validate operations manually when needed
validation = validate_operation("delete_node", {"node_path": "Root/ImportantNode"})
if not validation.allowed:
    logger.warning(f"Operation blocked: {validation.reason}")
    return False
```

### 4. Performance

```python
# Use batch operations for multiple nodes
creations = [
    {"node_type": "Node2D", "parent_path": "Root", "node_name": f"Node{i}"}
    for i in range(10)
]
results = await create_node_batch(creations)

# Process results
successful = [r for r in results if r.success]
failed = [r for r in results if not r.success]
```

## Troubleshooting

### Common Issues

1. **Connection Failed**
   - Ensure Godot Editor is running with the plugin
   - Check that port 9001 is available
   - Verify plugin is enabled in Godot

2. **Operation Blocked**
   - Check security context risk level
   - Validate paths and parameters
   - Review operation risk classification

3. **Command Timeout**
   - Increase `GODOT_COMMAND_TIMEOUT` in configuration
   - Check Godot Editor responsiveness
   - Verify WebSocket connection stability

### Debug Logging

Enable debug logging to troubleshoot issues:

```python
import logging
logging.getLogger("agents.tools.godot_bridge").setLevel(logging.DEBUG)
logging.getLogger("agents.tools.godot_debug_tools").setLevel(logging.DEBUG)
logging.getLogger("agents.tools.godot_executor_tools").setLevel(logging.DEBUG)
logging.getLogger("agents.tools.godot_security").setLevel(logging.DEBUG)
```

## API Reference

### Data Classes

#### `CreationResult`
- `success: bool` - Operation succeeded
- `created_path: Optional[str]` - Path to created object
- `created_id: Optional[str]` - ID of created object
- `error: Optional[str]` - Error message if failed

#### `ModificationResult`
- `success: bool` - Operation succeeded
- `modified_path: Optional[str]` - Path to modified object
- `old_value: Any` - Previous value
- `new_value: Any` - New value
- `error: Optional[str]` - Error message if failed

#### `SceneInfo`
- `name: str` - Scene name
- `path: str` - Scene file path
- `root_node_type: str` - Type of root node
- `node_count: int` - Total nodes in scene
- `has_script: bool` - Root node has script
- `script_path: Optional[str]` - Path to script if present

#### `NodeInfo`
- `name: str` - Node name
- `type: str` - Node type
- `path: str` - Node path in scene tree
- `parent: Optional[str]` - Parent node path
- `children: List[str]` - Child node paths
- `properties: Dict[str, Any]` - Node properties
- `groups: List[str]` - Node groups
- `has_script: bool` - Node has attached script
- `script_path: Optional[str]` - Path to script if present

#### `VisualSnapshot`
- `screenshot_path: Optional[str]` - Path to screenshot file
- `viewport_size: Tuple[int, int]` - Viewport dimensions
- `camera_info: Dict[str, Any]` - Camera information
- `selected_nodes: List[str]` - Currently selected nodes
- `scene_tree_state: Dict[str, Any]` - Scene tree state

### Enums

#### `OperationRisk`
- `SAFE` - Read-only operations
- `LOW` - Non-destructive operations
- `MEDIUM` - Reversible modifications
- `HIGH` - Destructive operations
- `CRITICAL` - Potentially dangerous operations

## Examples

See the `examples/` directory for complete usage examples:

- `basic_usage.py` - Basic operations and error handling
- `planning_agent.py` - Planning agent workflow
- `executor_agent.py` - Executor agent workflow
- `security_demo.py` - Security validation examples
- `batch_operations.py` - Batch operation examples

## Contributing

When adding new Godot tools:

1. Implement security validation
2. Add comprehensive error handling
3. Write tests for all functionality
4. Update documentation
5. Follow the existing code style
6. Consider backward compatibility

## License

This module is part of the Godot Assistant project and follows the same license terms.