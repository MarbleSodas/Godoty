use crate::mcp_tools::{
    get_enhanced_mcp_tool_definitions, EnhancedToolDefinition, ToolCategory, ToolDefinition
};
use crate::mcp_client::McpClientManager;
use crate::llm_config::AgentType;
use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::{Mutex, RwLock};

/// Centralized tool registry for managing access to all MCP tools
pub struct ToolRegistry {
    /// All available tools with metadata
    available_tools: HashMap<String, RegisteredTool>,

    /// Agent-specific tool permissions
    agent_permissions: HashMap<AgentType, AgentPermissions>,

    /// Server mappings for tool routing
    server_mappings: HashMap<String, ServerId>,

    /// MCP client manager for executing tools
    mcp_manager: Option<Arc<Mutex<McpClientManager>>>,

    /// Registry statistics
    stats: Arc<RwLock<ToolRegistryStats>>,
}

/// Registered tool with metadata
#[derive(Debug, Clone)]
pub struct RegisteredTool {
    /// Tool definition
    pub definition: ToolDefinition,

    /// Tool category for organization
    pub category: ToolCategory,

    /// Server that provides this tool
    pub server_id: String,

    /// Access permissions by agent type
    pub access_permissions: HashMap<AgentType, ToolAccessLevel>,

    /// Tool metadata
    pub metadata: ToolMetadata,
}

/// Tool access levels for agents
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ToolAccessLevel {
    /// No access
    None,
    /// Read-only access (for file tools, search tools, etc.)
    ReadOnly,
    /// Full access including write/modify operations
    Full,
}

/// Tool metadata for advanced routing and optimization
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolMetadata {
    /// Estimated execution cost (0.0 to 1.0)
    pub cost_weight: f32,

    /// Whether tool modifies system state
    pub state_modifying: bool,

    /// Whether tool requires network access
    pub requires_network: bool,

    /// Estimated execution time in milliseconds
    pub estimated_time_ms: u64,

    /// Safety level (0.0 = safe, 1.0 = dangerous)
    pub safety_risk: f32,

    /// Dependencies on other tools
    pub dependencies: Vec<String>,

    /// Tool tags for filtering
    pub tags: Vec<String>,
}

/// Agent-specific permissions
#[derive(Debug, Clone)]
pub struct AgentPermissions {
    /// Maximum number of tools allowed per execution
    pub max_tools_per_execution: usize,

    /// Maximum total cost weight per execution
    pub max_cost_weight: f32,

    /// Restricted categories (empty = no restrictions)
    pub restricted_categories: Vec<ToolCategory>,

    /// Allowed tools (empty = use category-based permissions)
    pub allowed_tools: Vec<String>,

    /// Denied tools (takes precedence over allowed)
    pub denied_tools: Vec<String>,

    /// Whether to log tool usage for this agent
    pub log_usage: bool,
}

/// Server identifier for routing
#[derive(Debug, Clone, Hash, Eq, PartialEq, Serialize, Deserialize)]
pub enum ServerId {
    DesktopCommander,
    SequentialThinking,
    Context7,
}

/// Tool registry statistics
#[derive(Debug, Default, Clone)]
pub struct ToolRegistryStats {
    /// Total tool calls
    pub total_tool_calls: u64,

    /// Tool calls by agent type
    pub calls_by_agent: HashMap<AgentType, u64>,

    /// Tool calls by category
    pub calls_by_category: HashMap<ToolCategory, u64>,

    /// Failed tool calls
    pub failed_calls: u64,

    /// Average execution time
    pub avg_execution_time_ms: f64,

    /// Most used tools
    pub most_used_tools: Vec<(String, u64)>,
}

/// Tool execution result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolExecutionResult {
    /// Tool call that was executed
    pub tool_call: ExecutedToolCall,

    /// Success or failure
    pub success: bool,

    /// Result data if successful
    pub result: Option<Value>,

    /// Error message if failed
    pub error: Option<String>,

    /// Execution time in milliseconds
    pub execution_time_ms: u64,

    /// Cost incurred
    pub cost_weight: f32,

    /// Additional metadata
    pub metadata: HashMap<String, String>,
}

/// Executed tool call with results
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutedToolCall {
    /// Tool name
    pub tool_name: String,

    /// Arguments that were passed
    pub arguments: Value,

    /// Agent that executed the tool
    pub agent_type: AgentType,

    /// Timestamp of execution
    pub timestamp: chrono::DateTime<chrono::Utc>,

    /// Server that handled the call
    pub server_id: String,
}

