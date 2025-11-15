use crate::research_agent::{ExecutionPlan, ResearchResult};
use crate::execution_engine::{ExecutionEngine, PlanExecutionRequest, ExecutionStep, ExecutionOptions, ToolCallSpec};
use crate::tool_facade::{ToolFacade, ToolExecutionContext, SafetyMode};
use crate::tool_registry::ToolRegistry;
use crate::unified_context::{UnifiedProjectContext, AgentContextType};
use crate::llm_client::LlmFactory;
use crate::llm_config::AgentType;
use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::sync::Arc;
use chrono::{DateTime, Utc};

/// Redesigned Orchestrator Agent focused on plan execution with full MCP tool access
pub struct OrchestratorAgent {
    /// API key for LLM access
    api_key: String,

    /// LLM factory for creating clients
    llm_factory: Option<LlmFactory>,

    /// Execution engine for running plans
    execution_engine: Arc<ExecutionEngine>,

    /// Tool facade for direct tool access
    tool_facade: Arc<ToolFacade>,

    /// Orchestrator configuration
    config: OrchestratorAgentConfig,
}

/// Configuration for orchestrator agent behavior
#[derive(Debug, Clone)]
pub struct OrchestratorAgentConfig {
    /// Maximum number of retries for failed steps
    pub max_retries: usize,

    /// Whether to enable adaptive execution (modify plan based on results)
    pub enable_adaptive_execution: bool,

    /// Safety mode for tool execution
    pub safety_mode: SafetyMode,

    /// Whether to enable detailed logging
    pub enable_detailed_logging: bool,

    /// Maximum execution time per plan (seconds)
    pub max_execution_time_seconds: u64,

    /// Whether to enable step validation
    pub enable_step_validation: bool,
}

impl Default for OrchestratorAgentConfig {
    fn default() -> Self {
        Self {
            max_retries: 3,
            enable_adaptive_execution: true,
            safety_mode: SafetyMode::Medium,
            enable_detailed_logging: true,
            max_execution_time_seconds: 300, // 5 minutes
            enable_step_validation: true,
        }
    }
}

/// Input for orchestrator execution
#[derive(Debug, Clone)]
pub struct OrchestratorInput {
    /// User's original request
    pub user_input: String,

    /// Research result with execution plan
    pub research_result: ResearchResult,

    /// Project context for execution
    pub project_context: UnifiedProjectContext,

    /// Execution constraints
    pub constraints: ExecutionConstraints,

    /// Previous execution results (for adaptive execution)
    pub previous_results: Option<Vec<ExecutionResult>>,
}

/// Constraints for plan execution
#[derive(Debug, Clone)]
pub struct ExecutionConstraints {
    /// Whether this is a dry run
    pub dry_run: bool,

    /// Maximum execution time
    pub max_time_seconds: Option<u64>,

    /// Allowed tool categories (empty = all allowed)
    pub allowed_tool_categories: Vec<String>,

    /// Forbidden tools
    pub forbidden_tools: Vec<String>,

    /// Safety mode override
    pub safety_mode: Option<SafetyMode>,
}

/// Result of plan execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionResult {
    /// Execution identifier
    pub execution_id: String,

    /// Research result that was executed
    pub research_result: ResearchResult,

    /// Plan execution result
    pub plan_result: PlanExecutionResult,

    /// Execution statistics and insights
    pub insights: ExecutionInsights,

    /// Whether execution was successful
    pub success: bool,

    /// Error details if execution failed
    pub error_details: Option<String>,

    /// Execution timestamp
    pub timestamp: DateTime<Utc>,
}

/// Plan execution result (enhanced from execution_engine)
#[derive(Debug, Clone, Serialize, Deserialize)]
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

    /// Generated commands/tools used
    pub generated_commands: Vec<Value>,

    /// Error details if execution failed
    pub error_details: Option<String>,
}

/// Step execution result (enhanced)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StepExecutionResult {
    /// Step identifier
    pub step_id: String,

    /// Whether step was successful
    pub success: bool,

    /// Results for each tool call in the step
    pub tool_results: Vec<ToolExecutionResult>,

    /// Execution time for this step
    pub execution_time_ms: u64,

    /// Error message if step failed
    pub error_message: Option<String>,

    /// Retry attempts made
    pub retry_attempts: u32,

    /// Step validation results
    pub validation_results: Option<StepValidationResult>,
}

