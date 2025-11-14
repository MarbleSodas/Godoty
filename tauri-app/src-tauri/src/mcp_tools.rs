use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

/// Tool definition for OpenRouter API
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolDefinition {
    #[serde(rename = "type")]
    pub tool_type: String,
    pub function: FunctionDefinition,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FunctionDefinition {
    pub name: String,
    pub description: String,
    pub parameters: Value,
}

/// Tool call from LLM response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCall {
    pub id: String,
    #[serde(rename = "type")]
    pub call_type: String,
    pub function: FunctionCall,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FunctionCall {
    pub name: String,
    pub arguments: String, // JSON string
}

/// Tool categories for organization and filtering
#[derive(Debug, Clone, PartialEq)]
pub enum ToolCategory {
    FileSystem,
    Search,
    ProcessManagement,
    SequentialThinking,
    Documentation,
    #[allow(dead_code)] // Reserved for future tool categories
    Analysis,
    #[allow(dead_code)] // Reserved for future tool categories
    Communication,
}

impl ToolCategory {
    pub fn as_str(&self) -> &'static str {
        match self {
            ToolCategory::FileSystem => "file_system",
            ToolCategory::Search => "search",
            ToolCategory::ProcessManagement => "process_management",
            ToolCategory::SequentialThinking => "sequential_thinking",
            ToolCategory::Documentation => "documentation",
            ToolCategory::Analysis => "analysis",
            ToolCategory::Communication => "communication",
        }
    }
}

/// Enhanced tool definition with category
#[derive(Debug, Clone)]
pub struct EnhancedToolDefinition {
    pub definition: ToolDefinition,
    #[allow(dead_code)] // Category used for tool organization
    pub category: ToolCategory,
    #[allow(dead_code)] // Server ID used for routing
    pub server_id: String,
    #[allow(dead_code)] // Access control for agents
    pub allowed_agents: Vec<String>, // Which agents can use this tool
}