impl ToolRegistry {
    /// Create a new tool registry
    pub fn new() -> Self {
        let mut registry = Self {
            available_tools: HashMap::new(),
            agent_permissions: HashMap::new(),
            server_mappings: HashMap::new(),
            mcp_manager: None,
            stats: Arc::new(RwLock::new(ToolRegistryStats::default())),
        };

        // Initialize with default tool definitions
        registry.initialize_tools();
        registry.setup_agent_permissions();

        registry
    }

    /// Create registry with MCP client manager
    pub fn with_mcp_manager(mcp_manager: Arc<Mutex<McpClientManager>>) -> Self {
        let mut registry = Self::new();
        registry.mcp_manager = Some(mcp_manager);
        registry
    }

    /// Initialize tools from existing MCP tool definitions
    fn initialize_tools(&mut self) {
        let enhanced_tools = get_enhanced_mcp_tool_definitions();

        for enhanced_tool in enhanced_tools {
            let metadata = self.create_tool_metadata(&enhanced_tool);
            let registered_tool = RegisteredTool {
                definition: enhanced_tool.definition,
                category: enhanced_tool.category.clone(),
                server_id: enhanced_tool.server_id.clone(),
                access_permissions: self.create_default_permissions(&enhanced_tool.category),
                metadata,
            };

            self.available_tools.insert(
                registered_tool.definition.function.name.clone(),
                registered_tool,
            );

            // Set up server mapping
            self.server_mappings.insert(
                enhanced_tool.server_id.clone(),
                self.map_server_name(&enhanced_tool.server_id),
            );
        }

        tracing::info!(
            tool_count = self.available_tools.len(),
            "Initialized tool registry with MCP tools"
        );
    }

    /// Set up default agent permissions
    fn setup_agent_permissions(&mut self) {
        // Planning Agent - read-only, focused on plan creation and analysis
        self.agent_permissions.insert(
            AgentType::Planning,
            AgentPermissions {
                max_tools_per_execution: 10,
                max_cost_weight: 0.7,
                restricted_categories: vec![ToolCategory::ProcessManagement],
                allowed_tools: vec![],
                denied_tools: vec![
                    "write_file".to_string(),
                    "edit_block".to_string(),
                    "create_directory".to_string(),
                    "move_file".to_string(),
                    "start_process".to_string(),
                    "interact_with_process".to_string(),
                    "kill_process".to_string(),
                ],
                log_usage: true,
            },
        );

        // Orchestrator Agent - full access for execution
        self.agent_permissions.insert(
            AgentType::Orchestrator,
            AgentPermissions {
                max_tools_per_execution: 25,
                max_cost_weight: 1.0,
                restricted_categories: vec![],
                allowed_tools: vec![],
                denied_tools: vec![],
                log_usage: true,
            },
        );
    }

    /// Create default permissions for a tool category
    fn create_default_permissions(&self, category: &ToolCategory) -> HashMap<AgentType, ToolAccessLevel> {
        let mut permissions = HashMap::new();

        match category {
            ToolCategory::FileSystem => {
                permissions.insert(AgentType::Planning, ToolAccessLevel::ReadOnly);
                permissions.insert(AgentType::Orchestrator, ToolAccessLevel::Full);
            }
            ToolCategory::Search => {
                permissions.insert(AgentType::Planning, ToolAccessLevel::Full);
                permissions.insert(AgentType::Orchestrator, ToolAccessLevel::Full);
            }
            ToolCategory::SequentialThinking => {
                permissions.insert(AgentType::Planning, ToolAccessLevel::Full);
                permissions.insert(AgentType::Orchestrator, ToolAccessLevel::Full);
            }
            ToolCategory::Documentation => {
                permissions.insert(AgentType::Planning, ToolAccessLevel::Full);
                permissions.insert(AgentType::Orchestrator, ToolAccessLevel::Full);
            }
            ToolCategory::ProcessManagement => {
                permissions.insert(AgentType::Planning, ToolAccessLevel::None);
                permissions.insert(AgentType::Orchestrator, ToolAccessLevel::Full);
            }
            _ => {
                permissions.insert(AgentType::Planning, ToolAccessLevel::ReadOnly);
                permissions.insert(AgentType::Orchestrator, ToolAccessLevel::Full);
            }
        }

        permissions
    }

