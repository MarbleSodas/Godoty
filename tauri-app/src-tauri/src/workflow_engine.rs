use crate::context_manager::{ContextManager, ContextRequirements};
use crate::tool_registry::ToolRegistry;
use crate::tool_facade::ToolFacade;
use crate::execution_engine::ExecutionEngine;
use crate::research_agent::{ResearchAgent, ResearchInput, ResearchConstraints, ResourceLimits};
use crate::orchestrator_agent::{OrchestratorAgent, OrchestratorInput, ExecutionConstraints};
use crate::unified_context::{UnifiedProjectContext, AgentContextType};
use crate::project_indexer::ProjectIndex;
use crate::chat_session::ChatSession;
use crate::llm_client::LlmFactory;
use crate::llm_config::AgentType;
use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::sync::Arc;
use chrono::{DateTime, Utc};

/// Main workflow engine that orchestrates Research → Orchestrator workflow
pub struct WorkflowEngine {
    /// Context manager for unified context building
    context_manager: Arc<ContextManager>,

    /// Tool registry for access control
    tool_registry: Arc<ToolRegistry>,

    /// Tool facade for secure tool execution
    tool_facade: Arc<ToolFacade>,

    /// Execution engine for plan execution
    execution_engine: Arc<ExecutionEngine>,

    /// Research agent
    research_agent: ResearchAgent,

    /// Orchestrator agent
    orchestrator_agent: OrchestratorAgent,

    /// Workflow configuration
    config: WorkflowConfig,
}

/// Workflow configuration
#[derive(Debug, Clone)]
pub struct WorkflowConfig {
    /// Whether to enable adaptive workflow (adjust based on complexity)
    pub enable_adaptive_workflow: bool,

    /// Maximum total workflow time (seconds)
    pub max_workflow_time_seconds: u64,

    /// Whether to enable detailed logging
    pub enable_detailed_logging: bool,

    /// Default safety mode
    pub default_safety_mode: crate::tool_facade::SafetyMode,

    /// Whether to enable performance monitoring
    pub enable_performance_monitoring: bool,
}

impl Default for WorkflowConfig {
    fn default() -> Self {
        Self {
            enable_adaptive_workflow: true,
            max_workflow_time_seconds: 600, // 10 minutes
            enable_detailed_logging: true,
            default_safety_mode: crate::tool_facade::SafetyMode::Medium,
            enable_performance_monitoring: true,
        }
    }
}

/// Main workflow request
#[derive(Debug, Clone)]
pub struct WorkflowRequest {
    /// User's input request
    pub user_input: String,

    /// Project path
    pub project_path: String,

    /// Project index
    pub project_index: ProjectIndex,

    /// Optional chat session for context
    pub chat_session: Option<Arc<ChatSession>>,

    /// Workflow options
    pub options: WorkflowOptions,
}

/// Options for workflow execution
#[derive(Debug, Clone)]
pub struct WorkflowOptions {
    /// Whether this is a dry run
    pub dry_run: bool,

    /// Maximum complexity allowed
    pub max_complexity: Option<crate::research_agent::ComplexityLevel>,

    /// Focus areas for research
    pub focus_areas: Vec<String>,

    /// Whether to force full research even for simple requests
    pub force_full_research: bool,

    /// Safety mode override
    pub safety_mode: Option<crate::tool_facade::SafetyMode>,

    /// Whether to return intermediate results
    pub return_intermediate_results: bool,
}

impl Default for WorkflowOptions {
    fn default() -> Self {
        Self {
            dry_run: false,
            max_complexity: None,
            focus_areas: Vec::new(),
            force_full_research: false,
            safety_mode: None,
            return_intermediate_results: false,
        }
    }
}

/// Main workflow result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowResult {
    /// Workflow identifier
    pub workflow_id: String,

    /// User request that was processed
    pub user_input: String,

    /// Whether workflow was successful
    pub success: bool,

    /// Generated commands (compatible with existing system)
    pub commands: Vec<Value>,

    /// Workflow phases completed
    pub phases: Vec<WorkflowPhase>,

    /// Research result (if research was performed)
    pub research_result: Option<crate::research_agent::ResearchResult>,

    /// Execution result (if execution was performed)
    pub execution_result: Option<crate::orchestrator_agent::ExecutionResult>,

    /// Workflow statistics and insights
    pub statistics: WorkflowStatistics,

    /// Error details if workflow failed
    pub error_details: Option<String>,

    /// Workflow timestamp
    pub timestamp: DateTime<Utc>,
}

