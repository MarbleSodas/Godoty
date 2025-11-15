use crate::tool_facade::{ToolFacade, ToolExecutionRequest, ToolExecutionContext, SafetyMode};
use crate::tool_registry::ToolRegistry;
use crate::llm_config::AgentType;
use crate::unified_context::UnifiedProjectContext;
use anyhow::Result;
use serde_json::Value;
use std::sync::Arc;
use tokio::sync::RwLock;

/// Command execution engine with advanced orchestration capabilities
pub struct ExecutionEngine {
    tool_facade: Arc<ToolFacade>,
    execution_state: Arc<RwLock<ExecutionState>>,
    config: ExecutionConfig,
}

/// Configuration for execution behavior
#[derive(Debug, Clone)]
pub struct ExecutionConfig {
    /// Maximum concurrent tool executions
    pub max_concurrent_executions: usize,

    /// Default timeout for tool execution (seconds)
    pub default_timeout_seconds: u64,

    /// Whether to enable execution replay for debugging
    pub enable_execution_replay: bool,

    /// Whether to enable performance monitoring
    pub enable_performance_monitoring: bool,

    /// Safety level for execution
    pub default_safety_mode: SafetyMode,
}

impl Default for ExecutionConfig {
    fn default() -> Self {
        Self {
            max_concurrent_executions: 5,
            default_timeout_seconds: 30,
            enable_execution_replay: true,
            enable_performance_monitoring: true,
            default_safety_mode: SafetyMode::Medium,
        }
    }
}

/// Current execution state tracking
#[derive(Debug, Default, Clone)]
pub struct ExecutionState {
    /// Currently executing sessions
    active_sessions: std::collections::HashMap<String, ExecutionSession>,

    /// Execution history
    execution_history: Vec<ExecutionRecord>,

    /// Performance metrics
    performance_metrics: PerformanceMetrics,
}

/// Active execution session
#[derive(Debug, Clone)]
pub struct ExecutionSession {
    /// Unique session identifier
    pub session_id: String,

    /// Agent type for this session
    pub agent_type: AgentType,

    /// Session start time
    pub start_time: chrono::DateTime<chrono::Utc>,

    /// Current step being executed
    pub current_step: Option<usize>,

    /// Execution context for this session
    pub context: ToolExecutionContext,

    /// Session metadata
    pub metadata: std::collections::HashMap<String, String>,
}

/// Record of a completed execution
#[derive(Debug, Clone)]
pub struct ExecutionRecord {
    /// Session identifier
    pub session_id: String,

    /// Agent type
    pub agent_type: AgentType,

    /// Whether execution was successful
    pub success: bool,

    /// Total execution time
    pub total_time_ms: u64,

    /// Number of tools executed
    pub tools_executed: usize,

    /// Execution timestamp
    pub timestamp: chrono::DateTime<chrono::Utc>,

    /// Error message if execution failed
    pub error_message: Option<String>,
}

/// Performance metrics for execution engine
#[derive(Debug, Default, Clone)]
pub struct PerformanceMetrics {
    /// Total sessions executed
    pub total_sessions: u64,

    /// Successful sessions
    pub successful_sessions: u64,

    /// Failed sessions
    pub failed_sessions: u64,

    /// Average session time
    pub avg_session_time_ms: f64,

    /// Total tools executed
    pub total_tools_executed: u64,

    /// Average tools per session
    pub avg_tools_per_session: f64,
}

/// Plan execution request
#[derive(Debug, Clone)]
pub struct PlanExecutionRequest {
    /// Agent type executing the plan
    pub agent_type: AgentType,

    /// Plan identifier
    pub plan_id: String,

    /// Steps to execute
    pub steps: Vec<ExecutionStep>,

    /// Execution context
    pub context: ToolExecutionContext,

    /// Execution options
    pub options: ExecutionOptions,
}

/// Individual execution step
#[derive(Debug, Clone)]
pub struct ExecutionStep {
    /// Step identifier
    pub step_id: String,

    /// Step description
    pub description: String,

    /// Tools to execute in this step
    pub tool_calls: Vec<ToolCallSpec>,

    /// Dependencies on other steps
    pub dependencies: Vec<String>,

    /// Whether this step is critical (failure stops execution)
    pub critical: bool,