    /// Create metadata for a tool
    fn create_tool_metadata(&self, enhanced_tool: &EnhancedToolDefinition) -> ToolMetadata {
        let (cost_weight, time_ms, safety_risk) = match enhanced_tool.category {
            ToolCategory::FileSystem => match enhanced_tool.definition.function.name.as_str() {
                "write_file" | "edit_block" | "move_file" => (0.8, 500, 0.4),
                "read_file" | "list_directory" | "get_file_info" => (0.2, 200, 0.1),
                _ => (0.4, 300, 0.2),
            },
            ToolCategory::Search => (0.3, 400, 0.1),
            ToolCategory::ProcessManagement => (0.9, 2000, 0.7),
            ToolCategory::SequentialThinking => (0.5, 1000, 0.1),
            ToolCategory::Documentation => (0.2, 300, 0.0),
            _ => (0.4, 500, 0.2),
        };

        let state_modifying = match enhanced_tool.category {
            ToolCategory::FileSystem => enhanced_tool.definition.function.name.contains("write")
                || enhanced_tool.definition.function.name.contains("edit")
                || enhanced_tool.definition.function.name.contains("create")
                || enhanced_tool.definition.function.name.contains("move")
                || enhanced_tool.definition.function.name.contains("delete"),
            ToolCategory::ProcessManagement => true,
            _ => false,
        };

        ToolMetadata {
            cost_weight,
            state_modifying,
            requires_network: matches!(enhanced_tool.category, ToolCategory::Documentation),
            estimated_time_ms: time_ms,
            safety_risk,
            dependencies: Vec::new(),
            tags: vec![enhanced_tool.category.as_str().to_string()],
        }
    }

    /// Map server name to ServerId enum
    fn map_server_name(&self, server_name: &str) -> ServerId {
        match server_name {
            "desktop-commander" => ServerId::DesktopCommander,
            "sequential-thinking" => ServerId::SequentialThinking,
            "context7" => ServerId::Context7,
            _ => {
                tracing::warn!(unknown_server = %server_name, "Unknown server name, using DesktopCommander as default");
                ServerId::DesktopCommander
            }
        }
    }

    /// Get tools available to a specific agent
    pub async fn get_tools_for_agent(&self, agent_type: AgentType) -> Vec<&RegisteredTool> {
        let permissions = self.agent_permissions.get(&agent_type);

        self.available_tools
            .values()
            .filter(|tool| {
                let access_level = tool.access_permissions.get(&agent_type);

                // Check if tool has access level for this agent
                if access_level.is_none() || access_level == Some(&ToolAccessLevel::None) {
                    return false;
                }

                // Check agent-specific permissions
                if let Some(perms) = permissions {
                    // Check denied tools
                    if perms.denied_tools.contains(&tool.definition.function.name) {
                        return false;
                    }

                    // Check allowed tools (if specified)
                    if !perms.allowed_tools.is_empty()
                        && !perms.allowed_tools.contains(&tool.definition.function.name)
                    {
                        return false;
                    }

                    // Check restricted categories
                    if perms.restricted_categories.contains(&tool.category) {
                        return false;
                    }
                }

                true
            })
            .collect()
    }

    /// Get OpenRouter-compatible tool definitions for an agent
    pub async fn get_openai_tools_for_agent(&self, agent_type: AgentType) -> Vec<ToolDefinition> {
        self.get_tools_for_agent(agent_type)
            .await
            .into_iter()
            .map(|tool| tool.definition.clone())
            .collect()
    }

    /// Validate tool access for an agent
    pub fn validate_tool_access(&self, agent_type: &AgentType, tool_name: &str) -> Result<ToolAccessLevel> {
        let tool = self.available_tools.get(tool_name)
            .ok_or_else(|| anyhow::anyhow!("Tool '{}' not found in registry", tool_name))?;

        let access_level = tool.access_permissions
            .get(&agent_type)
            .ok_or_else(|| anyhow::anyhow!("No access level defined for agent '{:?}' and tool '{}'", agent_type, tool_name))?;

        if *access_level == ToolAccessLevel::None {
            return Err(anyhow::anyhow!("Agent '{:?}' does not have access to tool '{}'", agent_type, tool_name));
        }

        // Check agent-specific permissions
        if let Some(perms) = self.agent_permissions.get(&agent_type) {
            if perms.denied_tools.contains(&tool_name.to_string()) {
                return Err(anyhow::anyhow!("Tool '{}' is explicitly denied for agent '{:?}'", tool_name, agent_type));
            }

            if !perms.allowed_tools.is_empty() && !perms.allowed_tools.contains(&tool_name.to_string()) {
                return Err(anyhow::anyhow!("Tool '{}' is not in allowed list for agent '{:?}'", tool_name, agent_type));
            }

            if perms.restricted_categories.contains(&tool.category) {
                return Err(anyhow::anyhow!("Tool category '{:?}' is restricted for agent '{:?}'", tool.category, agent_type));
            }
        }

        Ok(*access_level)
    }

