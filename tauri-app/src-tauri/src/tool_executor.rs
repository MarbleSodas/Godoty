use crate::mcp_client::McpClientManager;
use crate::mcp_tools::{ToolCall, get_tools_for_agent};
use anyhow::{anyhow, Result};
use serde_json::Value;
use tracing::{debug, info, warn};

/// Executes tool calls by dispatching to appropriate MCP servers or HTTP endpoints
pub struct ToolExecutor {
    #[allow(dead_code)] // API key reserved for future HTTP tool integrations
    api_key: String,
}

/// Agent types for tool filtering
#[derive(Debug, Clone)]
pub enum AgentType {
    Orchestrator,
    #[allow(dead_code)] // Used by PlanningAgent for tool filtering
    Planning,
}

impl AgentType {
    pub fn as_str(&self) -> &'static str {
        match self {
            AgentType::Orchestrator => "orchestrator",
            AgentType::Planning => "planning",
        }
    }
}

impl ToolExecutor {
    pub fn new(api_key: String) -> Self {
        Self { api_key }
    }

    /// Get available tools for a specific agent type
    pub fn get_tools_for_agent(&self, agent_type: AgentType) -> Vec<crate::mcp_tools::ToolDefinition> {
        get_tools_for_agent(agent_type.as_str())
    }

    /// Execute a tool call and return the result as a JSON value
    pub async fn execute_tool(
        &self,
        tool_call: &ToolCall,
        mcp_client: &mut Option<McpClientManager>,
        agent_type: Option<AgentType>,
    ) -> Result<Value> {
        let function_name = &tool_call.function.name;
        let args: Value = serde_json::from_str(&tool_call.function.arguments)
            .map_err(|e| anyhow!("Failed to parse tool arguments: {}", e))?;

        debug!(
            tool_name = %function_name,
            tool_call_id = %tool_call.id,
            agent_type = ?agent_type,
            args = %args,
            "Executing tool call"
        );

        // Check if the agent is allowed to use this tool
        if let Some(agent) = agent_type {
            let available_tools = self.get_tools_for_agent(agent.clone());
            let tool_allowed = available_tools.iter().any(|tool| tool.function.name == *function_name);

            if !tool_allowed {
                warn!(
                    tool_name = %function_name,
                    agent_type = %agent.as_str(),
                    "Agent attempted to use unauthorized tool"
                );
                return Err(anyhow!(
                    "Agent '{}' is not authorized to use tool '{}'",
                    agent.as_str(),
                    function_name
                ));
            }
        }

        // Dispatch to appropriate handler based on tool name
        match function_name.as_str() {
            // Context7 enhanced documentation tools
            "resolve_library_id" | "get_library_docs" => {
                self.execute_context7_tool(function_name, args, mcp_client).await
            }
            // Sequential thinking tools
            "sequentialthinking" | "brainstorm" | "reflect" => {
                self.execute_sequential_thinking_tool(function_name, args, mcp_client).await
            }
            // All other tools - dispatch to appropriate MCP server
            _ => {
                self.execute_mcp_tool(function_name, args, mcp_client).await
            }
        }
    }

    /// Execute a general MCP tool with automatic server routing
    async fn execute_mcp_tool(
        &self,
        tool_name: &str,
        args: Value,
        mcp_client: &mut Option<McpClientManager>,
    ) -> Result<Value> {
        let client = mcp_client
            .as_mut()
            .ok_or_else(|| anyhow!("MCP client manager not initialized"))?;

        // Validate paths for security (only applies to desktop-commander tools)
        if tool_name.contains("read") || tool_name.contains("write") || tool_name.contains("file") ||
           tool_name.contains("search") || tool_name.contains("list") || tool_name.contains("move") ||
           tool_name.contains("copy") || tool_name.contains("delete") || tool_name.contains("edit") {
            client.validate_paths_within_root(&args)?;
        }

        let result = client.call_tool(tool_name, args).await?;

        debug!(
            tool_name = %tool_name,
            result_preview = %serde_json::to_string(&result).unwrap_or_default().chars().take(200).collect::<String>(),
            "MCP tool executed successfully"
        );

        Ok(result)
    }

    /// Execute Context7 enhanced documentation tools
    async fn execute_context7_tool(
        &self,
        tool_name: &str,
        args: Value,
        mcp_client: &mut Option<McpClientManager>,
    ) -> Result<Value> {
        let client = mcp_client
            .as_mut()
            .ok_or_else(|| anyhow!("MCP client manager not initialized"))?;

        debug!(
            tool_name = %tool_name,
            "Executing Context7 tool"
        );

        let result = client.call_tool(tool_name, args).await?;

        debug!(
            tool_name = %tool_name,
            "Context7 tool executed successfully"
        );

        Ok(result)
    }

    /// Execute Sequential Thinking tools
    async fn execute_sequential_thinking_tool(
        &self,
        tool_name: &str,
        args: Value,
        mcp_client: &mut Option<McpClientManager>,
    ) -> Result<Value> {
        let client = mcp_client
            .as_mut()
            .ok_or_else(|| anyhow!("MCP client manager not initialized"))?;

        debug!(
            tool_name = %tool_name,
            "Executing Sequential Thinking tool"
        );

        let result = client.call_tool(tool_name, args).await?;

        debug!(
            tool_name = %tool_name,
            "Sequential Thinking tool executed successfully"
        );

        Ok(result)
    }

    /// Execute multiple tool calls in parallel (sequentially for now due to mutable client)
    pub async fn execute_tools_parallel(
        &self,
        tool_calls: &[ToolCall],
        mcp_client: &mut Option<McpClientManager>,
        agent_type: Option<AgentType>,
    ) -> Vec<(String, Result<Value>)> {
        let mut results = Vec::new();

        info!(
            tool_count = tool_calls.len(),
            agent_type = ?agent_type,
            "Executing tools in sequence (parallel execution planned for future)"
        );

        // Note: For now, we execute sequentially because mcp_client is mutable
        // In the future, we could use Arc<Mutex<McpClientManager>> for parallel execution
        for tool_call in tool_calls {
            let result = self.execute_tool(tool_call, mcp_client, agent_type.clone()).await;
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

