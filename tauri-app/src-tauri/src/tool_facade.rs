use crate::tool_registry::{ToolRegistry, ToolExecutionResult};
use crate::llm_config::AgentType;
use crate::unified_context::{UnifiedProjectContext, AgentContextType};
use anyhow::Result;
use serde_json::Value;
use std::sync::Arc;

/// Simplified interface for agents to access tools with proper validation and security
pub struct ToolFacade {
    tool_registry: Arc<ToolRegistry>,
    project_root: String,
    execution_stats: Arc<tokio::sync::RwLock<ToolFacadeStats>>,
}

/// Statistics for tool facade operations
#[derive(Debug, Default, Clone)]
pub struct ToolFacadeStats {
    /// Total tool executions
    pub total_executions: u64,

    /// Executions by agent
    pub executions_by_agent: std::collections::HashMap<AgentType, u64>,

    /// Security violations prevented
    pub security_violations_prevented: u64,

    /// Path validation failures
    pub path_validation_failures: u64,

    /// Successful executions
    pub successful_executions: u64,
}

/// Context-aware tool execution request
#[derive(Debug, Clone)]
pub struct ToolExecutionRequest {
    /// Agent making the request
    pub agent_type: AgentType,

    /// Tool name to execute
    pub tool_name: String,

    /// Tool arguments
    pub arguments: Value,

    /// Request context for validation
    pub execution_context: Option<ToolExecutionContext>,

    /// Request metadata
    pub metadata: std::collections::HashMap<String, String>,
}

/// Execution context for tool requests
#[derive(Debug, Clone)]
pub struct ToolExecutionContext {
    /// Current project path
    pub project_path: String,

    /// Current working directory relative to project
    pub working_dir: Option<String>,

    /// Session identifier
    pub session_id: Option<String>,

    /// Whether this is a dry run
    pub dry_run: bool,

    /// Safety mode level
    pub safety_mode: SafetyMode,
}

/// Safety levels for tool execution
#[derive(Debug, Clone, PartialEq)]
pub enum SafetyMode {
    /// High safety - no dangerous operations
    High,
    /// Medium safety - allow modifications but validate carefully
    Medium,
    /// Low safety - allow most operations
    Low,
}

/// Tool execution result with additional context
#[derive(Debug, Clone)]
pub struct ContextualToolResult {
    /// Raw execution result
    pub execution_result: ToolExecutionResult,

    /// Whether the result was processed for agent consumption
    pub processed_for_agent: bool,

    /// Security analysis of the operation
    pub security_analysis: SecurityAnalysis,

    /// Performance metrics
    pub performance_metrics: PerformanceMetrics,
}

/// Security analysis of tool execution
#[derive(Debug, Clone)]
pub struct SecurityAnalysis {
    /// Whether the operation was safe
    pub safe: bool,

    /// Security concerns identified
    pub concerns: Vec<String>,

    /// Whether paths were validated
    pub paths_validated: bool,

    /// Whether the operation was within allowed scope
    pub within_scope: bool,
}

/// Performance metrics for tool execution
#[derive(Debug, Clone)]
pub struct PerformanceMetrics {
    /// Total execution time
    pub total_time_ms: u64,

    /// Network time (if applicable)
    pub network_time_ms: Option<u64>,

    /// File system time (if applicable)
    pub fs_time_ms: Option<u64>,

    /// Memory usage estimate
    pub memory_usage_bytes: Option<u64>,
}

impl ToolFacade {
    /// Create a new tool facade with the given registry and project root
    pub fn new(tool_registry: Arc<ToolRegistry>, project_root: String) -> Self {
        Self {
            tool_registry,
            project_root,
            execution_stats: Arc::new(tokio::sync::RwLock::new(ToolFacadeStats::default())),
        }
    }