/// Get all available MCP tool definitions enhanced with categorization
pub fn get_enhanced_mcp_tool_definitions() -> Vec<EnhancedToolDefinition> {
    let mut tools = Vec::new();

    // Desktop Commander - File Operations
    tools.push(EnhancedToolDefinition {
        definition: create_read_file_tool(),
        category: ToolCategory::FileSystem,
        server_id: "desktop-commander".to_string(),
        allowed_agents: vec!["orchestrator".to_string(), "research".to_string()],
    });

    tools.push(EnhancedToolDefinition {
        definition: create_write_file_tool(),
        category: ToolCategory::FileSystem,
        server_id: "desktop-commander".to_string(),
        allowed_agents: vec!["orchestrator".to_string()], // Write-only for orchestrator
    });

    tools.push(EnhancedToolDefinition {
        definition: create_edit_block_tool(),
        category: ToolCategory::FileSystem,
        server_id: "desktop-commander".to_string(),
        allowed_agents: vec!["orchestrator".to_string()],
    });

    tools.push(EnhancedToolDefinition {
        definition: create_list_directory_tool(),
        category: ToolCategory::FileSystem,
        server_id: "desktop-commander".to_string(),
        allowed_agents: vec!["orchestrator".to_string(), "research".to_string()],
    });

    tools.push(EnhancedToolDefinition {
        definition: create_create_directory_tool(),
        category: ToolCategory::FileSystem,
        server_id: "desktop-commander".to_string(),
        allowed_agents: vec!["orchestrator".to_string()],
    });

    tools.push(EnhancedToolDefinition {
        definition: create_move_file_tool(),
        category: ToolCategory::FileSystem,
        server_id: "desktop-commander".to_string(),
        allowed_agents: vec!["orchestrator".to_string()],
    });

    tools.push(EnhancedToolDefinition {
        definition: create_get_file_info_tool(),
        category: ToolCategory::FileSystem,
        server_id: "desktop-commander".to_string(),
        allowed_agents: vec!["orchestrator".to_string(), "research".to_string()],
    });

    tools.push(EnhancedToolDefinition {
        definition: create_read_multiple_files_tool(),
        category: ToolCategory::FileSystem,
        server_id: "desktop-commander".to_string(),
        allowed_agents: vec!["orchestrator".to_string(), "research".to_string()],
    });

    // Desktop Commander - Search Operations
    tools.push(EnhancedToolDefinition {
        definition: create_start_search_tool(),
        category: ToolCategory::Search,
        server_id: "desktop-commander".to_string(),
        allowed_agents: vec!["orchestrator".to_string(), "research".to_string()],
    });

    tools.push(EnhancedToolDefinition {
        definition: create_get_more_search_results_tool(),
        category: ToolCategory::Search,
        server_id: "desktop-commander".to_string(),
        allowed_agents: vec!["orchestrator".to_string(), "research".to_string()],
    });

    tools.push(EnhancedToolDefinition {
        definition: create_stop_search_tool(),
        category: ToolCategory::Search,
        server_id: "desktop-commander".to_string(),
        allowed_agents: vec!["orchestrator".to_string(), "research".to_string()],
    });

    // Desktop Commander - Process Management
    tools.push(EnhancedToolDefinition {
        definition: create_start_process_tool(),
        category: ToolCategory::ProcessManagement,
        server_id: "desktop-commander".to_string(),
        allowed_agents: vec!["orchestrator".to_string()],
    });

    tools.push(EnhancedToolDefinition {
        definition: create_read_process_tool(),
        category: ToolCategory::ProcessManagement,
        server_id: "desktop-commander".to_string(),
        allowed_agents: vec!["orchestrator".to_string()],
    });

    tools.push(EnhancedToolDefinition {
        definition: create_interact_with_process_tool(),
        category: ToolCategory::ProcessManagement,
        server_id: "desktop-commander".to_string(),
        allowed_agents: vec!["orchestrator".to_string()],
    });

    tools.push(EnhancedToolDefinition {
        definition: create_list_processes_tool(),
        category: ToolCategory::ProcessManagement,
        server_id: "desktop-commander".to_string(),
        allowed_agents: vec!["orchestrator".to_string()],
    });

    tools.push(EnhancedToolDefinition {
        definition: create_kill_process_tool(),
        category: ToolCategory::ProcessManagement,
        server_id: "desktop-commander".to_string(),
        allowed_agents: vec!["orchestrator".to_string()],
    });

    // Sequential Thinking Tools
    tools.push(EnhancedToolDefinition {
        definition: create_sequential_thinking_tool(),
        category: ToolCategory::SequentialThinking,
        server_id: "sequential-thinking".to_string(),
        allowed_agents: vec!["orchestrator".to_string(), "research".to_string()],
    });

    tools.push(EnhancedToolDefinition {
        definition: create_brainstorm_tool(),
        category: ToolCategory::SequentialThinking,
        server_id: "sequential-thinking".to_string(),
        allowed_agents: vec!["orchestrator".to_string(), "research".to_string()],
    });

    tools.push(EnhancedToolDefinition {
        definition: create_reflect_tool(),
        category: ToolCategory::SequentialThinking,
        server_id: "sequential-thinking".to_string(),
        allowed_agents: vec!["orchestrator".to_string(), "research".to_string()],
    });

    // Context7 Enhanced Documentation Tools
    tools.push(EnhancedToolDefinition {
        definition: create_resolve_library_id_tool(),
        category: ToolCategory::Documentation,
        server_id: "context7".to_string(),
        allowed_agents: vec!["orchestrator".to_string(), "research".to_string()],
    });

    tools.push(EnhancedToolDefinition {
        definition: create_get_library_docs_tool(),
        category: ToolCategory::Documentation,
        server_id: "context7".to_string(),
        allowed_agents: vec!["orchestrator".to_string(), "research".to_string()],
    });

    // Enhanced legacy documentation tool (now uses context7)
    tools.push(EnhancedToolDefinition {
        definition: create_fetch_documentation_tool(),
        category: ToolCategory::Documentation,
        server_id: "context7".to_string(),
        allowed_agents: vec!["orchestrator".to_string(), "research".to_string()],
    });

    tools
}