    /// Timeout for this step (seconds)
    pub timeout_seconds: Option<u64>,
}

/// Tool call specification
#[derive(Debug, Clone)]
pub struct ToolCallSpec {
    /// Tool name
    pub tool_name: String,

    /// Tool arguments
    pub arguments: Value,

    /// Whether this tool call is critical
    pub critical: bool,

    /// Expected outcome (for validation)
    pub expected_outcome: Option<String>,

    /// Retry count on failure
    pub retry_count: u32,
}

/// Options for plan execution
#[derive(Debug, Clone)]
pub struct ExecutionOptions {
    /// Whether to continue on step failure
    pub continue_on_failure: bool,

    /// Maximum number of retries per step
    pub max_retries: u32,

    /// Whether to enable parallel execution for independent steps
    pub enable_parallel: bool,

    /// Whether to enable step validation
    pub enable_validation: bool,

    /// Dry run mode (don't actually execute tools)
    pub dry_run: bool,
}

impl Default for ExecutionOptions {
    fn default() -> Self {
        Self {
            continue_on_failure: false,
            max_retries: 2,
            enable_parallel: true,
            enable_validation: true,
            dry_run: false,
        }
    }
}

/// Result of plan execution
#[derive(Debug, Clone)]
pub struct PlanExecutionResult {
    /// Session identifier
    pub session_id: String,

    /// Whether execution was successful
    pub success: bool,

    /// Results for each step
    pub step_results: Vec<StepExecutionResult>,

    /// Total execution time
    pub total_time_ms: u64,

    /// Execution statistics
    pub statistics: ExecutionStatistics,

    /// Generated commands from tool execution
    pub generated_commands: Vec<serde_json::Value>,

    /// Error details if execution failed
    pub error_details: Option<String>,
}

/// Result of a single step execution
#[derive(Debug, Clone)]
pub struct StepExecutionResult {
    /// Step identifier
    pub step_id: String,

    /// Whether step was successful
    pub success: bool,

    /// Results for each tool call in the step
    pub tool_results: Vec<crate::tool_facade::ContextualToolResult>,

    /// Execution time for this step
    pub execution_time_ms: u64,

    /// Error message if step failed
    pub error_message: Option<String>,

    /// Retry attempts made
    pub retry_attempts: u32,
}

/// Execution statistics
#[derive(Debug, Clone, Default)]
pub struct ExecutionStatistics {
    /// Total steps executed
    pub total_steps: u32,

    /// Successful steps
    pub successful_steps: u32,

    /// Failed steps
    pub failed_steps: u32,

    /// Total tool calls made
    pub total_tool_calls: u32,

    /// Successful tool calls
    pub successful_tool_calls: u32,

    /// Failed tool calls
    pub failed_tool_calls: u64,
}

impl ExecutionEngine {
    /// Create a new execution engine
    pub fn new(tool_registry: Arc<ToolRegistry>, project_root: String) -> Self {
        Self {
            tool_facade: Arc::new(ToolFacade::new(tool_registry, project_root)),
            execution_state: Arc::new(RwLock::new(ExecutionState::default())),
            config: ExecutionConfig::default(),
        }
    }

    /// Create execution engine with custom configuration
    pub fn with_config(
        tool_registry: Arc<ToolRegistry>,
        project_root: String,
        config: ExecutionConfig,
    ) -> Self {
        Self {
            tool_facade: Arc::new(ToolFacade::new(tool_registry, project_root)),
            execution_state: Arc::new(RwLock::new(ExecutionState::default())),
            config,
        }
    }