    /// Execute a tool with context-aware validation and security
    pub async fn execute_tool_with_context(
        &self,
        request: ToolExecutionRequest,
    ) -> Result<ContextualToolResult> {
        let start_time = std::time::Instant::now();

        // Update stats
        {
            let mut stats = self.execution_stats.write().await;
            stats.total_executions += 1;
            *stats.executions_by_agent.entry(request.agent_type.clone()).or_insert(0) += 1;
        }

        // Security validation
        let security_analysis = self.validate_execution_security(&request).await?;
        if !security_analysis.safe {
            {
                let mut stats = self.execution_stats.write().await;
                stats.security_violations_prevented += 1;
            }

            return Err(anyhow::anyhow!(
                "Tool execution blocked by security validation: {}",
                security_analysis.concerns.join(", ")
            ));
        }

        // Path validation for file operations
        self.validate_paths(&request).await?;

        // Create execution context (need to extract before borrowing request)
        let execution_context = request.execution_context.clone().unwrap_or_else(|| {
            ToolExecutionContext {
                project_path: self.project_root.clone(),
                working_dir: None,
                session_id: None,
                dry_run: false,
                safety_mode: SafetyMode::Medium,
            }
        });

        // Handle dry run
        if execution_context.dry_run {
            return Ok(self.create_dry_run_result(&request, &security_analysis).await);
        }

        // Execute the actual tool
        let execution_result = self.tool_registry
            .execute_tool(
                request.agent_type.clone(),
                &request.tool_name,
                request.arguments.clone(),
            )
            .await?;

        // Process result for agent consumption
        let processed_result = self.process_result_for_agent(
            &execution_result,
            &request.agent_type,
        ).await?;

        // Calculate performance metrics
        let total_time_ms = start_time.elapsed().as_millis() as u64;
        let performance_metrics = PerformanceMetrics {
            total_time_ms,
            network_time_ms: None, // TODO: Extract from execution_result
            fs_time_ms: None,      // TODO: Extract from execution_result
            memory_usage_bytes: None,
        };

        // Update successful execution stats
        if execution_result.success {
            let mut stats = self.execution_stats.write().await;
            stats.successful_executions += 1;
        }

        Ok(ContextualToolResult {
            execution_result,
            processed_for_agent: true,
            security_analysis,
            performance_metrics,
        })
    }

    /// Execute multiple tools in sequence with context propagation
    pub async fn execute_tool_sequence(
        &self,
        agent_type: AgentType,
        tools: Vec<(String, Value)>,
        execution_context: Option<ToolExecutionContext>,
    ) -> Result<Vec<ContextualToolResult>> {
        let mut results = Vec::new();
        let mut context = execution_context;

        for (tool_name, arguments) in tools {
            let request = ToolExecutionRequest {
                agent_type: agent_type.clone(),
                tool_name,
                arguments,
                execution_context: context.clone(),
                metadata: std::collections::HashMap::new(),
            };

            let result = self.execute_tool_with_context(request).await?;

            // Update context for next tool based on result
            if let Some(ref mut ctx) = context {
                self.update_execution_context(ctx, &result).await;
            }

            results.push(result);

            // Stop sequence if a tool fails
            if !results.last().unwrap().execution_result.success {
                break;
            }
        }

        Ok(results)
    }

    /// Execute tools in parallel (when safe to do so)
    pub async fn execute_tools_parallel(
        &self,
        agent_type: AgentType,
        tools: Vec<(String, Value)>,
    ) -> Result<Vec<ContextualToolResult>> {
        // Check if parallel execution is safe for these tools
        if !self.is_parallel_execution_safe(&tools) {
            return self.execute_tool_sequence(agent_type, tools, None).await;
        }

        let requests: Vec<ToolExecutionRequest> = tools
            .into_iter()
            .map(|(tool_name, arguments)| ToolExecutionRequest {
                agent_type: agent_type.clone(),
                tool_name,
                arguments,
                execution_context: None,
                metadata: std::collections::HashMap::new(),
            })
            .collect();

        // Execute in parallel
        let futures = requests
            .into_iter()
            .map(|req| self.execute_tool_with_context(req));

        let results: Vec<Result<ContextualToolResult>> = futures_util::future::join_all(futures).await;

        // Collect results, returning first error if any
        let mut successful_results = Vec::new();
        for result in results {
            match result {
                Ok(r) => successful_results.push(r),
                Err(e) => return Err(e),
            }
        }

        Ok(successful_results)
    }

