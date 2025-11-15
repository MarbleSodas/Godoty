use crate::workflow_engine::{WorkflowEngine, WorkflowRequest, WorkflowOptions};
use crate::agent::{AgentResponse, AgentThought};
use crate::metrics::WorkflowMetrics;
use crate::llm_config::AgentLlmConfig;
use crate::project_indexer::ProjectIndex;
use crate::chat_session::ChatSession;
use crate::llm_client::LlmFactory;
use anyhow::Result;
use serde_json::Value;
use std::sync::Arc;

/// Migration adapter to bridge existing system with new workflow engine
pub struct MigrationAdapter {
    /// New workflow engine
    workflow_engine: WorkflowEngine,

    /// Whether to use new architecture (can be toggled)
    use_new_architecture: bool,
}

impl MigrationAdapter {
    /// Create new migration adapter
    pub fn new(api_key: &str, project_root: String) -> Self {
        Self {
            workflow_engine: WorkflowEngine::new(api_key, project_root),
            use_new_architecture: true, // Enable new architecture by default
        }
    }

    /// Create adapter with explicit architecture choice
    pub fn with_architecture(api_key: &str, project_root: String, use_new: bool) -> Self {
        Self {
            workflow_engine: WorkflowEngine::new(api_key, project_root),
            use_new_architecture: use_new,
        }
    }

    /// Set LLM factory for agents
    pub fn with_llm_factory(mut self, llm_factory: Option<LlmFactory>) -> Self {
        self.workflow_engine = self.workflow_engine.with_llm_factory(llm_factory);
        self
    }

    /// Main adapter method - process request using appropriate system
    pub async fn process_request(
        &self,
        user_input: &str,
        project_index: &ProjectIndex,
        config: Option<&AgentLlmConfig>,
        chat_session: Option<&Arc<ChatSession>>,
        api_key: &str,
        project_path: &str,
    ) -> Result<AgentResponse> {
        if self.use_new_architecture {
            self.process_with_new_architecture(user_input, project_index, config, chat_session, api_key, project_path).await
        } else {
            self.process_with_legacy_system(user_input, project_index, config, chat_session, api_key, project_path).await
        }
    }

    /// Process request using new workflow engine
    async fn process_with_new_architecture(
        &self,
        user_input: &str,
        project_index: &ProjectIndex,
        _config: Option<&AgentLlmConfig>,
        chat_session: Option<&Arc<ChatSession>>,
        _api_key: &str,
        project_path: &str,
    ) -> Result<AgentResponse> {
        tracing::info!("Processing request with new workflow engine architecture");

        let workflow_request = WorkflowRequest {
            user_input: user_input.to_string(),
            project_path: project_path.to_string(),
            project_index: project_index.clone(),
            chat_session: chat_session.cloned(),
            options: WorkflowOptions::default(),
        };

        let workflow_result = self.workflow_engine.process_request(workflow_request).await?;

        // Convert new workflow result to legacy AgentResponse format
        self.convert_workflow_result_to_agent_response(workflow_result)
    }

    /// Process request using legacy system (fallback)
    async fn process_with_legacy_system(
        &self,
        user_input: &str,
        project_index: &ProjectIndex,
        config: Option<&AgentLlmConfig>,
        chat_session: Option<&Arc<ChatSession>>,
        api_key: &str,
        project_path: &str,
    ) -> Result<AgentResponse> {
        tracing::info!("Processing request with legacy system (fallback)");

        // Use the existing AgenticWorkflow as fallback
        let mut workflow = crate::agent::AgenticWorkflow::new(api_key);

        if let Some(cfg) = config {
            workflow = workflow.with_config(cfg);
        }

        workflow.execute(user_input, project_index, chat_session).await
    }

