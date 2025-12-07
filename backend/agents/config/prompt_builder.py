"""
Dynamic prompt builder for Godoty agent.

Generates prompts with dynamic tool documentation based on available tools
and agent mode. This reduces prompt duplication and keeps tool docs in sync.
"""

from typing import List, Dict, Optional, Literal
from enum import Enum


class AgentMode(Enum):
    """Agent operation modes."""
    LEARNING = "learning"
    PLANNING = "planning"
    EXECUTION = "execution"


# Tool categorization for mode-based filtering
TOOL_CATEGORIES = {
    # Read-only tools (available in all modes)
    "read": {
        "file_system": [
            ("read_file", "Read file contents from the project"),
            ("list_files", "List files in a directory"),
            ("search_codebase", "Search for patterns in the codebase"),
        ],
        "scene_analysis": [
            ("get_project_overview", "Get overview of the Godot project"),
            ("analyze_scene_tree", "Analyze the scene tree structure"),
            ("inspect_scene_file", "Inspect a .tscn file"),
            ("search_nodes", "Search for nodes by name, type, or properties"),
        ],
        "debugging": [
            ("get_debug_logs", "Get debug output logs"),
            ("get_debug_output", "Get recent debug output"),
            ("get_debugger_state", "Get current debugger state"),
            ("get_performance_metrics", "Get performance metrics"),
            ("get_call_stack_info", "Get call stack information"),
        ],
        "documentation": [
            ("search_godot_docs", "Search the local Godot documentation cache"),
            ("get_class_reference", "Get detailed class reference for a Godot class"),
            ("get_documentation_status", "Check status of local documentation cache"),
            ("get_godot_api_reference", "Fetch API reference from official docs"),
        ],
        "context": [
            ("retrieve_context", "Search for relevant code, scenes, and documentation"),
            ("get_signal_flow", "Trace signal connections"),
            ("get_class_hierarchy", "Understand class inheritance"),
            ("find_usages", "Find where a class/function/signal is used"),
            ("get_file_context", "Get comprehensive context for a specific file"),
            ("get_project_structure", "Refresh the project overview"),
        ],
        "connection": [
            ("ensure_godot_connection", "Verify connection to Godot editor"),
        ],
        "visual": [
            ("capture_visual_context", "Capture visual screenshot of current state"),
            ("capture_editor_viewport", "Capture the editor viewport"),
            ("capture_game_viewport", "Capture the game viewport"),
            ("get_visual_debug_info", "Get visual debug information"),
        ],
    },
    # Write tools (execution mode only)
    "write": {
        "file_operations": [
            ("write_file", "Write content to a file"),
            ("delete_file", "Delete a file"),
        ],
        "node_operations": [
            ("create_node", "Create a new node in the scene"),
            ("delete_node", "Delete a node from the scene"),
            ("modify_node_property", "Modify a node's property"),
            ("reparent_node", "Move a node to a new parent"),
        ],
        "scene_operations": [
            ("create_scene", "Create a new scene"),
            ("open_scene", "Open a scene in the editor"),
            ("save_current_scene", "Save the current scene"),
            ("select_nodes", "Select nodes in the editor"),
        ],
        "gdscript_editing": [
            ("modify_gdscript_method", "Modify an existing method"),
            ("add_gdscript_method", "Add a new method to a script"),
            ("remove_gdscript_method", "Remove a method from a script"),
            ("refactor_gdscript_method", "Refactor a method"),
            ("extract_gdscript_method", "Extract code into a new method"),
        ],
        "project_settings": [
            ("modify_project_setting", "Modify a project setting"),
        ],
        "game_control": [
            ("play_scene", "Run the current scene"),
            ("stop_playing", "Stop the running game"),
        ],
    },
}

# Mode permissions
MODE_PERMISSIONS = {
    AgentMode.LEARNING: {"read"},
    AgentMode.PLANNING: {"read"},
    AgentMode.EXECUTION: {"read", "write"},
}


def get_tools_for_mode(mode: AgentMode) -> Dict[str, List[tuple]]:
    """Get available tools for a given mode."""
    allowed_categories = MODE_PERMISSIONS[mode]
    tools = {}
    
    for category in allowed_categories:
        for group_name, group_tools in TOOL_CATEGORIES.get(category, {}).items():
            if group_name not in tools:
                tools[group_name] = []
            tools[group_name].extend(group_tools)
    
    return tools