/// Get tool definitions for a specific agent type
pub fn get_tools_for_agent(agent_type: &str) -> Vec<ToolDefinition> {
    get_enhanced_mcp_tool_definitions()
        .into_iter()
        .filter(|tool| tool.allowed_agents.contains(&agent_type.to_string()))
        .map(|tool| tool.definition)
        .collect()
}

/// Get tool definitions by category
#[allow(dead_code)] // Used for future category-based tool filtering
pub fn get_tools_by_category(category: ToolCategory) -> Vec<EnhancedToolDefinition> {
    get_enhanced_mcp_tool_definitions()
        .into_iter()
        .filter(|tool| tool.category == category)
        .collect()
}

/// Legacy function for backward compatibility
#[allow(dead_code)] // Available for legacy compatibility
pub fn get_mcp_tool_definitions() -> Vec<ToolDefinition> {
    get_enhanced_mcp_tool_definitions()
        .into_iter()
        .map(|tool| tool.definition)
        .collect()
}

// Desktop Commander Tool Definitions

fn create_read_file_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "read_file".to_string(),
            description: "Read the contents of a file from the project directory".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file relative to project root"
                    },
                    "offset": {
                        "type": "number",
                        "description": "Optional line offset to start reading from"
                    },
                    "length": {
                        "type": "number",
                        "description": "Optional number of lines to read"
                    }
                },
                "required": ["path"]
            }),
        },
    }
}

fn create_write_file_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "write_file".to_string(),
            description: "Write content to a file in the project directory. Creates the file if it doesn't exist.".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file relative to project root"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["rewrite", "append"],
                        "default": "rewrite",
                        "description": "Whether to overwrite or append to the file"
                    }
                },
                "required": ["path", "content"]
            }),
        },
    }
}

fn create_edit_block_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "edit_block".to_string(),
            description: "Make surgical edits to an existing file by replacing a specific block of text".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file relative to project root"
                    },
                    "old_string": {
                        "type": "string",
                        "description": "The exact text to find and replace"
                    },
                    "new_string": {
                        "type": "string",
                        "description": "The new text to replace with"
                    }
                },
                "required": ["path", "old_string", "new_string"]
            }),
        },
    }
}

fn create_list_directory_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "list_directory".to_string(),
            description: "List files and directories in a given path with detailed information".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the directory relative to project root"
                    },
                    "depth": {
                        "type": "number",
                        "default": 2,
                        "description": "Directory depth to explore (1-5)"
                    }
                },
                "required": ["path"]
            }),
        },
    }
}

fn create_create_directory_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "create_directory".to_string(),
            description: "Create a new directory in the project (supports nested paths)".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the directory to create relative to project root"
                    }
                },
                "required": ["path"]
            }),
        },
    }
}

fn create_move_file_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "move_file".to_string(),
            description: "Move or rename a file in the project".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Source path relative to project root"
                    },
                    "destination": {
                        "type": "string",
                        "description": "Destination path relative to project root"
                    }
                },
                "required": ["source", "destination"]
            }),
        },
    }
}

fn create_get_file_info_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "get_file_info".to_string(),
            description: "Get detailed metadata about a file (size, modified time, line count, etc.)".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file relative to project root"
                    }
                },
                "required": ["path"]
            }),
        },
    }
}

fn create_start_search_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "start_search".to_string(),
            description: "Start a streaming search for files or content in the project with advanced options".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to search in"
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Search pattern or query"
                    },
                    "search_type": {
                        "type": "string",
                        "enum": ["files", "content"],
                        "default": "files",
                        "description": "Search for file names or content within files"
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "File pattern filter (e.g., '*.ts', 'package.json')"
                    },
                    "ignore_case": {
                        "type": "boolean",
                        "default": true,
                        "description": "Case-insensitive search"
                    },
                    "max_results": {
                        "type": "number",
                        "description": "Maximum number of results to return"
                    }
                },
                "required": ["path", "pattern"]
            }),
        },
    }
}