/// Tool execution result (compatible with existing system)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolExecutionResult {
    /// Tool name
    pub tool_name: String,

    /// Tool arguments
    pub arguments: Value,

    /// Whether execution was successful
    pub success: bool,

    /// Result data
    pub result: Option<Value>,

    /// Error message if failed
    pub error_message: Option<String>,

    /// Execution time
    pub execution_time_ms: u64,
}

/// Step validation result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StepValidationResult {
    /// Whether step outcome meets success criteria
    pub success_criteria_met: bool,

    /// Validation errors
    pub validation_errors: Vec<String>,

    /// Validation warnings
    pub validation_warnings: Vec<String>,

    /// Post-conditions checked
    pub post_conditions_checked: Vec<String>,
}

/// Execution statistics
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
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

    /// Total execution time
    pub total_execution_time_ms: u64,

    /// Tools used
    pub tools_used: Vec<String>,
}

/// Execution insights and analysis
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionInsights {
    /// Performance analysis
    pub performance_analysis: PerformanceAnalysis,

    /// Success factors analysis
    pub success_factors: Vec<SuccessFactor>,

    /// Issues encountered
    pub issues_encountered: Vec<ExecutionIssue>,

    /// Recommendations for improvement
    pub recommendations: Vec<String>,

    /// Adaptive execution changes made
    pub adaptive_changes: Vec<AdaptiveChange>,
}

/// Performance analysis
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PerformanceAnalysis {
    /// Overall execution efficiency
    pub efficiency_score: f32,

    /// Bottleneck steps
    pub bottleneck_steps: Vec<String>,

    /// Tool usage efficiency
    pub tool_efficiency: std::collections::HashMap<String, f32>,

    /// Time distribution by step
    pub time_distribution: std::collections::HashMap<String, u64>,
}

/// Success factors identified during execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SuccessFactor {
    /// Factor description
    pub description: String,

    /// Impact level (0.0-1.0)
    pub impact: f32,

    /// Evidence supporting this factor
    pub evidence: Vec<String>,
}

/// Issues encountered during execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionIssue {
    /// Issue description
    pub description: String,

    /// Severity level
    pub severity: IssueSeverity,

    /// When the issue occurred
    pub occurrence_time: DateTime<Utc>,

    /// How the issue was resolved
    pub resolution: Option<String>,

    /// Step where issue occurred
    pub step_id: Option<String>,
}

/// Issue severity levels
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum IssueSeverity {
    Low,
    Medium,
    High,
    Critical,
}

/// Changes made during adaptive execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AdaptiveChange {
    /// Change description
    pub description: String,

    /// Reason for the change
    pub reason: String,

    /// When the change was made
    pub timestamp: DateTime<Utc>,

    /// Impact on execution
    pub impact: String,
}

impl OrchestratorAgent {
    /// Create a new orchestrator agent
    pub fn new(
        api_key: &str,
        execution_engine: Arc<ExecutionEngine>,
        tool_facade: Arc<ToolFacade>,
    ) -> Self {
        Self {
            api_key: api_key.to_string(),
            llm_factory: None,
            execution_engine,
            tool_facade,
            config: OrchestratorAgentConfig::default(),
        }
    }

    /// Create orchestrator agent with custom configuration
    pub fn with_config(
        api_key: &str,
        execution_engine: Arc<ExecutionEngine>,
        tool_facade: Arc<ToolFacade>,
        config: OrchestratorAgentConfig,
    ) -> Self {
        Self {
            api_key: api_key.to_string(),
            llm_factory: None,
            execution_engine,
            tool_facade,
            config,
        }
    }

    /// Set LLM factory for this agent
    pub fn with_llm_factory(mut self, llm_factory: Option<LlmFactory>) -> Self {
        self.llm_factory = llm_factory;
        self
    }