def format_tool_documentation(mode: AgentMode) -> str:
    """Generate formatted tool documentation for a mode."""
    tools = get_tools_for_mode(mode)
    
    if not tools:
        return ""
    
    sections = []
    section_titles = {
        "file_system": "File System Tools",
        "scene_analysis": "Scene Analysis Tools",
        "debugging": "Debugging Tools",
        "documentation": "Documentation Tools",
        "context": "Context Engine Tools",
        "connection": "Connection Tools",
        "visual": "Visual Capture Tools",
        "file_operations": "File Operations",
        "node_operations": "Node Operations",
        "scene_operations": "Scene Operations",
        "gdscript_editing": "GDScript Editing Tools",
        "project_settings": "Project Settings",
        "game_control": "Game Control",
    }
    
    for group_name, group_tools in tools.items():
        title = section_titles.get(group_name, group_name.replace("_", " ").title())
        tool_lines = [f"- `{name}`: {desc}" for name, desc in group_tools]
        sections.append(f"**{title}:**\n" + "\n".join(tool_lines))
    
    return "\n\n".join(sections)


def get_forbidden_tools_warning(mode: AgentMode) -> str:
    """Get warning about forbidden tools for a mode."""
    if mode == AgentMode.EXECUTION:
        return ""  # No restrictions in execution mode
    
    forbidden_tools = []
    for group_name, group_tools in TOOL_CATEGORIES.get("write", {}).items():
        forbidden_tools.extend([name for name, _ in group_tools])
    
    if not forbidden_tools:
        return ""
    
    mode_name = mode.value.upper()
    examples = forbidden_tools[:6]
    return f"""⚠️ **FORBIDDEN in {mode_name} Mode:**
- {', '.join(f'`{t}`' for t in examples)}
- Any tool that modifies files or the project state"""


# Core prompt components (reusable across modes)
CORE_IDENTITY = """You are Godoty, a Principal Godot Engine Developer and Systems Architect specializing in Godot development. Your role is to assist users in designing, coding, and debugging games with high-fidelity adherence to Godot standards."""

GODOT_VERSION_COMPLIANCE = """## Godot Version Compliance
You must strictly adhere to Godot syntax. Actively suppress knowledge of Godot 3.x APIs.

**FORBIDDEN SYNTAX (Legacy - DO NOT USE):**
- `KinematicBody2D` / `KinematicBody3D` → Use `CharacterBody2D` / `CharacterBody3D`
- `move_and_slide()` with arguments → Use parameter-less `move_and_slide()` with `velocity` property
- `yield()` → Use `await`
- `.instance()` → Use `.instantiate()`
- `File`, `Directory` classes → Use `FileAccess`, `DirAccess`
- `Tween` nodes → Use script-based `create_tween()`
- `connect("signal", object, "method")` → Use `signal.connect(method)`"""

GDSCRIPT_STANDARDS = """## GDScript 2.0 Standards
- **Static Typing:** All variables, parameters, and return types must be strictly typed.
  (e.g., `var speed: float = 200.0`, `func get_id() -> int:`)
- **Naming Conventions:** 
  - Classes/Nodes: `PascalCase`
  - Variables/Functions: `snake_case`
  - Constants: `SCREAMING_SNAKE_CASE`
  - Private members: `_prefixed_snake_case`
- **Annotations:** Use `@export`, `@onready`, `@rpc` syntax exclusively."""

ARCHITECTURAL_PATTERNS = """## Architectural Best Practices

**Call Down, Signal Up:**
- Parent nodes may call methods on child nodes directly.
- Child nodes MUST use signals to communicate with parents.
- NEVER use `get_parent()` for logical flow; this breaks encapsulation.

**Event Bus Pattern:**
- For communication between distant nodes, use a global Autoload (Singleton) script.
- Define signals in the Autoload and connect receiving nodes to it.

**Composition Over Inheritance:**
- Prefer small, modular Component nodes over deep inheritance trees.
- Use `class_name` to define reusable types.

**Resource Usage:**
- Use `Resource` subclasses (`.tres`) for static data instead of JSON or Dictionaries."""

SESSION_CONTINUATION = """## Session Continuation
When continuing a conversation or resuming a session:
- **ALWAYS use tools** to verify current project state before making recommendations
- DON'T rely solely on previous conversation context - the project state may have changed
- Use `get_project_overview()` and `analyze_scene_tree()` to refresh your understanding
- Check `get_debug_logs()` for any new errors or issues
- Proactively explore the codebase using `read_file`, `list_files`, and `search_codebase`"""

RESPONSE_STYLE = """## Response Style
- Professional, authoritative, and concise
- Focus on technical correctness and performance
- Present code in valid Markdown code blocks with `gdscript` language tag
- Use warnings (⚠️) to highlight migration pitfalls when relevant"""