    /// Execute a plan with the given request
    pub async fn execute_plan(&self, request: PlanExecutionRequest) -> Result<PlanExecutionResult> {
        let session_id = uuid::Uuid::new_v4().to_string();
        let start_time = std::time::Instant::now();

        // Create execution session
        let session = ExecutionSession {
            session_id: session_id.clone(),
            agent_type: request.agent_type.clone(),
            start_time: chrono::Utc::now(),
            current_step: None,
            context: request.context,
            metadata: std::collections::HashMap::new(),
        };

        // Register session
        {
            let mut state = self.execution_state.write().await;
            state.active_sessions.insert(session_id.clone(), session);
        }

        // Execute steps
        let step_results = self.execute_steps(&session_id, &request.steps, &request.options).await?;

        let total_time_ms = start_time.elapsed().as_millis() as u64;

        // Calculate overall success
        let success = step_results.iter().all(|r| r.success || !request.options.continue_on_failure);

        // Calculate statistics
        let statistics = self.calculate_statistics(&step_results);

        // Collect generated commands from step results
        let generated_commands: Vec<serde_json::Value> = step_results
            .iter()
            .flat_map(|r| r.tool_results.iter())
            .filter_map(|t| t.execution_result.result.clone())
            .collect();

        // Update session and record completion
        self.complete_session(&session_id, success, total_time_ms, &step_results).await;

        let error_details = if !success {
            step_results
                .iter()
                .find_map(|r| r.error_message.clone())
        } else {
            None
        };

        Ok(PlanExecutionResult {
            session_id,
            success,
            step_results,
            total_time_ms,
            statistics,
            generated_commands,
            error_details,
        })
    }

    /// Execute individual steps in the plan
    async fn execute_steps(
        &self,
        session_id: &str,
        steps: &[ExecutionStep],
        options: &ExecutionOptions,
    ) -> Result<Vec<StepExecutionResult>> {
        let mut step_results = Vec::new();
        let mut completed_steps = std::collections::HashSet::new();

        for step in steps {
            // Check dependencies
            if !self.check_dependencies(step, &completed_steps) {
                continue;
            }

            // Update current step in session
            {
                let mut state = self.execution_state.write().await;
                if let Some(session) = state.active_sessions.get_mut(session_id) {
                    session.current_step = Some(
                        step_results.len()
                    );
                }
            }

            // Execute the step
            let step_result = self.execute_step(session_id, step, options).await?;

            // Check if we should stop execution before moving step_result
            let should_stop = !step_result.success && !options.continue_on_failure && step.critical;

            completed_steps.insert(step.step_id.clone());
            step_results.push(step_result);

            // Stop if step failed and continue_on_failure is false
            if should_stop {
                break;
            }
        }

        Ok(step_results)
    }

    /// Check if step dependencies are satisfied
    fn check_dependencies(&self, step: &ExecutionStep, completed_steps: &std::collections::HashSet<String>) -> bool {
        step.dependencies.iter().all(|dep| completed_steps.contains(dep))
    }

    /// Execute a single step
    async fn execute_step(
        &self,
        session_id: &str,
        step: &ExecutionStep,
        options: &ExecutionOptions,
    ) -> Result<StepExecutionResult> {
        let start_time = std::time::Instant::now();
        let mut tool_results = Vec::new();
        let mut success = true;
        let mut error_message = None;
        let mut retry_attempts = 0;

        // Execute tool calls with retry logic
        for tool_call in &step.tool_calls {
            let mut tool_success = false;
            let mut tool_error = None;

            for attempt in 0..=tool_call.retry_count {
                retry_attempts = attempt;

                let request = ToolExecutionRequest {
                    agent_type: AgentType::Orchestrator, // TODO: Pass agent type from session
                    tool_name: tool_call.tool_name.clone(),
                    arguments: tool_call.arguments.clone(),
                    execution_context: Some(self.create_step_context(session_id).await),
                    metadata: std::collections::HashMap::new(),
                };

                match self.tool_facade.execute_tool_with_context(request).await {
                    Ok(result) => {
                        tool_results.push(result);
                        tool_success = true;
                        break;
                    }
                    Err(e) => {
                        tool_error = Some(e.to_string());
                        if attempt < tool_call.retry_count {
                            tokio::time::sleep(std::time::Duration::from_millis(1000)).await;
                        }
                    }
                }
            }

            if !tool_success {
                success = false;
                if tool_call.critical {
                    error_message = tool_error;
                    break;
                }
            }
        }

        let execution_time_ms = start_time.elapsed().as_millis() as u64;

        // Validate step outcome if enabled
        if success && options.enable_validation {
            // TODO: Implement step validation based on expected outcomes
        }

        Ok(StepExecutionResult {
            step_id: step.step_id.clone(),
            success,
            tool_results,
            execution_time_ms,
            error_message,
            retry_attempts,
        })
    }

