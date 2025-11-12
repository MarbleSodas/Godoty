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

/// Get all available MCP tool definitions
pub fn get_mcp_tool_definitions() -> Vec<ToolDefinition> {
    vec![
        // Desktop Commander tools
        create_read_file_tool(),
        create_write_file_tool(),
        create_edit_block_tool(),
        create_list_directory_tool(),
        create_create_directory_tool(),
        create_move_file_tool(),
        create_get_file_info_tool(),
        create_start_search_tool(),
        create_get_more_search_results_tool(),
        create_stop_search_tool(),
        // Context7 tool
        create_fetch_documentation_tool(),
    ]
}

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
                    "old_text": {
                        "type": "string",
                        "description": "The exact text to find and replace"
                    },
                    "new_text": {
                        "type": "string",
                        "description": "The new text to replace with"
                    }
                },
                "required": ["path", "old_text", "new_text"]
            }),
        },
    }
}

fn create_list_directory_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "list_directory".to_string(),
            description: "List files and directories in a given path".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the directory relative to project root"
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
            description: "Create a new directory in the project".to_string(),
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
            description: "Get metadata about a file (size, modified time, etc.)".to_string(),
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
            description: "Start a search for files or content in the project".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "path": {
                        "type": "string",
                        "description": "Optional path to limit search scope"
                    }
                },
                "required": ["query"]
            }),
        },
    }
}

fn create_get_more_search_results_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "get_more_search_results".to_string(),
            description: "Get more results from an ongoing search".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {},
                "required": []
            }),
        },
    }
}

fn create_stop_search_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "stop_search".to_string(),
            description: "Stop an ongoing search".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {},
                "required": []
            }),
        },
    }
}

fn create_fetch_documentation_tool() -> ToolDefinition {
    ToolDefinition {
        tool_type: "function".to_string(),
        function: FunctionDefinition {
            name: "fetch_documentation".to_string(),
            description: "Fetch Godot documentation for a specific topic or class using Context7".to_string(),
            parameters: json!({
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The topic or class name to fetch documentation for (e.g., 'CharacterBody2D', 'signals', 'Node2D')"
                    }
                },
                "required": ["topic"]
            }),
        },
    }
}

