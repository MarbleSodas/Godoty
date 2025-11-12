use crate::mcp_client::McpClient;
use crate::mcp_tools::ToolCall;
use crate::context_engine::ContextEngine;
use anyhow::{anyhow, Result};
use serde_json::{json, Value};

/// Executes tool calls by dispatching to appropriate MCP servers or HTTP endpoints
pub struct ToolExecutor {
    api_key: String,
}

impl ToolExecutor {
    pub fn new(api_key: String) -> Self {
        Self { api_key }
    }

    /// Execute a tool call and return the result as a JSON value
    pub async fn execute_tool(
        &self,
        tool_call: &ToolCall,
        mcp_client: &mut Option<McpClient>,
    ) -> Result<Value> {
        let function_name = &tool_call.function.name;
        let args: Value = serde_json::from_str(&tool_call.function.arguments)
            .map_err(|e| anyhow!("Failed to parse tool arguments: {}", e))?;

        tracing::debug!(
            tool_name = %function_name,
            tool_call_id = %tool_call.id,
            args = %args,
            "Executing tool call"
        );

        match function_name.as_str() {
            // Desktop Commander MCP tools - File Operations
            "read_file" | "write_file" | "edit_block" | "list_directory"
            | "create_directory" | "move_file" | "get_file_info"
            | "read_multiple_files" => {
                self.execute_desktop_commander_tool(function_name, args, mcp_client).await
            }
            // Desktop Commander MCP tools - Search Operations
            "start_search" | "get_more_search_results" | "stop_search" => {
                self.execute_desktop_commander_tool(function_name, args, mcp_client).await
            }
            // Desktop Commander MCP tools - Process Management
            "start_process" | "read_process" | "interact_with_process"
            | "list_processes" | "kill_process" => {
                self.execute_desktop_commander_tool(function_name, args, mcp_client).await
            }
            // Context7 HTTP tool
            "fetch_documentation" => {
                self.execute_fetch_documentation(args).await
            }
            _ => Err(anyhow!("Unknown tool: {}", function_name)),
        }
    }

    /// Execute a Desktop Commander MCP tool
    async fn execute_desktop_commander_tool(
        &self,
        tool_name: &str,
        args: Value,
        mcp_client: &mut Option<McpClient>,
    ) -> Result<Value> {
        let client = mcp_client
            .as_mut()
            .ok_or_else(|| anyhow!("Desktop Commander MCP client not initialized"))?;

        let result = client.call_tool(tool_name, args).await?;
        
        tracing::debug!(
            tool_name = %tool_name,
            result_preview = %serde_json::to_string(&result).unwrap_or_default().chars().take(200).collect::<String>(),
            "Desktop Commander tool executed successfully"
        );

        Ok(result)
    }

    /// Execute the fetch_documentation tool using Context7
    async fn execute_fetch_documentation(&self, args: Value) -> Result<Value> {
        let topic = args
            .get("topic")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow!("Missing 'topic' parameter for fetch_documentation"))?;

        tracing::debug!(
            topic = %topic,
            "Fetching documentation from Context7"
        );

        let ctx_engine = ContextEngine::new(&self.api_key);
        let docs = ctx_engine.fetch_from_context7(topic).await?;

        tracing::debug!(
            topic = %topic,
            docs_length = docs.len(),
            "Documentation fetched successfully"
        );

        Ok(json!({
            "topic": topic,
            "documentation": docs,
            "length": docs.len()
        }))
    }

    /// Execute multiple tool calls in parallel
    pub async fn execute_tools_parallel(
        &self,
        tool_calls: &[ToolCall],
        mcp_client: &mut Option<McpClient>,
    ) -> Vec<(String, Result<Value>)> {
        let mut results = Vec::new();
        
        // Note: For now, we execute sequentially because mcp_client is mutable
        // In the future, we could use Arc<Mutex<McpClient>> for parallel execution
        for tool_call in tool_calls {
            let result = self.execute_tool(tool_call, mcp_client).await;
            results.push((tool_call.id.clone(), result));
        }
        
        results
    }
}

/// Format tool execution results as messages for the LLM
pub fn format_tool_results_as_messages(
    results: Vec<(String, Result<Value>)>,
) -> Vec<crate::llm_client::ChatMessageWithTools> {
    results
        .into_iter()
        .map(|(tool_call_id, result)| {
            let content = match result {
                Ok(value) => serde_json::to_string_pretty(&value).unwrap_or_else(|_| value.to_string()),
                Err(e) => format!("Error: {}", e),
            };

            crate::llm_client::ChatMessageWithTools {
                role: "tool".to_string(),
                content,
                tool_calls: None,
                tool_call_id: Some(tool_call_id),
            }
        })
        .collect()
}