/// Individual workflow phase
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowPhase {
    /// Phase identifier
    pub phase_id: String,

    /// Phase type
    pub phase_type: WorkflowPhaseType,

    /// Phase description
    pub description: String,

    /// Whether phase was successful
    pub success: bool,

    /// Phase duration in milliseconds
    pub duration_ms: u64,

    /// Phase-specific data
    pub data: Option<Value>,

    /// Error message if phase failed
    pub error_message: Option<String>,
}

/// Types of workflow phases
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum WorkflowPhaseType {
    ContextBuilding,
    Research,
    Planning,
    Execution,
    Validation,
}

/// Workflow statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowStatistics {
    /// Total workflow time in milliseconds
    pub total_time_ms: u64,

    /// Time spent in each phase
    pub phase_times: std::collections::HashMap<String, u64>,

    /// Number of tools used
    pub tools_used: usize,

    /// Number of commands generated
    pub commands_generated: usize,

    /// Context completeness score
    pub context_completeness: f32,

    /// Research confidence score
    pub research_confidence: Option<f32>,

    /// Execution efficiency score
    pub execution_efficiency: Option<f32>,
}

impl WorkflowEngine {
    /// Create a new workflow engine
    pub fn new(api_key: &str, project_root: String) -> Self {
        let context_manager = Arc::new(ContextManager::new(api_key));
        let tool_registry = Arc::new(ToolRegistry::new());
        let tool_facade = Arc::new(ToolFacade::new(tool_registry.clone(), project_root.clone()));
        let execution_engine = Arc::new(ExecutionEngine::new(tool_registry.clone(), project_root));

        let research_agent = ResearchAgent::new(
            api_key,
            context_manager.clone(),
            tool_registry.clone(),
        );

        let orchestrator_agent = OrchestratorAgent::new(
            api_key,
            execution_engine.clone(),
            tool_facade.clone(),
        );

        Self {
            context_manager,
            tool_registry,
            tool_facade,
            execution_engine,
            research_agent,
            orchestrator_agent,
            config: WorkflowConfig::default(),
        }
    }

    /// Create workflow engine with custom configuration
    pub fn with_config(
        api_key: &str,
        project_root: String,
        config: WorkflowConfig,
    ) -> Self {
        let mut engine = Self::new(api_key, project_root);
        engine.config = config;
        engine
    }

    /// Set LLM factory for agents
    pub fn with_llm_factory(mut self, llm_factory: Option<LlmFactory>) -> Self {
        self.research_agent = self.research_agent.with_llm_factory(llm_factory.clone());
        self.orchestrator_agent = self.orchestrator_agent.with_llm_factory(llm_factory);
        self
    }