    /// Validate execution security
    async fn validate_execution_security(&self, request: &ToolExecutionRequest) -> Result<SecurityAnalysis> {
        let mut concerns = Vec::new();
        let mut safe = true;
        let mut paths_validated = true;
        let mut within_scope = true;

        // Check agent permissions
        match self.tool_registry.validate_tool_access(&request.agent_type, &request.tool_name) {
            Ok(_) => {
                // Access granted
            }
            Err(e) => {
                safe = false;
                concerns.push(format!("Access denied: {}", e));
            }
        }

        // Check for dangerous operations based on agent type and tool
        if request.agent_type == AgentType::Planning {
            let dangerous_tools = [
                "write_file", "edit_block", "create_directory",
                "move_file", "start_process", "interact_with_process", "kill_process"
            ];

            if dangerous_tools.contains(&request.tool_name.as_str()) {
                safe = false;
                concerns.push(format!(
                    "Research agent attempted to use dangerous tool: {}",
                    request.tool_name
                ));
            }
        }

        // Validate execution context safety mode
        if let Some(ctx) = &request.execution_context {
            if ctx.safety_mode == SafetyMode::High {
                // High safety mode - block potentially dangerous operations
                let high_risk_tools = [
                    "start_process", "interact_with_process", "kill_process",
                    "write_file", "edit_block"
                ];

                if high_risk_tools.contains(&request.tool_name.as_str()) {
                    safe = false;
                    concerns.push(format!(
                        "Tool {} blocked in high safety mode",
                        request.tool_name
                    ));
                }
            }
        }

        Ok(SecurityAnalysis {
            safe,
            concerns,
            paths_validated,
            within_scope,
        })
    }

    /// Validate file paths to ensure they stay within project boundaries
    async fn validate_paths(&self, request: &ToolExecutionRequest) -> Result<()> {
        // For file operation tools, validate paths
        let file_tools = [
            "read_file", "write_file", "edit_block", "create_directory",
            "list_directory", "move_file", "get_file_info"
        ];

        if !file_tools.contains(&request.tool_name.as_str()) {
            return Ok(());
        }

        // Extract paths from arguments
        if let Some(paths) = self.extract_paths_from_arguments(&request.arguments) {
            for path in paths {
                if !self.is_path_safe(&path) {
                    {
                        let mut stats = self.execution_stats.write().await;
                        stats.path_validation_failures += 1;
                    }

                    return Err(anyhow::anyhow!(
                        "Path validation failed: '{}' is outside project boundaries or contains dangerous patterns",
                        path
                    ));
                }
            }
        }

        Ok(())
    }

    /// Extract file paths from tool arguments
    fn extract_paths_from_arguments(&self, arguments: &Value) -> Option<Vec<String>> {
        let mut paths = Vec::new();

        // Common path argument names
        let path_fields = ["path", "file_path", "source", "destination", "directory_path"];

        for field in &path_fields {
            if let Some(path) = arguments.get(field).and_then(|v| v.as_str()) {
                paths.push(path.to_string());
            }
        }

        // Handle array of paths
        if let Some(path_array) = arguments.get("paths").and_then(|v| v.as_array()) {
            for path_value in path_array {
                if let Some(path) = path_value.as_str() {
                    paths.push(path.to_string());
                }
            }
        }

        if paths.is_empty() {
            None
        } else {
            Some(paths)
        }
    }

    /// Check if a path is safe (within project boundaries)
    fn is_path_safe(&self, path: &str) -> bool {
        use std::path::Path;

        // Normalize the path
        let normalized_path = Path::new(path);

        // Check for dangerous patterns
        let path_str = normalized_path.to_string_lossy();
        let dangerous_patterns = ["..", "~", "/etc", "/sys", "/proc", "$HOME"];

        for pattern in &dangerous_patterns {
            if path_str.contains(pattern) {
                return false;
            }
        }

        // If absolute path, ensure it's within project root
        if normalized_path.is_absolute() {
            if !path_str.starts_with(&self.project_root) {
                return false;
            }
        }

        // For relative paths, we'll rely on the working directory being set properly
        true
    }