    /// Execute a tool call
    pub async fn execute_tool(
        &self,
        agent_type: AgentType,
        tool_name: &str,
        arguments: Value,
    ) -> Result<ToolExecutionResult> {
        let start_time = std::time::Instant::now();

        // Validate access
        let access_level = self.validate_tool_access(&agent_type, tool_name)?;

        let tool = self.available_tools.get(tool_name)
            .ok_or_else(|| anyhow::anyhow!("Tool '{}' not found", tool_name))?;

        // Check if tool is read-only but agent is trying to modify
        if access_level == ToolAccessLevel::ReadOnly && tool.metadata.state_modifying {
            return Err(anyhow::anyhow!(
                "Tool '{}' requires full access but agent '{:?}' only has read-only access",
                tool_name, agent_type
            ));
        }

        // Execute tool via MCP manager
        let result = if let Some(mcp_manager) = &self.mcp_manager {
            let mut manager = mcp_manager.lock().await;
            manager.call_tool(tool_name, arguments.clone()).await
        } else {
            Err(anyhow::anyhow!("No MCP client manager available"))
        };

        let execution_time_ms = start_time.elapsed().as_millis() as u64;
        let success = result.is_ok();

        // Extract error message before consuming result
        let error_msg = result.as_ref().err().map(|e| e.to_string());
        let result_value = result.ok();

        // Create execution record
        let execution_result = ToolExecutionResult {
            tool_call: ExecutedToolCall {
                tool_name: tool_name.to_string(),
                arguments,
                agent_type: agent_type.clone(),
                timestamp: chrono::Utc::now(),
                server_id: tool.server_id.clone(),
            },
            success,
            result: result_value,
            error: error_msg,
            execution_time_ms,
            cost_weight: tool.metadata.cost_weight,
            metadata: HashMap::new(),
        };

        // Update statistics
        self.update_stats(&execution_result).await;

        tracing::debug!(
            tool_name = %tool_name,
            agent_type = ?agent_type,
            success = success,
            time_ms = execution_time_ms,
            "Tool execution completed"
        );

        Ok(execution_result)
    }

    /// Update registry statistics
    async fn update_stats(&self, result: &ToolExecutionResult) {
        let mut stats = self.stats.write().await;

        stats.total_tool_calls += 1;

        if !result.success {
            stats.failed_calls += 1;
        }

        // Update by agent
        *stats.calls_by_agent.entry(result.tool_call.agent_type.clone()).or_insert(0) += 1;

        // Update by category
        if let Some(tool) = self.available_tools.get(&result.tool_call.tool_name) {
            *stats.calls_by_category.entry(tool.category.clone()).or_insert(0) += 1;
        }

        // Update most used tools
        let tool_name = &result.tool_call.tool_name;
        if let Some((_, count)) = stats.most_used_tools.iter_mut().find(|(name, _)| name == tool_name) {
            *count += 1;
        } else {
            stats.most_used_tools.push((tool_name.clone(), 1));
        }

        // Update average execution time
        let total_time = stats.avg_execution_time_ms * (stats.total_tool_calls - 1) as f64 + result.execution_time_ms as f64;
        stats.avg_execution_time_ms = total_time / stats.total_tool_calls as f64;

        // Keep most used tools sorted and limited
        stats.most_used_tools.sort_by(|a, b| b.1.cmp(&a.1));
        stats.most_used_tools.truncate(10);
    }

    /// Get registry statistics
    pub async fn get_stats(&self) -> ToolRegistryStats {
        self.stats.read().await.clone()
    }

    /// Reset statistics
    pub async fn reset_stats(&self) {
        let mut stats = self.stats.write().await;
        *stats = ToolRegistryStats::default();
    }

    /// Get tool information by name
    pub fn get_tool_info(&self, tool_name: &str) -> Option<&RegisteredTool> {
        self.available_tools.get(tool_name)
    }

    /// List all available tools by category
    pub fn list_tools_by_category(&self, category: ToolCategory) -> Vec<&RegisteredTool> {
        self.available_tools
            .values()
            .filter(|tool| tool.category == category)
            .collect()
    }

    /// Get available tools count
    pub fn get_available_tools_count(&self) -> usize {
        self.available_tools.len()
    }

    /// Check if MCP client manager is available
    pub fn has_mcp_manager(&self) -> bool {
        self.mcp_manager.is_some()
    }
}