    /// Main entry point: process user request through complete workflow
    pub async fn process_request(&self, request: WorkflowRequest) -> Result<WorkflowResult> {
        let workflow_id = uuid::Uuid::new_v4().to_string();
        let start_time = Utc::now();
        let mut phases = Vec::new();

        tracing::info!(
            workflow_id = %workflow_id,
            user_input_preview = %request.user_input.chars().take(100).collect::<String>(),
            project_path = %request.project_path,
            "Starting workflow processing"
        );

        // Phase 1: Build unified context
        let (unified_context, context_phase) = self.build_context_phase(&request, &workflow_id).await?;
        phases.push(context_phase);

        // Phase 2: Assess complexity and determine workflow path
        let complexity_assessment = self.assess_complexity(&request.user_input, &unified_context).await?;

        // Phase 3: Research phase (create execution plan)
        let (research_result, research_phase) = self.research_phase(
            &request,
            &unified_context,
            &complexity_assessment,
            &workflow_id,
        ).await?;
        phases.push(research_phase);

        // Phase 4: Execution phase
        let (execution_result, execution_phase) = self.execution_phase(
            &request,
            &unified_context,
            &research_result,
            &workflow_id,
        ).await?;
        phases.push(execution_phase);

        // Phase 5: Validation phase
        let (validation_success, validation_phase) = self.validation_phase(
            &request,
            &research_result,
            &execution_result,
            &workflow_id,
        ).await?;
        phases.push(validation_phase);

        let end_time = Utc::now();
        let total_time_ms = end_time.signed_duration_since(start_time).num_milliseconds() as u64;

        // Extract commands from execution result
        let commands = if let Some(execution) = &execution_result {
            execution.plan_result.generated_commands.clone()
        } else {
            Vec::new()
        };

        // Calculate statistics
        let statistics = self.calculate_workflow_statistics(
            total_time_ms,
            &phases,
            &unified_context,
            &Some(research_result.clone()),
            &execution_result,
        );

        let success = validation_success && (execution_result.is_some() || commands.len() > 0);

        Ok(WorkflowResult {
            workflow_id,
            user_input: request.user_input.clone(),
            success,
            commands,
            phases,
            research_result: Some(research_result),
            execution_result,
            statistics,
            error_details: if !success {
                phases.iter()
                    .filter_map(|p| p.error_message.clone())
                    .next()
            } else {
                None
            },
            timestamp: end_time,
        })
    }

    /// Quick execution for simple requests (bypasses full research)
    pub async fn execute_simple_request(&self, request: WorkflowRequest) -> Result<WorkflowResult> {
        let workflow_id = uuid::Uuid::new_v4().to_string();
        let start_time = Utc::now();
        let mut phases = Vec::new();

        tracing::info!(
            workflow_id = %workflow_id,
            "Executing simple request workflow"
        );

        // Build minimal context
        let (unified_context, context_phase) = self.build_context_phase(&request, &workflow_id).await?;
        phases.push(context_phase);

        // Direct execution with orchestrator using minimal plan
        let minimal_plan = self.create_minimal_plan(&request.user_input, &unified_context).await?;

        let execution_input = OrchestratorInput {
            user_input: request.user_input.clone(),
            research_result: crate::research_agent::ResearchResult {
                research_id: workflow_id.clone(),
                timestamp: Utc::now(),
                findings: Vec::new(),
                execution_plan: Some(minimal_plan),
                recommended_approaches: Vec::new(),
                risks_and_mitigations: Vec::new(),
                metadata: crate::research_agent::ResearchMetadata {
                    research_duration_seconds: 0,
                    sources_consulted: 0,
                    tools_used: Vec::new(),
                    iterations_performed: 0,
                    overall_confidence: 0.5,
                },
            },
            project_context: unified_context,
            constraints: ExecutionConstraints {
                dry_run: request.options.dry_run,
                max_time_seconds: Some(self.config.max_workflow_time_seconds),
                allowed_tool_categories: Vec::new(),
                forbidden_tools: Vec::new(),
                safety_mode: request.options.safety_mode.clone(),
            },
            previous_results: None,
        };

        let execution_result = self.orchestrator_agent.execute_plan(execution_input).await?;

        let end_time = Utc::now();
        let total_time_ms = end_time.signed_duration_since(start_time).num_milliseconds() as u64;

        let commands = execution_result.plan_result.generated_commands.clone();

        // Collect statistics before moving values
        let phase_times: Vec<(String, u64)> = phases.iter()
            .map(|p| (p.phase_id.clone(), p.duration_ms))
            .collect();
        let commands_count = commands.len();

        Ok(WorkflowResult {
            workflow_id,
            user_input: request.user_input.clone(),
            success: execution_result.success,
            commands,
            phases,
            research_result: None,
            execution_result: Some(execution_result),
            statistics: WorkflowStatistics {
                total_time_ms,
                phase_times,
                tools_used: commands_count,
                commands_generated: commands_count,
                context_completeness: 0.5,
                research_confidence: None,
                execution_efficiency: Some(0.7),
            },
            error_details: None,
            timestamp: end_time,
        })
    }