    /// Convert WorkflowResult to AgentResponse for backward compatibility
    fn convert_workflow_result_to_agent_response(&self, workflow_result: crate::workflow_engine::WorkflowResult) -> Result<AgentResponse> {
        // Convert workflow phases to agent thoughts
        let thoughts = self.convert_phases_to_thoughts(&workflow_result.phases);

        // Create or extract execution plan
        let plan = if let Some(research_result) = &workflow_result.research_result {
            if let Some(execution_plan) = &research_result.execution_plan {
                self.convert_new_plan_to_legacy_plan(execution_plan)
            } else {
                // Create fallback plan
                crate::agent::ExecutionPlan {
                    reasoning: format!("Processed in {}ms with {} commands",
                        workflow_result.statistics.total_time_ms,
                        workflow_result.commands.len()),
                    metadata: None,
                    phases: Vec::new(),
                    steps: Vec::new(),
                    estimated_complexity: "medium".to_string(),
                    overall_goal: String::new(),
                    success_criteria: Vec::new(),
                    estimated_duration: None,
                    complexity: None,
                    preconditions: Vec::new(),
                    post_conditions: Vec::new(),
                    fallback_strategies: Vec::new(),
                    plan_id: workflow_result.workflow_id.clone(),
                }
            }
        } else {
            // Create minimal plan for simple execution
            crate::agent::ExecutionPlan {
                reasoning: "Simple request processed with new architecture".to_string(),
                metadata: None,
                phases: Vec::new(),
                steps: Vec::new(),
                estimated_complexity: "simple".to_string(),
                overall_goal: String::new(),
                success_criteria: Vec::new(),
                estimated_duration: None,
                complexity: None,
                preconditions: Vec::new(),
                post_conditions: Vec::new(),
                fallback_strategies: Vec::new(),
                plan_id: workflow_result.workflow_id.clone(),
            }
        };

        // Create workflow metrics
        let metrics = Some(WorkflowMetrics {
            reasoning_steps: thoughts.len() as u32,
            planning_tokens: 0, // TODO: Extract from workflow statistics
            planning_time_ms: workflow_result.statistics.phase_times.get("context-building")
                .or_else(|| workflow_result.statistics.phase_times.get("context"))
                .copied()
                .unwrap_or(0),
            generation_tokens: 0, // TODO: Extract from workflow statistics
            generation_time_ms: workflow_result.statistics.phase_times.get("execution")
                .copied()
                .unwrap_or(0),
            validation_tokens: 0,
            validation_time_ms: workflow_result.statistics.phase_times.get("validation")
                .copied()
                .unwrap_or(0),
            documentation_tokens: 0,
            commands_generated: workflow_result.statistics.commands_generated as u32,
            commands_validated: workflow_result.statistics.commands_generated as u32,
            total_tokens: 0, // TODO: Calculate from statistics
            kb_search_time_ms: 0,
            plugin_kb_queries: 0,
            docs_kb_queries: 0,
            total_docs_retrieved: 0,
            avg_relevance_score: 0.0,
            validation_errors: 0,
            validation_warnings: 0,
            reasoning_steps: workflow_result.phases.len() as u32,
            planning_cost_usd: 0.0,
            generation_cost_usd: 0.0,
            validation_cost_usd: 0.0,
            total_cost_usd: 0.0,
            retry_attempts: 0,
        });

        Ok(AgentResponse {
            commands: workflow_result.commands,
            thoughts,
            plan,
            metrics,
        })
    }

    /// Convert workflow phases to agent thoughts
    fn convert_phases_to_thoughts(&self, phases: &[crate::workflow_engine::WorkflowPhase]) -> Vec<AgentThought> {
        phases.iter().enumerate().map(|(i, phase)| {
            AgentThought {
                step: i + 1,
                thought: format!("[{}] {}", phase.phase_type.as_str(), phase.description),
                action: Some(phase.phase_type.as_str().to_string()),
                observation: if phase.success {
                    Some("Completed successfully".to_string())
                } else {
                    phase.error_message.clone()
                },
            }
        }).collect()
    }