fn create_get_more_search_results_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "get_more_search_results".to_string(),
            description: "Get more results from an ongoing streaming search".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Search session ID from previous start_search call"
                    },
                    "offset": {
                        "type": "number",
                        "default": 0,
                        "description": "Result offset for pagination"
                    },
                    "length": {
                        "type": "number",
                        "default": 100,
                        "description": "Number of results to return"
                    }
                },
                "required": ["session_id"]
            }),
        },
    }
}

fn create_stop_search_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "stop_search".to_string(),
            description: "Stop an ongoing streaming search session".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Search session ID to stop"
                    }
                },
                "required": ["session_id"]
            }),
        },
    }
}

fn create_read_multiple_files_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "read_multiple_files".to_string(),
            description: "Read the contents of multiple files simultaneously for efficient analysis".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "Array of file paths relative to project root"
                    }
                },
                "required": ["paths"]
            }),
        },
    }
}

fn create_start_process_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "start_process".to_string(),
            description: "Start a new process/command with intelligent state detection. Primary tool for running scripts, commands, or starting interactive processes like Python REPL.".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute"
                    },
                    "timeout_ms": {
                        "type": "number",
                        "default": 30000,
                        "description": "Maximum time to wait for command completion in milliseconds"
                    },
                    "shell": {
                        "type": "string",
                        "description": "Optional shell to use (e.g., 'powershell', 'cmd', 'bash')"
                    },
                    "verbose_timing": {
                        "type": "boolean",
                        "default": false,
                        "description": "Enable detailed timing information for debugging"
                    }
                },
                "required": ["command"]
            }),
        },
    }
}

fn create_read_process_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "read_process".to_string(),
            description: "Read output from a running process with intelligent completion detection".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "pid": {
                        "type": "number",
                        "description": "Process ID to read from"
                    },
                    "timeout_ms": {
                        "type": "number",
                        "description": "Maximum time to wait in milliseconds"
                    },
                    "verbose_timing": {
                        "type": "boolean",
                        "default": false,
                        "description": "Enable detailed timing information"
                    }
                },
                "required": ["pid"]
            }),
        },
    }
}

fn create_interact_with_process_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "interact_with_process".to_string(),
            description: "Send input to a running process and receive response. Primary tool for running scripts and interactive commands.".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "pid": {
                        "type": "number",
                        "description": "Process ID to interact with"
                    },
                    "input": {
                        "type": "string",
                        "description": "Input text to send to the process"
                    },
                    "timeout_ms": {
                        "type": "number",
                        "default": 8000,
                        "description": "Maximum time to wait for response in milliseconds"
                    },
                    "wait_for_prompt": {
                        "type": "boolean",
                        "default": true,
                        "description": "Wait for process prompt before returning"
                    },
                    "verbose_timing": {
                        "type": "boolean",
                        "default": false,
                        "description": "Enable detailed timing information"
                    }
                },
                "required": ["pid", "input"]
            }),
        },
    }
}

fn create_list_processes_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "list_processes".to_string(),
            description: "List all active terminal sessions/processes started by this agent".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {},
                "required": []
            }),
        },
    }
}

fn create_kill_process_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "kill_process".to_string(),
            description: "Force terminate a running process by PID".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "pid": {
                        "type": "number",
                        "description": "Process ID to terminate"
                    }
                },
                "required": ["pid"]
            }),
        },
    }
}

// Sequential Thinking Tool Definitions

fn create_sequential_thinking_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "sequentialthinking".to_string(),
            description: "A detailed tool for dynamic and reflective problem-solving through thoughts. Each thought can build on, question, or revise previous insights as understanding deepens.".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "thought": {
                        "type": "string",
                        "description": "Your current thinking step"
                    },
                    "next_thought_needed": {
                        "type": "boolean",
                        "description": "Whether another thought step is needed"
                    },
                    "thought_number": {
                        "type": "number",
                        "minimum": 1,
                        "description": "Current thought number in sequence"
                    },
                    "total_thoughts": {
                        "type": "number",
                        "minimum": 1,
                        "description": "Estimated total thoughts needed"
                    },
                    "is_revision": {
                        "type": "boolean",
                        "description": "Whether this thought revises previous thinking"
                    },
                    "revises_thought": {
                        "type": "number",
                        "description": "Which thought number is being reconsidered (if is_revision is true)"
                    },
                    "branch_from_thought": {
                        "type": "number",
                        "description": "Branching point thought number (if branching)"
                    }
                },
                "required": ["thought", "next_thought_needed", "thought_number", "total_thoughts"]
            }),
        },
    }
}