    /// Phase 1: Build unified context
    async fn build_context_phase(
        &self,
        request: &WorkflowRequest,
        workflow_id: &str,
    ) -> Result<(UnifiedProjectContext, WorkflowPhase)> {
        let phase_start = std::time::Instant::now();
        let phase_id = format!("{}-context", workflow_id);

        tracing::debug!(workflow_id = %workflow_id, "Building unified context");

        // Determine context requirements based on workflow options
        let requirements = if request.options.force_full_research {
            ContextManager::research_requirements()
        } else {
            ContextManager::orchestrator_requirements()
        };

        // Build unified context
        let unified_context = self.context_manager
            .build_unified_context(
                &request.user_input,
                &request.project_path,
                &request.project_index,
                request.chat_session.as_ref().map(|s| s.as_ref()),
                &requirements,
            )
            .await?;

        let duration_ms = phase_start.elapsed().as_millis() as u64;

        let phase = WorkflowPhase {
            phase_id,
            phase_type: WorkflowPhaseType::ContextBuilding,
            description: "Built unified project context with documentation and search results".to_string(),
            success: true,
            duration_ms,
            data: Some(serde_json::json!({
                "context_completeness": unified_context.metadata.completeness_score,
                "total_tokens": unified_context.metadata.total_tokens,
                "sources_used": unified_context.metadata.sources_used
            })),
            error_message: None,
        };

        Ok((unified_context, phase))
    }

    /// Assess request complexity
    async fn assess_complexity(
        &self,
        user_input: &str,
        context: &UnifiedProjectContext,
    ) -> Result<ComplexityAssessment> {
        // Simple heuristic-based complexity assessment
        let input_length = user_input.len();
        let project_size = context.structured_index.scenes.len() + context.structured_index.scripts.len();
        let context_quality = context.metadata.completeness_score;

        let complexity_level = if input_length < 50 && project_size < 10 && context_quality > 0.7 {
            crate::research_agent::ComplexityLevel::Simple
        } else if input_length < 200 && project_size < 50 && context_quality > 0.5 {
            crate::research_agent::ComplexityLevel::Medium
        } else if input_length < 500 && project_size < 100 {
            crate::research_agent::ComplexityLevel::Complex
        } else {
            crate::research_agent::ComplexityLevel::Critical
        };

        let should_use_research = matches!(
            complexity_level,
            crate::research_agent::ComplexityLevel::Medium |
            crate::research_agent::ComplexityLevel::Complex |
            crate::research_agent::ComplexityLevel::Critical
        );

        Ok(ComplexityAssessment {
            complexity_level,
            should_use_research,
            confidence: 0.8,
            reasoning: format!(
                "Based on input length ({}), project size ({}), and context quality ({:.2})",
                input_length, project_size, context_quality
            ),
        })
    }

    /// Phase 2: Research and planning
    async fn research_phase(
        &self,
        request: &WorkflowRequest,
        context: &UnifiedProjectContext,
        assessment: &ComplexityAssessment,
        workflow_id: &str,
    ) -> Result<(crate::research_agent::ResearchResult, WorkflowPhase)> {
        let phase_start = std::time::Instant::now();
        let phase_id = format!("{}-research", workflow_id);

        tracing::debug!(
            workflow_id = %workflow_id,
            complexity = ?assessment.complexity_level,
            "Starting research phase"
        );

        let research_input = ResearchInput {
            user_input: request.user_input.clone(),
            project_context: context.clone(),
            previous_research: None,
            constraints: ResearchConstraints {
                max_complexity: request.options.max_complexity.clone().unwrap_or(assessment.complexity_level.clone()),
                focus_areas: request.options.focus_areas.clone(),
                exclusions: Vec::new(),
                time_limit_seconds: Some(self.config.max_workflow_time_seconds / 2),
                resource_limits: ResourceLimits {
                    max_files_to_analyze: 20,
                    max_documentation_topics: 10,
                    max_rag_queries: 5,
                },
            },
        };

        let research_result = self.research_agent.create_execution_plan(research_input).await?;

        let duration_ms = phase_start.elapsed().as_millis() as u64;

        let phase = WorkflowPhase {
            phase_id,
            phase_type: WorkflowPhaseType::Research,
            description: format!(
                "Researched and created execution plan with {} steps",
                research_result.execution_plan.as_ref().map(|p| p.steps.len()).unwrap_or(0)
            ),
            success: true,
            duration_ms,
            data: Some(serde_json::json!({
                "research_confidence": research_result.metadata.overall_confidence,
                "steps_created": research_result.execution_plan.as_ref().map(|p| p.steps.len()).unwrap_or(0),
                "findings_count": research_result.findings.len()
            })),
            error_message: None,
        };

        Ok((research_result, phase))
    }