    /// Create execution context for a step
    async fn create_step_context(&self, session_id: &str) -> ToolExecutionContext {
        let state = self.execution_state.read().await;

        if let Some(session) = state.active_sessions.get(session_id) {
            session.context.clone()
        } else {
            // Fallback context
            ToolExecutionContext {
                project_path: String::new(), // TODO: Get from config
                working_dir: None,
                session_id: Some(session_id.to_string()),
                dry_run: false,
                safety_mode: self.config.default_safety_mode.clone(),
            }
        }
    }

    /// Complete an execution session
    async fn complete_session(
        &self,
        session_id: &str,
        success: bool,
        total_time_ms: u64,
        step_results: &[StepExecutionResult],
    ) {
        let mut state = self.execution_state.write().await;

        if let Some(session) = state.active_sessions.remove(session_id) {
            // Create execution record
            let record = ExecutionRecord {
                session_id: session_id.to_string(),
                agent_type: session.agent_type,
                success,
                total_time_ms,
                tools_executed: step_results.iter().map(|r| r.tool_results.len()).sum(),
                timestamp: chrono::Utc::now(),
                error_message: if !success {
                    step_results
                        .iter()
                        .find_map(|r| r.error_message.clone())
                } else {
                    None
                },
            };

            // Add to history
            state.execution_history.push(record);

            // Update performance metrics
            state.performance_metrics.total_sessions += 1;
            if success {
                state.performance_metrics.successful_sessions += 1;
            } else {
                state.performance_metrics.failed_sessions += 1;
            }

            // Update averages
            let total_sessions = state.performance_metrics.total_sessions as f64;
            let current_avg = state.performance_metrics.avg_session_time_ms;
            let session_time = total_time_ms as f64;
            state.performance_metrics.avg_session_time_ms =
                (current_avg * (total_sessions - 1.0) + session_time) / total_sessions;
        }
    }

    /// Calculate execution statistics
    fn calculate_statistics(&self, step_results: &[StepExecutionResult]) -> ExecutionStatistics {
        let total_steps = step_results.len() as u32;
        let successful_steps = step_results.iter().filter(|r| r.success).count() as u32;
        let failed_steps = total_steps - successful_steps;

        let mut total_tool_calls = 0u32;
        let mut successful_tool_calls = 0u32;

        for step_result in step_results {
            total_tool_calls += step_result.tool_results.len() as u32;
            successful_tool_calls += step_result.tool_results.iter()
                .filter(|r| r.execution_result.success)
                .count() as u32;
        }

        ExecutionStatistics {
            total_steps,
            successful_steps,
            failed_steps,
            total_tool_calls,
            successful_tool_calls,
            failed_tool_calls: (total_tool_calls - successful_tool_calls) as u64,
        }
    }

    /// Get current execution state
    pub async fn get_execution_state(&self) -> ExecutionState {
        (*self.execution_state.read().await).clone()
    }

    /// Get execution history
    pub async fn get_execution_history(&self) -> Vec<ExecutionRecord> {
        self.execution_state.read().await.execution_history.clone()
    }

    /// Get performance metrics
    pub async fn get_performance_metrics(&self) -> PerformanceMetrics {
        self.execution_state.read().await.performance_metrics.clone()
    }

    /// Clear execution history
    pub async fn clear_execution_history(&self) {
        let mut state = self.execution_state.write().await;
        state.execution_history.clear();
        state.performance_metrics = PerformanceMetrics::default();
    }

    /// Get active sessions
    pub async fn get_active_sessions(&self) -> std::collections::HashMap<String, ExecutionSession> {
        self.execution_state.read().await.active_sessions.clone()
    }

    /// Cancel an active execution session
    pub async fn cancel_session(&self, session_id: &str) -> Result<bool> {
        let mut state = self.execution_state.write().await;

        if state.active_sessions.remove(session_id).is_some() {
            // TODO: Implement actual cancellation of running tool calls
            Ok(true)
        } else {
            Ok(false)
        }
    }

    /// Create default execution options
    pub fn default_options() -> ExecutionOptions {
        ExecutionOptions::default()
    }

    /// Create execution context for project
    pub fn create_project_context(&self, project_path: &str) -> ToolExecutionContext {
        ToolExecutionContext {
            project_path: project_path.to_string(),
            working_dir: None,
            session_id: None,
            dry_run: false,
            safety_mode: self.config.default_safety_mode.clone(),
        }
    }
}