    /// Main entry point: execute research plan
    pub async fn execute_plan(&self, input: OrchestratorInput) -> Result<ExecutionResult> {
        let execution_id = uuid::Uuid::new_v4().to_string();
        let start_time = Utc::now();

        tracing::info!(
            execution_id = %execution_id,
            plan_id = %input.research_result.research_id,
            steps_count = input.research_result.execution_plan.as_ref().map(|p| p.steps.len()).unwrap_or(0),
            "Starting plan execution"
        );

        // Validate input and plan
        self.validate_execution_input(&input)?;

        // Convert research plan to execution engine format
        let plan = input.research_result.execution_plan
            .ok_or_else(|| anyhow::anyhow!("No execution plan in research result"))?;

        let execution_request = self.convert_plan_to_request(&input, &plan)?;

        // Execute the plan
        let plan_result = self.execution_engine.execute_plan(execution_request).await?;

        // Generate execution insights
        let insights = self.generate_execution_insights(&input, &plan_result).await?;

        // Process tool results into commands compatible with existing system
        let generated_commands = self.process_tool_results(&plan_result).await?;

        let end_time = Utc::now();
        let success = plan_result.success && insights.performance_analysis.efficiency_score > 0.5;

        Ok(ExecutionResult {
            execution_id,
            research_result: input.research_result,
            plan_result,
            insights,
            success,
            error_details: if !success {
                plan_result.error_details.clone()
            } else {
                None
            },
            timestamp: end_time,
        })
    }

    /// Execute plan with direct tool calls (for simpler cases)
    pub async fn execute_with_direct_tools(&self, plan: &ExecutionPlan, context: &UnifiedProjectContext) -> Result<Vec<Value>> {
        let mut commands = Vec::new();
        let execution_context = self.create_execution_context(context);

        for step in &plan.steps {
            for tool_call in &step.required_tools {
                // Map plan tools to actual tool calls
                let tool_spec = self.map_tool_to_spec(tool_call, step)?;

                let request = crate::tool_facade::ToolExecutionRequest {
                    agent_type: AgentType::Orchestrator,
                    tool_name: tool_spec.tool_name.clone(),
                    arguments: tool_spec.arguments.clone(),
                    execution_context: Some(execution_context.clone()),
                    metadata: std::collections::HashMap::new(),
                };

                let result = self.tool_facade.execute_tool_with_context(request).await?;

                if result.execution_result.success {
                    if let Some(result_data) = result.execution_result.result {
                        commands.push(result_data);
                    }
                } else {
                    return Err(anyhow::anyhow!(
                        "Tool execution failed: {}",
                        result.execution_result.error.unwrap_or_default()
                    ));
                }
            }
        }

        Ok(commands)
    }

    /// Generate actions for a plan (compatible with existing system)
    pub async fn generate_actions_for_plan(
        &self,
        plan: &ExecutionPlan,
        user_input: &str,
        plugin_examples: &str,
        allowed_actions: &str,
    ) -> Result<crate::llm_client::LlmResponse> {
        let llm_client = self.llm_factory.as_ref()
            .ok_or_else(|| anyhow::anyhow!("LLM factory not configured for orchestrator agent"))?
            .create_client_for_agent(AgentType::Orchestrator)?;

        let plan_summary = serde_json::to_string_pretty(plan)?;

        let system_prompt = format!(
            r#"You are a command generation agent for Godot with access to advanced tools.

Execution Plan:
{}

Plugin Command Examples:
{}

Available Actions: {}

Generate a JSON array of Godot editor commands to execute this plan.
Each command must match the plugin schema OR use MCP tools for advanced operations.

MCP Tool Format: {{"action":"desktop_commander","tool":"tool_name","args":{{...}}}}

Available MCP tools include:
- File operations: read_file, write_file, edit_block, list_directory, etc.
- Search operations: start_search, get_more_search_results
- Process operations: start_process, interact_with_process
- Documentation access via Context7

Focus on precise, executable commands that will implement the plan steps."#,
            plan_summary,
            plugin_examples,
            allowed_actions
        );

        let user_prompt = format!(
            r#"User Request: {}
Plan to Execute: {}

Generate specific commands to implement this plan. Include both Godot editor commands and MCP tool calls as needed."#,
            user_input,
            plan.metadata.description
        );

        llm_client.generate_response(&system_prompt, &user_prompt).await
    }