    /// Convert new ExecutionPlan to legacy format
    fn convert_new_plan_to_legacy_plan(&self, new_plan: &crate::research_agent::ExecutionPlan) -> crate::agent::ExecutionPlan {
        let steps = new_plan.steps.iter().map(|step| {
            crate::agent::PlanStep {
                step_number: step.step_number,
                description: step.description.clone(),
                commands_needed: step.required_tools.clone(), // Map required_tools to commands_needed
                step_id: step.step_id.clone(),
                explanation: step.explanation.clone(),
                required_tools: step.required_tools.clone(),
                expected_outcome: step.expected_outcome.clone(),
                success_criteria: step.success_criteria.clone(),
                dependencies: step.dependencies.clone(),
                error_recovery: step.error_recovery.clone(),
                estimated_time_minutes: step.estimated_time_minutes,
                safety_considerations: step.safety_considerations.clone(),
            }
        }).collect();

        let metadata = &new_plan.metadata;

        crate::agent::ExecutionPlan {
            reasoning: metadata.description.clone(),
            metadata: Some(crate::agent::PlanMetadata {
                title: metadata.title.clone(),
                description: metadata.description.clone(),
                complexity: metadata.complexity.clone(),
                estimated_time_minutes: metadata.estimated_time_minutes,
                required_tools: metadata.required_tools.clone(),
                risk_level: metadata.risk_level.clone(),
            }),
            phases: Vec::new(), // Legacy doesn't use phases
            steps,
            estimated_complexity: metadata.complexity.clone(),
            overall_goal: metadata.title.clone(),
            success_criteria: new_plan.post_conditions.iter()
                .flat_map(|pc| pc.success_criteria.clone())
                .collect(),
            estimated_duration: Some(format!("{} minutes", metadata.estimated_time_minutes)),
            complexity: Some(metadata.complexity.clone()),
            preconditions: new_plan.preconditions.iter().map(|pc| {
                crate::agent::Precondition {
                    description: pc.description.clone(),
                    verification_method: pc.verification_method.clone(),
                    mandatory: pc.mandatory,
                }
            }).collect(),
            post_conditions: new_plan.post_conditions.iter().map(|pc| {
                crate::agent::PostCondition {
                    description: pc.description.clone(),
                    verification_method: pc.verification_method.clone(),
                    success_criteria: pc.success_criteria.clone(),
                }
            }).collect(),
            fallback_strategies: new_plan.fallback_strategies.iter().map(|fs| {
                crate::agent::FallbackStrategy {
                    name: fs.name.clone(),
                    trigger_conditions: fs.trigger_conditions.clone(),
                    alternative_steps: fs.alternative_steps.iter()
                        .map(|s| s.description.clone())
                        .collect(), // Convert Vec<PlanStep> to Vec<String>
                    expected_success_rate: fs.expected_success_rate,
                }
            }).collect(),
            plan_id: new_plan.plan_id.clone(),
        }
    }

    /// Toggle between new and legacy architecture
    pub fn set_architecture(&mut self, use_new: bool) {
        self.use_new_architecture = use_new;
        tracing::info!(use_new = use_new, "Switched architecture mode");
    }

    /// Get current architecture mode
    pub fn is_using_new_architecture(&self) -> bool {
        self.use_new_architecture
    }

    /// Get workflow engine statistics
    pub async fn get_workflow_statistics(&self) -> crate::workflow_engine::WorkflowEngineStatistics {
        self.workflow_engine.get_statistics().await
    }

    /// Perform quick execution for simple requests (bypasses full research)
    pub async fn execute_simple_request(
        &self,
        user_input: &str,
        project_index: &ProjectIndex,
        project_path: &str,
    ) -> Result<AgentResponse> {
        if !self.use_new_architecture {
            return Err(anyhow::anyhow!("Simple execution only available with new architecture"));
        }

        let workflow_request = WorkflowRequest {
            user_input: user_input.to_string(),
            project_path: project_path.to_string(),
            project_index: project_index.clone(),
            chat_session: None,
            options: WorkflowOptions {
                dry_run: false,
                max_complexity: Some(crate::research_agent::ComplexityLevel::Simple),
                focus_areas: Vec::new(),
                force_full_research: false,
                safety_mode: None,
                return_intermediate_results: false,
            },
        };

        let workflow_result = self.workflow_engine.execute_simple_request(workflow_request).await?;
        self.convert_workflow_result_to_agent_response(workflow_result)
    }
}

impl crate::workflow_engine::WorkflowPhaseType {
    fn as_str(&self) -> &'static str {
        match self {
            crate::workflow_engine::WorkflowPhaseType::ContextBuilding => "context_building",
            crate::workflow_engine::WorkflowPhaseType::Research => "research",
            crate::workflow_engine::WorkflowPhaseType::Planning => "planning",
            crate::workflow_engine::WorkflowPhaseType::Execution => "execution",
            crate::workflow_engine::WorkflowPhaseType::Validation => "validation",
        }
    }
}