    /// Phase 3: Execution
    async fn execution_phase(
        &self,
        request: &WorkflowRequest,
        context: &UnifiedProjectContext,
        research_result: &crate::research_agent::ResearchResult,
        workflow_id: &str,
    ) -> Result<(Option<crate::orchestrator_agent::ExecutionResult>, WorkflowPhase)> {
        let phase_start = std::time::Instant::now();
        let phase_id = format!("{}-execution", workflow_id);

        tracing::debug!(workflow_id = %workflow_id, "Starting execution phase");

        // Skip execution if no plan was created
        let execution_plan = match &research_result.execution_plan {
            Some(plan) => plan,
            None => {
                let duration_ms = phase_start.elapsed().as_millis() as u64;
                return Ok((None, WorkflowPhase {
                    phase_id,
                    phase_type: WorkflowPhaseType::Execution,
                    description: "Skipped execution - no execution plan available".to_string(),
                    success: true,
                    duration_ms,
                    data: None,
                    error_message: None,
                }));
            }
        };

        let orchestrator_input = OrchestratorInput {
            user_input: request.user_input.clone(),
            research_result: research_result.clone(),
            project_context: context.clone(),
            constraints: ExecutionConstraints {
                dry_run: request.options.dry_run,
                max_time_seconds: Some(self.config.max_workflow_time_seconds / 2),
                allowed_tool_categories: Vec::new(),
                forbidden_tools: Vec::new(),
                safety_mode: request.options.safety_mode.clone(),
            },
            previous_results: None,
        };

        let execution_result = self.orchestrator_agent.execute_plan(orchestrator_input).await?;

        let duration_ms = phase_start.elapsed().as_millis() as u64;

        let phase = WorkflowPhase {
            phase_id,
            phase_type: WorkflowPhaseType::Execution,
            description: format!(
                "Executed plan with {} steps, {} commands generated",
                execution_result.plan_result.step_results.len(),
                execution_result.plan_result.generated_commands.len()
            ),
            success: execution_result.success,
            duration_ms,
            data: Some(serde_json::json!({
                "commands_generated": execution_result.plan_result.generated_commands.len(),
                "steps_completed": execution_result.plan_result.step_results.len(),
                "execution_efficiency": execution_result.insights.performance_analysis.efficiency_score
            })),
            error_message: execution_result.error_details.clone(),
        };

        Ok((Some(execution_result), phase))
    }

    /// Phase 4: Validation
    async fn validation_phase(
        &self,
        request: &WorkflowRequest,
        research_result: &crate::research_agent::ResearchResult,
        execution_result: &Option<crate::orchestrator_agent::ExecutionResult>,
        workflow_id: &str,
    ) -> Result<(bool, WorkflowPhase)> {
        let phase_start = std::time::Instant::now();
        let phase_id = format!("{}-validation", workflow_id);

        tracing::debug!(workflow_id = %workflow_id, "Starting validation phase");

        // Basic validation checks
        let mut validation_success = true;
        let mut validation_errors = Vec::new();

        // Check if execution produced results
        if let Some(execution) = execution_result {
            if !execution.success {
                validation_success = false;
                validation_errors.push("Execution failed".to_string());
            }

            if execution.plan_result.generated_commands.is_empty() {
                validation_errors.push("No commands generated".to_string());
            }
        } else {
            validation_errors.push("No execution result available".to_string());
        }

        // Check research quality
        if research_result.metadata.overall_confidence < 0.5 {
            validation_errors.push("Low research confidence".to_string());
        }

        let duration_ms = phase_start.elapsed().as_millis() as u64;

        let phase = WorkflowPhase {
            phase_id,
            phase_type: WorkflowPhaseType::Validation,
            description: if validation_success {
                "Validation completed successfully".to_string()
            } else {
                format!("Validation failed: {}", validation_errors.join(", "))
            },
            success: validation_success,
            duration_ms,
            data: Some(serde_json::json!({
                "validation_errors": validation_errors,
                "research_confidence": research_result.metadata.overall_confidence
            })),
            error_message: if validation_errors.is_empty() {
                None
            } else {
                Some(validation_errors.join(", "))
            },
        };

        Ok((validation_success, phase))
    }