    /// Validate execution input and plan
    fn validate_execution_input(&self, input: &OrchestratorInput) -> Result<()> {
        if input.research_result.execution_plan.is_none() {
            return Err(anyhow::anyhow!("No execution plan provided in research result"));
        }

        let plan = input.research_result.execution_plan.as_ref().unwrap();

        if plan.steps.is_empty() {
            return Err(anyhow::anyhow!("Execution plan has no steps"));
        }

        // Check for required tools availability
        for step in &plan.steps {
            for tool in &step.required_tools {
                // TODO: Verify tool is available in tool registry
                tracing::debug!(required_tool = %tool, "Validating tool availability");
            }
        }

        Ok(())
    }

    /// Convert research plan to execution engine request
    fn convert_plan_to_request(&self, input: &OrchestratorInput, plan: &ExecutionPlan) -> Result<PlanExecutionRequest> {
        let steps: Vec<ExecutionStep> = plan.steps.iter()
            .enumerate()
            .map(|(i, step)| {
                let tool_calls: Vec<ToolCallSpec> = step.required_tools.iter()
                    .map(|tool_name| ToolCallSpec {
                        tool_name: tool_name.clone(),
                        arguments: serde_json::json!({}), // TODO: Extract from step
                        critical: true,
                        expected_outcome: Some(step.expected_outcome.clone()),
                        retry_count: self.config.max_retries as u32,
                    })
                    .collect();

                ExecutionStep {
                    step_id: step.step_id.clone(),
                    description: step.description.clone(),
                    tool_calls,
                    dependencies: step.dependencies.clone(),
                    critical: true,
                    timeout_seconds: Some(self.config.max_execution_time_seconds),
                }
            })
            .collect();

        let options = ExecutionOptions {
            continue_on_failure: false,
            max_retries: self.config.max_retries as u32,
            enable_parallel: false, // Start with sequential execution
            enable_validation: self.config.enable_step_validation,
            dry_run: input.constraints.dry_run,
        };

        let context = self.create_execution_context(&input.project_context);

        Ok(PlanExecutionRequest {
            agent_type: AgentType::Orchestrator,
            plan_id: plan.plan_id.clone(),
            steps,
            context,
            options,
        })
    }

    /// Create execution context from project context
    fn create_execution_context(&self, project_context: &UnifiedProjectContext) -> ToolExecutionContext {
        ToolExecutionContext {
            project_path: project_context.structured_index.project_path.clone(),
            working_dir: None,
            session_id: Some(uuid::Uuid::new_v4().to_string()),
            dry_run: false,
            safety_mode: self.config.safety_mode.clone(),
        }
    }

    /// Generate execution insights from results
    async fn generate_execution_insights(&self, input: &OrchestratorInput, result: &PlanExecutionResult) -> Result<ExecutionInsights> {
        let mut insights = ExecutionInsights {
            performance_analysis: PerformanceAnalysis {
                efficiency_score: self.calculate_efficiency_score(result),
                bottleneck_steps: self.identify_bottlenecks(result),
                tool_efficiency: self.calculate_tool_efficiency(result),
                time_distribution: self.calculate_time_distribution(result),
            },
            success_factors: self.identify_success_factors(input, result),
            issues_encountered: self.identify_issues(result),
            recommendations: self.generate_recommendations(result),
            adaptive_changes: vec![], // TODO: Track adaptive changes
        };

        // Add adaptive execution insights if enabled
        if self.config.enable_adaptive_execution {
            insights.adaptive_changes = self.analyze_adaptive_changes(result).await?;
        }

        Ok(insights)
    }

    /// Process tool results into commands compatible with existing system
    async fn process_tool_results(&self, result: &PlanExecutionResult) -> Result<Vec<Value>> {
        let mut commands = Vec::new();

        for step_result in &result.step_results {
            for tool_result in &step_result.tool_results {
                if tool_result.success {
                    // Convert tool results to command format expected by existing system
                    if let Some(result_data) = &tool_result.result {
                        commands.push(result_data.clone());
                    }
                }
            }
        }

        // If no specific commands, create a simple success response
        if commands.is_empty() {
            commands.push(serde_json::json!({
                "status": "success",
                "message": "Plan executed successfully",
                "steps_completed": result.step_results.len(),
                "total_time_ms": result.total_time_ms
            }));
        }

        Ok(commands)
    }