    /// Check if parallel execution is safe for the given tools
    fn is_parallel_execution_safe(&self, tools: &[(String, Value)]) -> bool {
        // Don't allow parallel execution if any tool modifies state
        let state_modifying_tools = [
            "write_file", "edit_block", "create_directory", "move_file",
            "start_process", "interact_with_process", "kill_process"
        ];

        for (tool_name, _) in tools {
            if state_modifying_tools.contains(&tool_name.as_str()) {
                return false;
            }
        }

        true
    }

    /// Create a dry run result
    async fn create_dry_run_result(
        &self,
        request: &ToolExecutionRequest,
        security_analysis: &SecurityAnalysis,
    ) -> ContextualToolResult {
        ContextualToolResult {
            execution_result: ToolExecutionResult {
                tool_call: crate::tool_registry::ExecutedToolCall {
                    tool_name: request.tool_name.clone(),
                    arguments: request.arguments.clone(),
                    agent_type: request.agent_type.clone(),
                    timestamp: chrono::Utc::now(),
                    server_id: "dry_run".to_string(),
                },
                success: true,
                result: Some(serde_json::json!({
                    "dry_run": true,
                    "message": "Tool execution simulated (dry run mode)",
                    "tool_name": request.tool_name
                })),
                error: None,
                execution_time_ms: 0,
                cost_weight: 0.0,
                metadata: std::collections::HashMap::new(),
            },
            processed_for_agent: true,
            security_analysis: security_analysis.clone(),
            performance_metrics: PerformanceMetrics {
                total_time_ms: 0,
                network_time_ms: None,
                fs_time_ms: None,
                memory_usage_bytes: None,
            },
        }
    }

    /// Process execution result for agent consumption
    async fn process_result_for_agent(
        &self,
        execution_result: &ToolExecutionResult,
        agent_type: &AgentType,
    ) -> Result<bool> {
        // Different agents may need different result processing
        match agent_type {
            AgentType::Planning => {
                // For planning agents, focus on extracting insights and data
                self.process_result_for_planning(execution_result).await
            }
            AgentType::Orchestrator => {
                // For orchestrator agents, focus on execution status and outcomes
                self.process_result_for_orchestrator(execution_result).await
            }
        }
    }

    /// Process result for research agent
    async fn process_result_for_planning(&self, _execution_result: &ToolExecutionResult) -> Result<bool> {
        // Research agents need detailed analysis of results
        // TODO: Implement research-specific processing
        Ok(true)
    }

    /// Process result for orchestrator agent
    async fn process_result_for_orchestrator(&self, _execution_result: &ToolExecutionResult) -> Result<bool> {
        // Orchestrator agents need concise execution status
        // TODO: Implement orchestrator-specific processing
        Ok(true)
    }

    /// Update execution context based on tool result
    async fn update_execution_context(
        &self,
        context: &mut ToolExecutionContext,
        result: &ContextualToolResult,
    ) {
        // TODO: Update context based on tool execution results
        // For example, update working directory, track state changes, etc.
    }

    /// Get execution statistics
    pub async fn get_execution_stats(&self) -> ToolFacadeStats {
        let stats = self.execution_stats.read().await;
        (*stats).clone()
    }

    /// Reset execution statistics
    pub async fn reset_execution_stats(&self) {
        let mut stats = self.execution_stats.write().await;
        *stats = ToolFacadeStats::default();
    }

    /// Create default execution context
    pub fn create_default_context(&self) -> ToolExecutionContext {
        ToolExecutionContext {
            project_path: self.project_root.clone(),
            working_dir: None,
            session_id: None,
            dry_run: false,
            safety_mode: SafetyMode::Medium,
        }
    }
}