    /// Create minimal plan for simple requests
    async fn create_minimal_plan(
        &self,
        user_input: &str,
        context: &UnifiedProjectContext,
    ) -> Result<crate::research_agent::ExecutionPlan> {
        let plan_id = uuid::Uuid::new_v4().to_string();

        Ok(crate::research_agent::ExecutionPlan {
            plan_id,
            metadata: crate::research_agent::PlanMetadata {
                title: format!("Simple execution: {}", user_input.chars().take(30).collect::<String>()),
                description: "Minimal plan for simple request".to_string(),
                complexity: crate::research_agent::ComplexityLevel::Simple,
                estimated_time_minutes: 1,
                required_tools: vec!["create_node".to_string(), "modify_node".to_string()],
                risk_level: crate::research_agent::RiskLevel::Low,
            },
            preconditions: vec![],
            steps: vec![crate::research_agent::PlanStep {
                step_id: "simple-step".to_string(),
                step_number: 1,
                description: format!("Execute: {}", user_input),
                explanation: "Direct execution of user request".to_string(),
                required_tools: vec![],
                expected_outcome: "Request completed successfully".to_string(),
                success_criteria: vec!["No errors".to_string()],
                dependencies: vec![],
                error_recovery: vec![],
                estimated_time_minutes: 1,
                safety_considerations: vec![],
            }],
            post_conditions: vec![],
            fallback_strategies: vec![],
        })
    }

    /// Calculate workflow statistics
    fn calculate_workflow_statistics(
        &self,
        total_time_ms: u64,
        phases: &[WorkflowPhase],
        context: &UnifiedProjectContext,
        research_result: &Option<crate::research_agent::ResearchResult>,
        execution_result: &Option<crate::orchestrator_agent::ExecutionResult>,
    ) -> WorkflowStatistics {
        let phase_times: std::collections::HashMap<String, u64> = phases
            .iter()
            .map(|p| (p.phase_id.clone(), p.duration_ms))
            .collect();

        let (tools_used, commands_generated, research_confidence, execution_efficiency) = if let Some(execution) = execution_result {
            (
                execution.plan_result.statistics.total_tool_calls as usize,
                execution.plan_result.generated_commands.len(),
                None,
                Some(execution.insights.performance_analysis.efficiency_score),
            )
        } else {
            (0, 0, None, None)
        };

        WorkflowStatistics {
            total_time_ms,
            phase_times,
            tools_used,
            commands_generated,
            context_completeness: context.metadata.completeness_score as f32,
            research_confidence: research_result.as_ref().map(|r| r.metadata.overall_confidence),
            execution_efficiency,
        }
    }

    /// Get workflow engine statistics
    pub async fn get_statistics(&self) -> WorkflowEngineStatistics {
        WorkflowEngineStatistics {
            context_stats: self.context_manager.get_stats().await,
            tool_registry_stats: self.tool_registry.get_stats().await,
            execution_stats: self.execution_engine.get_performance_metrics().await,
        }
    }
}

/// Complexity assessment result
#[derive(Debug, Clone)]
pub struct ComplexityAssessment {
    pub complexity_level: crate::research_agent::ComplexityLevel,
    pub should_use_research: bool,
    pub confidence: f32,
    pub reasoning: String,
}

/// Workflow engine statistics
#[derive(Debug, Clone)]
pub struct WorkflowEngineStatistics {
    pub context_stats: crate::context_manager::ContextStats,
    pub tool_registry_stats: crate::tool_registry::ToolRegistryStats,
    pub execution_stats: crate::execution_engine::PerformanceMetrics,
}