fn create_brainstorm_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "brainstorm".to_string(),
            description: "Generate novel ideas with dynamic context gathering. Supports various creative frameworks including SCAMPER, Design Thinking, and lateral thinking.".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Primary brainstorming challenge or question to explore"
                    },
                    "methodology": {
                        "type": "string",
                        "enum": ["divergent", "convergent", "scamper", "design-thinking", "lateral", "auto"],
                        "default": "auto",
                        "description": "Brainstorming framework to use"
                    },
                    "domain": {
                        "type": "string",
                        "description": "Domain context for specialized brainstorming"
                    },
                    "constraints": {
                        "type": "string",
                        "description": "Known limitations, requirements, or boundaries"
                    },
                    "existing_context": {
                        "type": "string",
                        "description": "Background information or previous attempts"
                    },
                    "idea_count": {
                        "type": "number",
                        "default": 12,
                        "minimum": 1,
                        "description": "Target number of ideas to generate"
                    },
                    "include_analysis": {
                        "type": "boolean",
                        "default": true,
                        "description": "Include feasibility and impact analysis"
                    }
                },
                "required": ["prompt"]
            }),
        },
    }
}

fn create_reflect_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "reflect".to_string(),
            description: "Reflect on previous actions, decisions, or outcomes to gain insights and improve future approaches.".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "What to reflect on (action, decision, outcome, process)"
                    },
                    "context": {
                        "type": "string",
                        "description": "Context or background information"
                    },
                    "successes": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "What went well or succeeded"
                    },
                    "challenges": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "What was challenging or didn't work"
                    },
                    "learnings": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "Key insights or lessons learned"
                    },
                    "future_actions": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "Recommended actions for future scenarios"
                    }
                },
                "required": ["subject"]
            }),
        },
    }
}

// Context7 Enhanced Documentation Tools

fn create_resolve_library_id_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "resolve_library_id".to_string(),
            description: "Resolves a package/product name to a Context7-compatible library ID and returns a list of matching libraries.".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "libraryName": {
                        "type": "string",
                        "description": "Library name to search for and retrieve a Context7-compatible library ID"
                    }
                },
                "required": ["libraryName"]
            }),
        },
    }
}

fn create_get_library_docs_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "get_library_docs".to_string(),
            description: "Fetches up-to-date documentation for a library using its Context7-compatible library ID.".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "context7CompatibleLibraryID": {
                        "type": "string",
                        "description": "Exact Context7-compatible library ID (e.g., '/mongodb/docs', '/vercel/next.js')"
                    },
                    "topic": {
                        "type": "string",
                        "description": "Optional topic to focus documentation on (e.g., 'hooks', 'routing')"
                    },
                    "tokens": {
                        "type": "number",
                        "default": 5000,
                        "description": "Maximum number of tokens of documentation to retrieve"
                    }
                },
                "required": ["context7CompatibleLibraryID"]
            }),
        },
    }
}

fn create_fetch_documentation_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "fetch_documentation".to_string(),
            description: "Fetch comprehensive documentation using Context7 for a specific topic, library, or framework. Automatically resolves library names and fetches relevant documentation.".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The topic, library name, or framework to fetch documentation for (e.g., 'Godot', 'React', 'CharacterBody2D')"
                    },
                    "tokens": {
                        "type": "number",
                        "default": 5000,
                        "description": "Maximum number of tokens of documentation to retrieve"
                    }
                },
                "required": ["topic"]
            }),
        },
    }
}