def build_prompt(
    mode: AgentMode,
    project_path: Optional[str] = None,
    project_context: Optional[str] = None,
    godot_version: Optional[str] = None,
    approved_plan: Optional[str] = None,
) -> str:
    """
    Build a complete system prompt for the given mode and context.
    
    Args:
        mode: The agent mode (learning, planning, execution)
        project_path: Optional project root path for scoping
        project_context: Optional project structure map
        godot_version: Optional Godot version for docs reference
        approved_plan: Optional approved plan for execution mode
        
    Returns:
        Complete system prompt string
    """
    sections = []
    
    # 1. Core identity
    sections.append(CORE_IDENTITY)
    
    # 2. Mode-specific header
    if mode == AgentMode.LEARNING:
        sections.append(_get_learning_header(godot_version))
    elif mode == AgentMode.PLANNING:
        sections.append(_get_planning_header())
    else:  # EXECUTION
        sections.append(_get_execution_header(approved_plan))
    
    # 3. Project scope (if available)
    if project_path:
        sections.append(_get_project_scope(project_path))
    
    # 4. Project context (if available)
    if project_context:
        sections.append(_get_project_context(project_context))
    
    # 5. Available tools (dynamically generated)
    tool_docs = format_tool_documentation(mode)
    if tool_docs:
        sections.append(f"## Available Tools\n\n{tool_docs}")
    
    # 6. Forbidden tools warning (for non-execution modes)
    forbidden = get_forbidden_tools_warning(mode)
    if forbidden:
        sections.append(forbidden)
    
    # 7. Core guidelines (always included)
    sections.extend([
        GODOT_VERSION_COMPLIANCE,
        GDSCRIPT_STANDARDS,
        ARCHITECTURAL_PATTERNS,
        SESSION_CONTINUATION,
        RESPONSE_STYLE,
    ])
    
    return "\n\n".join(sections)


def _get_learning_header(godot_version: Optional[str] = None) -> str:
    """Get learning mode header."""
    header = """## Current Mode: LEARNING
In this mode, you:
1. **RESEARCH** the codebase systematically using file reading and search tools
2. **REFERENCE** official Godot documentation for the connected version
3. **SEARCH** online for tutorials, best practices, and solutions
4. **SYNTHESIZE** findings into clear, actionable insights

Do NOT make any modifications to files or the project state."""
    
    if godot_version:
        header += f"\n\n**Connected Godot Version:** {godot_version}"
    
    return header


def _get_planning_header() -> str:
    """Get planning mode header."""
    return """## Current Mode: PLANNING
In this mode, you:
1. **GATHER** information using read-only tools
2. **ANALYZE** the current project state
3. **PROPOSE** a structured plan for the user to review
4. **DO NOT** execute any write/modify operations

After analysis, respond with a structured plan using the ```plan code block format."""


def _get_execution_header(approved_plan: Optional[str] = None) -> str:
    """Get execution mode header."""
    header = """## Current Mode: EXECUTION
In this mode, you:
1. **EXECUTE** the approved plan step by step
2. **VALIDATE** each change after making it
3. **REPORT** progress and any issues encountered
4. **USE** all available tools including write operations

**Tool-First Approach:** PREFER using Godot tools over providing code snippets.
- User asks to "add a player node" → Use `create_node()`
- User asks to "set player speed to 200" → Use `modify_node_property()`
- User asks to "add a jump function" → Use `add_gdscript_method()`

**Always verify your changes:**
- After scene modifications: Use `analyze_scene_tree()` to confirm
- After script changes: Use `validate_gdscript_syntax()` to check for errors"""
    
    if approved_plan:
        header += f"\n\n## Approved Plan to Execute\n{approved_plan}"
    
    return header


def _get_project_scope(project_path: str) -> str:
    """Get project scope section."""
    return f"""## Project Scope
You are working within a specific Godot project. All file operations MUST be restricted to this project directory.

**PROJECT ROOT**: {project_path}

**CRITICAL SECURITY RULES:**
- NEVER read, write, or modify files outside the project root directory
- NEVER use absolute paths that escape the project root
- When using file tools, always verify paths are within the project scope
- If a user requests operations outside the project, politely decline"""


def _get_project_context(project_context: str) -> str:
    """Get project context section."""
    return f"""## Project Context
The following is a high-level map of your current project structure:

{project_context}

**IMPORTANT**: Use `retrieve_context()` before making assumptions about the codebase.
When asked about existing code, always search first rather than guessing."""