    /// Map tool name to tool specification
    fn map_tool_to_spec(&self, tool_name: &str, step: &crate::research_agent::PlanStep) -> Result<ToolCallSpec> {
        // TODO: Implement proper tool mapping based on step requirements
        Ok(ToolCallSpec {
            tool_name: tool_name.to_string(),
            arguments: serde_json::json!({}),
            critical: true,
            expected_outcome: Some(step.expected_outcome.clone()),
            retry_count: self.config.max_retries as u32,
        })
    }

    // Helper methods for insight generation
    fn calculate_efficiency_score(&self, result: &PlanExecutionResult) -> f32 {
        if result.total_time_ms == 0 {
            return 0.0;
        }

        let success_rate = result.statistics.successful_steps as f32 / result.statistics.total_steps as f32;
        let time_efficiency = 1.0 - (result.total_time_ms as f32 / 300000.0).min(1.0); // 5 minutes = max

        (success_rate + time_efficiency) / 2.0
    }

    fn identify_bottlenecks(&self, result: &PlanExecutionResult) -> Vec<String> {
        let avg_step_time = result.total_time_ms as f32 / result.step_results.len() as f32;
        let mut bottlenecks = Vec::new();

        for step_result in &result.step_results {
            if step_result.execution_time_ms as f32 > avg_step_time * 1.5 {
                bottlenecks.push(step_result.step_id.clone());
            }
        }

        bottlenecks
    }

    fn calculate_tool_efficiency(&self, result: &PlanExecutionResult) -> std::collections::HashMap<String, f32> {
        let mut efficiency = std::collections::HashMap::new();
        let mut tool_usage = std::collections::HashMap::new();
        let mut tool_success = std::collections::HashMap::new();

        for step_result in &result.step_results {
            for tool_result in &step_result.tool_results {
                *tool_usage.entry(tool_result.tool_name.clone()).or_insert(0) += 1;
                if tool_result.success {
                    *tool_success.entry(tool_result.tool_name.clone()).or_insert(0) += 1;
                }
            }
        }

        for (tool_name, total_uses) in tool_usage {
            let successful = tool_success.get(&tool_name).unwrap_or(&0);
            efficiency.insert(tool_name, *successful as f32 / *total_uses as f32);
        }

        efficiency
    }

    fn calculate_time_distribution(&self, result: &PlanExecutionResult) -> std::collections::HashMap<String, u64> {
        let mut distribution = std::collections::HashMap::new();

        for step_result in &result.step_results {
            distribution.insert(step_result.step_id.clone(), step_result.execution_time_ms);
        }

        distribution
    }

    fn identify_success_factors(&self, input: &OrchestratorInput, result: &PlanExecutionResult) -> Vec<SuccessFactor> {
        let mut factors = Vec::new();

        if result.success {
            factors.push(SuccessFactor {
                description: "Plan was well-structured and executable".to_string(),
                impact: 0.8,
                evidence: vec![format!("{} out of {} steps successful", result.statistics.successful_steps, result.statistics.total_steps)],
            });
        }

        factors
    }

    fn identify_issues(&self, result: &PlanExecutionResult) -> Vec<ExecutionIssue> {
        let mut issues = Vec::new();

        for step_result in &result.step_results {
            if !step_result.success {
                if let Some(error_msg) = &step_result.error_message {
                    issues.push(ExecutionIssue {
                        description: format!("Step {} failed: {}", step_result.step_id, error_msg),
                        severity: IssueSeverity::High,
                        occurrence_time: Utc::now(),
                        resolution: None,
                        step_id: Some(step_result.step_id.clone()),
                    });
                }
            }
        }

        issues
    }

    fn generate_recommendations(&self, result: &PlanExecutionResult) -> Vec<String> {
        let mut recommendations = Vec::new();

        if !result.success {
            recommendations.push("Consider reviewing tool permissions and availability".to_string());
        }

        if result.total_time_ms > 180000 { // 3 minutes
            recommendations.push("Consider optimizing plan steps for better performance".to_string());
        }

        recommendations
    }

    async fn analyze_adaptive_changes(&self, result: &PlanExecutionResult) -> Result<Vec<AdaptiveChange>> {
        // TODO: Implement adaptive change analysis
        Ok(vec![])
    }
}