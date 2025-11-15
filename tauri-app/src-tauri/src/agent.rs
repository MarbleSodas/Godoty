use crate::guardrails::{Guardrails, ValidationResult};
use crate::llm_client::LlmFactory;
use crate::llm_config::{AgentLlmConfig, AgentType};
use crate::mcp_client::McpClient;
use crate::metrics::{MetricsStore, WorkflowMetrics};
use crate::project_indexer::ProjectIndex;
use crate::context_engine::ContextEngine;
use crate::strands_agent::{
    AgentExecutionContext, AgentOutput, StrandsAgent,
    OrchestratorAgent, PlanningAgent,
};
use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Represents a thought or reasoning step in the agent's decision-making process
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentThought {
    pub step: usize,
    pub thought: String,
    pub action: Option<String>,
    pub observation: Option<String>,
}

/// Visual context data for debug/game tasks
#[derive(Clone, Debug, Default)]
pub struct VisualContext {
    #[allow(dead_code)] // Future feature: Game screenshot analysis
    pub game_screenshot_metadata: Option<Value>,
    pub game_screenshot_path: Option<String>,
}

/// Agent context containing all information needed for decision-making
#[derive(Clone)]
pub struct AgentContext {
    pub user_input: String,
    pub project_index: ProjectIndex,
    #[allow(dead_code)] // Legacy field - preserved for compatibility
    pub chat_history: String,
    pub visual_context: VisualContext,
}

/// Agentic workflow orchestrator with Strands agents
#[derive(Clone)]
pub struct AgenticWorkflow {
    api_key: String,
    client: Client,
    #[allow(dead_code)] // Enhancement plan Phase 2: Safety guardrails
    guardrails: Guardrails,
    metrics_store: Option<MetricsStore>,
    llm_factory: Option<LlmFactory>,
}

impl AgenticWorkflow {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
            guardrails: Guardrails::with_defaults(),
            metrics_store: None,
            llm_factory: None,
        }
    }


    pub fn with_metrics_store(mut self, metrics_store: MetricsStore) -> Self {
        self.metrics_store = Some(metrics_store);
        self
    }

    pub fn with_llm_factory(mut self, llm_factory: LlmFactory) -> Self {
        self.llm_factory = Some(llm_factory);
        self
    }

    /// Execute with optional MCP client and config for tool calling support
    #[tracing::instrument(skip(self, context, mcp_client, config))]
    #[allow(dead_code)] // Alternative execution method for MCP integration
    pub async fn execute_with_mcp(
        &self,
        context: &AgentContext,
        mcp_client: &mut Option<McpClient>,
        config: Option<&AgentLlmConfig>,
    ) -> Result<AgentResponse> {
        // Initialize metrics
        let request_id = uuid::Uuid::new_v4().to_string();
        let mut metrics = WorkflowMetrics::new(request_id.clone(), context.user_input.clone());

        // Trace start of workflow
        let input_preview: String = context.user_input.chars().take(120).collect();
        tracing::info!(%request_id, input_len = context.user_input.len(), input_preview = %input_preview, "Starting agentic workflow");

        // Execute the workflow and ensure metrics are saved even on error
        let result = self.execute_internal(context, &mut metrics, mcp_client, config).await;

        // Finalize metrics based on result
        match &result {
            Ok(_) => {
                metrics.finalize(true, None);
                tracing::info!(
                    total_tokens = metrics.total_tokens,
                    total_cost_usd = metrics.total_cost_usd,
                    commands_generated = metrics.commands_generated,
                    "Agentic workflow completed successfully"
                );
            }
            Err(e) => {
                metrics.finalize(false, Some(e.to_string()));
                tracing::error!(
                    total_tokens = metrics.total_tokens,
                    total_cost_usd = metrics.total_cost_usd,
                    error = %e,
                    "Agentic workflow failed"
                );
            }
        }

        // Always save metrics to store
        if let Some(store) = &self.metrics_store {
            let _ = store.add_metrics(metrics.clone()).await;
            let _ = store.save_to_disk().await;
        }

        // Return result with metrics attached
        result.map(|mut response| {
            response.metrics = Some(metrics);
            response
        })
    }

    /// Internal execution logic (separated to ensure metrics are always saved)
    #[allow(dead_code)] // Internal method for execute_with_mcp
    async fn execute_internal(
        &self,
        context: &AgentContext,
        metrics: &mut WorkflowMetrics,
        mcp_client: &mut Option<McpClient>,
        config: Option<&AgentLlmConfig>,
    ) -> Result<AgentResponse> {
        // Check rate limit
        self.guardrails.check_rate_limit().await?;

        let mut thoughts = Vec::new();
        let mut iteration = 0;

        // Create project context string
        let project_context = format!(
            "Total Scenes: {}\nTotal Scripts: {}",
            context.project_index.scenes.len(),
            context.project_index.scripts.len()
        );

        // Prepare visual context string for agents (game screenshots only)
        let local_visual = context.visual_context.clone();
        let _visual_context_str = if let Some(ref game_path) = local_visual.game_screenshot_path {
            let mut context_parts = vec![
                format!("Game Debug Screenshot: {}", game_path),
                "This shows the current visual state of the running game.".to_string(),
            ];

            if let Some(ref game_meta) = local_visual.game_screenshot_metadata {
                context_parts.push(format!("Screenshot Metadata: {}", game_meta));
            }

            Some(context_parts.join("\n"))
        } else {
            None
        };

        // Build comprehensive context before any planning
        let ctx_engine = ContextEngine::new(&self.api_key);
        // Prefetch commonly used docs (ignore errors)
        let _ = ctx_engine.prefetch_common_godot_docs().await;
        let comp_ctx = ctx_engine
            .build_comprehensive_context(
                &context.user_input,
                &context.project_index,
                None,
                8,
            )
            .await
            .unwrap_or_else(|_| crate::context_engine::ComprehensiveContext {
                godot_docs: String::new(),
                project_context: project_context.clone(),
                chat_history: String::new(),
                recent_messages: vec![],
                context_query: context.user_input.clone(),
                visual_analysis: None,
            });
        // No visual analysis for game screenshots - they are used directly via file paths
        let formatted_context_for_ai = ctx_engine.format_context_for_ai(&comp_ctx);

        // Orchestrator step: decide if research is needed
        let orchestrator = OrchestratorAgent::new(&self.api_key).with_llm_factory(self.llm_factory.clone());
        let orch_context = AgentExecutionContext {
            user_input: context.user_input.clone(),
            project_context: formatted_context_for_ai.clone(),
            previous_output: None,
            dynamic_context_provider: None,
            project_path: None,
        };

        // Use tool calling mode if enabled in config
        let use_tool_calling = config.map(|c| c.enable_tool_calling).unwrap_or(false);
        let orch_output = if use_tool_calling && mcp_client.is_some() {
            orchestrator.execute_with_tools(&orch_context, mcp_client).await.unwrap_or(AgentOutput{
                content: "{\"research_needed\":false,\"research_queries\":[\"\"],\"reasoning\":\"fallback\"}".to_string(),
                tokens_used:0,
                execution_time_ms:0,
                metadata: serde_json::Map::new(),
                cost_usd: None,
                thoughts: Vec::new(),
            })
        } else {
            orchestrator.execute(&orch_context).await.unwrap_or(AgentOutput{
                content: "{\"research_needed\":false,\"research_queries\":[\"\"],\"reasoning\":\"fallback\"}".to_string(),
                tokens_used:0,
                execution_time_ms:0,
                metadata: serde_json::Map::new(),
                cost_usd: None,
                thoughts: Vec::new(),
            })
        };

        // Track orchestrator cost in planning metrics
        if let Some(cost) = orch_output.cost_usd {
            metrics.planning_cost_usd += cost;
        }

        // Convert orchestrator thoughts to agent thoughts and add to workflow thoughts
        for orch_thought in orch_output.thoughts.iter() {
            thoughts.push(AgentThought {
                step: thoughts.len() + 1,
                thought: format!("[{}] {}", orch_thought.phase, orch_thought.insight),
                action: Some("orchestrator".to_string()),
                observation: Some(format!("Confidence: {:.0}%", orch_thought.confidence * 100.0)),
            });
        }

        // Orchestrator output parsed and research handled below where planning is resolved.

        // Step 2: Planning or accept plan from Research/Orchestrator
        // Parse Orchestrator signal for research/simple, optional initial plan, and optional direct commands
        let mut plan_opt: Option<ExecutionPlan> = None;
        let mut research_needed = false;
        let mut orch_direct_commands: Vec<Value> = Vec::new();
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(&orch_output.content) {
            research_needed = v.get("research_needed").and_then(|b| b.as_bool()).unwrap_or(false);
            if let Some(ip) = v.get("initial_plan") {
                if ip.is_object() {
                    if let Ok(p) = serde_json::from_value::<ExecutionPlan>(ip.clone()) { plan_opt = Some(p); }
                }
            }
            if let Some(dc) = v.get("direct_commands") {
                match dc {
                    serde_json::Value::Array(arr) => {
                        orch_direct_commands = arr.clone();
                    }
                    serde_json::Value::Object(obj) => {
                        orch_direct_commands = vec![serde_json::Value::Object(obj.clone())];
                    }
                    _ => {}
                }
            }
        }

        // Conditional Planning step -> produces a full plan for larger changes
        let mut planning_summary = String::new();
        if research_needed {
            let planning_agent = PlanningAgent::new(&self.api_key).with_llm_factory(self.llm_factory.clone());
            let planning_ctx = AgentExecutionContext { previous_output: Some(orch_output.content.clone()), ..orch_context.clone() };

            // Use tool calling mode for planning agent if enabled and MCP client is available
            let use_tool_calling = config.map(|c| c.enable_tool_calling).unwrap_or(true);
            let res = if use_tool_calling && mcp_client.is_some() {
                planning_agent.execute_with_tools(&planning_ctx, mcp_client).await?
            } else {
                planning_agent.execute(&planning_ctx).await?
            };

            // Track planning cost in planning metrics
            if let Some(cost) = res.cost_usd {
                metrics.planning_cost_usd += cost;
            }

            // Convert planning agent thoughts to agent thoughts
            for planning_thought in res.thoughts.iter() {
                thoughts.push(AgentThought {
                    step: thoughts.len() + 1,
                    thought: format!("[{}] {}", planning_thought.phase, planning_thought.insight),
                    action: Some("planning".to_string()),
                    observation: Some(format!("Confidence: {:.0}%", planning_thought.confidence * 100.0)),
                });
            }

            // Try to parse a plan from planning content
            match serde_json::from_str::<ExecutionPlan>(&Self::extract_json(&res.content)?) {
                Ok(p) => plan_opt = Some(p),
                Err(_) => planning_summary = res.content,
            }
        }

        // Aggregate prior context and outputs to guide planning (if needed)
        let _combined_previous = {
            let mut s = String::new();
            s.push_str("# Comprehensive Context\n");
            s.push_str(&formatted_context_for_ai);
            s.push_str("\n\n# Orchestrator Decision\n");
            s.push_str(&orch_output.content);
            if !planning_summary.is_empty() {
                s.push_str("\n\n# Planning Summary\n");
                s.push_str(&planning_summary);
            }

            s
        };

        let plan: ExecutionPlan = if let Some(p) = plan_opt {
            p
        } else {
            // Minimal fallback plan when no explicit plan was provided by Orchestrator/Planning
            ExecutionPlan {
                reasoning: "Derived minimal plan from context (no explicit plan provided)".to_string(),
                metadata: None,
                phases: vec![],
                steps: vec![PlanStep {
                    step_number: 1,
                    description: "Apply the requested change using available tools".to_string(),
                    commands_needed: vec![],
                    step_id: String::new(),
                    explanation: String::new(),
                    required_tools: vec![],
                    expected_outcome: String::new(),
                    success_criteria: vec![],
                    dependencies: vec![],
                    error_recovery: vec![],
                    estimated_time_minutes: 0,
                    safety_considerations: vec![],
                }],
                estimated_complexity: "low".to_string(),
                overall_goal: String::new(),
                success_criteria: vec![],
                estimated_duration: None,
                complexity: None,
                preconditions: vec![],
                post_conditions: vec![],
                fallback_strategies: vec![],
                plan_id: String::new(),
            }
        };

        // Fast path: if orchestrator supplied concrete direct commands, validate and return
        if !orch_direct_commands.is_empty() {
            tracing::debug!(direct_count = orch_direct_commands.len(), "Using orchestrator direct commands fast path");

            // Guardrail validation first
            let guardrail_validation = self.guardrails.validate_commands(&orch_direct_commands)?;
            if !guardrail_validation.valid {
                tracing::warn!(errors = ?guardrail_validation.errors, "Direct commands failed guardrail validation; falling back to code generation");
                thoughts.push(AgentThought {
                    step: thoughts.len() + 1,
                    thought: "Direct commands failed guardrails; falling back to code generation".to_string(),
                    action: Some("guardrails".to_string()),
                    observation: Some(guardrail_validation.errors.join("; ")),
                });
            } else {
                // Guardrails passed; accept orchestrator-provided commands and return
                let commands = orch_direct_commands;
                metrics.commands_generated = commands.len() as u32;
                metrics.commands_validated = commands.len() as u32;

                // Check token budget and record
                metrics.total_tokens = metrics.planning_tokens
                    + metrics.generation_tokens
                    + metrics.validation_tokens
                    + metrics.documentation_tokens;
                self.guardrails.check_token_budget(metrics.total_tokens)?;
                self.guardrails.record_request(metrics.total_tokens).await;

                // Return response (metrics will be finalized and saved by execute())
                return Ok(AgentResponse {
                    commands,
                    thoughts,
                    plan,
                    metrics: None, // Will be set by execute()
                });
            }
        }


        thoughts.push(AgentThought {
            step: thoughts.len() + 1,
            thought: format!("Created execution plan with {} steps", plan.steps.len()),
            action: Some("planning".to_string()),
            observation: Some(plan.reasoning.clone()),
        });
        metrics.reasoning_steps += 1;

        // Step 3: Code Generation Agent - Generate commands with retry logic
        let mut commands = Vec::new();
        let mut validation_result: Option<ValidationResult> = None;
        let max_retries = self.guardrails.config.max_retry_attempts;

        for retry in 0..=max_retries {
            iteration += 1;
            self.guardrails.check_iteration_limit(iteration)?;
            tracing::debug!(attempt = retry + 1, "Code generation attempt starting");

            // Generate commands directly with the Orchestrator model (no separate CodeGenerationAgent)
            // Plugin examples now come from Context7/ContextEngine instead of local KB
            let plugin_examples = String::new();
            let allowed_actions_list = self.guardrails.config.allowed_command_types.join(", ");

            let _system_prompt = format!(
                r#"You are a command generation agent for Godot.

Execution Plan:
{}

Plugin Command Examples:
{}

STRICT SCHEMA RULES:
- Every command MUST include an 'action' field; it must be one of: [{}].
- Map Godot UI/node types to the 'type' field ONLY when action = 'create_node' (or when searching by type). Do NOT use node types as command actions.
- Required fields by action:
  - create_node: type, name
  - create_scene: name, root_type
  - modify_node: path, properties
  - delete_node: path
  - attach_script: path, script_content
  - open_scene: path
  - select_nodes: paths
  - focus_node: path
  - rename_node: path, new_name
  - reparent_node: path, new_parent
- Use only fields defined in the schema. Do not invent new fields.

Generate a JSON array of commands to execute the plan.
Each command must be a valid JSON object matching the plugin's command schema OR the Desktop Commander MCP command schema.
- Desktop Commander MCP command shape: {{"action":"desktop_commander","tool": one of ["read_file","write_file","edit_block","create_directory","list_directory","move_file","start_search","get_more_search_results","stop_search","get_file_info","read_multiple_files","start_process","interact_with_process","read_process","list_processes","kill_process"], "args": object}}
- Prefer "edit_block" for surgical edits to existing files; "write_file" for new files; use search/directory tools as needed.
- Use process tools ("start_process", "interact_with_process") for running scripts, validation, or command execution.
- Keep ALL file/directory paths within the project root shown in context.
Respond ONLY with the JSON array, no explanations.
"#,
                serde_json::to_string_pretty(&plan)?,
                plugin_examples,
                allowed_actions_list
            );

            let mut combined_input = context.user_input.clone();
            if let Some(v) = &validation_result {
                combined_input.push_str(&format!("\n\nFix these guardrail errors: {:?}", v.errors));
            }

            let gen_start = std::time::Instant::now();
            let llm_response = orchestrator
                .generate_actions_for_plan(
                    &plan,
                    &combined_input,
                    &plugin_examples,
                    &allowed_actions_list,
                )
                .await?;
            metrics.generation_time_ms += gen_start.elapsed().as_millis() as u64;

            // Track generation cost
            if let Some(usage) = &llm_response.usage {
                metrics.generation_tokens += usage.total_tokens;
                if let Some(cost) = usage.cost {
                    metrics.generation_cost_usd += cost;
                }
            } else {
                // Fallback to approximation if no usage info
                let approx_tokens_used = ((combined_input.len() + llm_response.content.len()) / 4) as u32;
                metrics.generation_tokens += approx_tokens_used;
            }

            let response = llm_response.content;

            // Parse generated commands (accept array or single object) with robust salvage
            let gen_raw = Self::extract_json(&response)?;

            // Validate JSON completeness before parsing
            let trimmed_gen = gen_raw.trim();
            if !trimmed_gen.ends_with('}') && !trimmed_gen.ends_with(']') {
                tracing::warn!(
                    raw_json_len = gen_raw.len(),
                    last_50_chars = %gen_raw.chars().rev().take(50).collect::<Vec<_>>().iter().rev().collect::<String>(),
                    "Generated commands JSON appears incomplete (doesn't end with }} or ])"
                );
            }

            // Attempt direct parse
            let gen_val: serde_json::Value = match serde_json::from_str(&gen_raw) {
                Ok(v) => v,
                Err(first_err) => {
                    // Log the FULL raw JSON for debugging
                    tracing::error!(
                        parse_error = %first_err,
                        raw_json_len = gen_raw.len(),
                        full_raw_json = %gen_raw,
                        "Failed to parse generated commands JSON"
                    );

                    // Try fixing common JSON issues before more complex repairs
                    let quick_fixed = fix_common_json_issues(&gen_raw);
                    if let Ok(v_fixed) = serde_json::from_str::<serde_json::Value>(&quick_fixed) {
                        tracing::info!("Successfully parsed JSON after quick fixes");
                        v_fixed
                    } else {
                        // Try trimming to a balanced JSON block
                        if let Some(trimmed) = Self::trim_to_balanced_json_block(&gen_raw) {
                            if let Ok(v2) = serde_json::from_str::<serde_json::Value>(&trimmed) {
                                v2
                            } else {
                                // Try sanitizing control characters within strings
                                let sanitized = sanitize_json_control_chars(&trimmed);
                                match serde_json::from_str::<serde_json::Value>(&sanitized) {
                                    Ok(v3) => v3,
                                    Err(_) => {
                                        // Last resort: request JSON repair
                                        let repair_prompt = r#"You will receive a possibly malformed JSON array of Godoty commands.
Return ONLY a valid JSON array of command objects (no extra text).
Ensure all strings escape control characters correctly (e.g., use \\n, \\t).
Do NOT add extra closing braces - each object should have exactly one closing brace."#;
                                        let repaired = self
                                            .call_llm_with_agent_type(
                                                repair_prompt,
                                                &gen_raw,
                                                Some(AgentType::Orchestrator),
                                            )
                                            .await?;
                                        let repaired_json = Self::extract_json(&repaired)?;
                                        let repaired_sanitized =
                                            sanitize_json_control_chars(&repaired_json);
                                        serde_json::from_str::<serde_json::Value>(&repaired_sanitized).map_err(|e| {
                                            tracing::error!(full_repaired_json = %repaired_sanitized, "Failed to parse repaired commands JSON");
                                            anyhow::anyhow!("Failed to parse generated commands JSON: {}. First error: {}. See logs for full JSON.", e, first_err)
                                        })?
                                    }
                                }
                            }
                        } else {
                            // No balanced block; try sanitization directly
                            let sanitized = sanitize_json_control_chars(&gen_raw);
                            match serde_json::from_str::<serde_json::Value>(&sanitized) {
                                Ok(v3) => v3,
                                Err(e) => {
                                    tracing::error!(full_sanitized_json = %sanitized, "Failed to parse sanitized commands JSON");
                                    return Err(anyhow::anyhow!("Failed to parse generated commands JSON: {}. First error: {}. See logs for full JSON.", e, first_err));
                                }
                            }
                        }
                    }
                }
            };
            let generated_commands: Vec<Value> = match gen_val {
                serde_json::Value::Array(arr) => arr,
                serde_json::Value::Object(_) => vec![gen_val],
                other => {
                    return Err(anyhow::anyhow!(format!(
                        "Expected JSON array or object for generated commands, got {}",
                        other
                    )))
                }
            };
            metrics.commands_generated = generated_commands.len() as u32;
            tracing::debug!(
                attempt = retry + 1,
                commands_generated = metrics.commands_generated,
                generation_tokens = metrics.generation_tokens,
                "Code generation completed"
            );

            thoughts.push(AgentThought {
                step: thoughts.len() + 1,
                thought: format!(
                    "Generated {} commands (attempt {})",
                    generated_commands.len(),
                    retry + 1
                ),
                action: Some("command_generation".to_string()),
                observation: Some("Commands ready for validation".to_string()),
            });
            metrics.reasoning_steps += 1;

            // Step 4: Validation Agent - Validate commands
            iteration += 1;
            self.guardrails.check_iteration_limit(iteration)?;

            // First, use guardrails for basic validation
            let guardrail_validation = self.guardrails.validate_commands(&generated_commands)?;

            if !guardrail_validation.valid {
                metrics.validation_errors += guardrail_validation.errors.len() as u32;
                metrics.validation_warnings += guardrail_validation.warnings.len() as u32;
                tracing::warn!(
                    errors = metrics.validation_errors,
                    warnings = metrics.validation_warnings,
                    attempt = retry + 1,
                    "Guardrail validation failed"
                );

                thoughts.push(AgentThought {
                    step: thoughts.len() + 1,
                    thought: format!(
                        "Guardrail validation failed with {} errors",
                        guardrail_validation.errors.len()
                    ),
                    action: Some("guardrail_validation".to_string()),
                    observation: Some(guardrail_validation.errors.join("; ")),
                });
                metrics.reasoning_steps += 1;

                if retry < max_retries {
                    validation_result = Some(guardrail_validation);
                    metrics.retry_attempts += 1;
                    continue;
                } else {
                    return Err(anyhow::anyhow!(
                        "Validation failed after {} retries: {:?}",
                        max_retries,
                        guardrail_validation.errors
                    ));
                }
            }

            // Guardrails passed; accept generated commands directly
            commands = generated_commands;
            metrics.commands_validated = commands.len() as u32;
            break;
        }

        // Check token budget
        metrics.total_tokens = metrics.planning_tokens
            + metrics.generation_tokens
            + metrics.validation_tokens
            + metrics.documentation_tokens;
        self.guardrails.check_token_budget(metrics.total_tokens)?;

        // Record request for rate limiting
        self.guardrails.record_request(metrics.total_tokens).await;

        // Return response (metrics will be finalized and saved by execute())
        Ok(AgentResponse {
            commands,
            thoughts,
            plan,
            metrics: None, // Will be set by execute()
        })
    }



    /// Call the LLM API with optional agent type for factory-based routing
    async fn call_llm_with_agent_type(
        &self,
        system_prompt: &str,
        user_input: &str,
        agent_type: Option<AgentType>,
    ) -> Result<String> {
        // If LlmFactory is configured and agent_type is provided, use it
        if let (Some(factory), Some(ref agent_type)) = (&self.llm_factory, agent_type) {
            let client = factory.create_client_for_agent(agent_type.clone())?;
            let sys_prev = system_prompt.chars().take(200).collect::<String>();
            let user_prev = user_input.chars().take(200).collect::<String>();
            tracing::debug!(
                agent_type = ?agent_type,
                model = %client.model_identifier(),
                endpoint = %client.endpoint(),
                system_prompt_preview = %sys_prev,
                user_input_preview = %user_prev,
                "Agent LLM invocation"
            );
            return client
                .generate_response_streaming_with_tools(system_prompt, user_input)
                .await;
        }

        // Fallback to default OpenRouter implementation
        self.call_llm_default(system_prompt, user_input).await
    }


    /// Default LLM implementation using OpenRouter
    async fn call_llm_default(&self, system_prompt: &str, user_input: &str) -> Result<String> {
        #[derive(Serialize)]
        struct ChatRequest {
            model: String,
            messages: Vec<ChatMessage>,
            temperature: f32,
            max_tokens: i32,
        }

        #[derive(Serialize, Deserialize)]
        struct ChatMessage {
            role: String,
            content: String,
        }

        #[derive(Deserialize)]
        struct ChatResponse {
            choices: Vec<Choice>,
            #[serde(default)]
            usage: Option<Usage>,
        }

        #[derive(Deserialize)]
        struct Choice {
            message: ChatMessage,
            #[serde(default)]
            finish_reason: Option<String>,
        }

        #[derive(Debug, Deserialize)]
        struct Usage {
            #[allow(dead_code)]
            #[serde(default)]
            prompt_tokens: u32,
            #[allow(dead_code)]
            #[serde(default)]
            completion_tokens: u32,
            #[allow(dead_code)]
            #[serde(default)]
            total_tokens: u32,
        }

        let request = ChatRequest {
            model: "minimax/minimax-m2:free".to_string(),
            messages: vec![
                ChatMessage {
                    role: "system".to_string(),
                    content: system_prompt.to_string(),
                },
                ChatMessage {
                    role: "user".to_string(),
                    content: user_input.to_string(),
                },
            ],
            temperature: 0.7,
            max_tokens: 16384, // Increased from 8192 to prevent truncation
        };

        let sys_prev = system_prompt.chars().take(200).collect::<String>();
        let user_prev = user_input.chars().take(200).collect::<String>();
        tracing::warn!("Using default LLM fallback path; configuration-based factory not applied. Consider configuring AgentLlmConfig and ApiKeyStore.");
        tracing::debug!(
            provider = "OpenRouter",
            model = %"minimax/minimax-m2:free",
            endpoint = "https://openrouter.ai/api/v1/chat/completions",
            system_prompt_preview = %sys_prev,
            user_input_preview = %user_prev,
            "Agent LLM invocation (fallback)"
        );

        let response = self
            .client
            .post("https://openrouter.ai/api/v1/chat/completions")
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", "application/json")
            .header("HTTP-Referer", "https://github.com/godoty/godoty")
            .header("X-Title", "Godoty AI Assistant")
            .json(&request)
            .send()
            .await?;

        if !response.status().is_success() {
            return Err(anyhow::anyhow!(
                "LLM API request failed: {}",
                response.status()
            ));
        }

        let response_text = response.text().await?;
        let chat_response: ChatResponse = serde_json::from_str(&response_text).map_err(|e| {
            let preview = response_text.chars().take(500).collect::<String>();
            anyhow::anyhow!(
                "Failed to parse LLM chat response JSON: {}. Raw preview: {}",
                e,
                preview
            )
        })?;

        if let Some(choice) = chat_response.choices.first() {
            // Check if response was truncated due to token limit
            if let Some(ref finish_reason) = choice.finish_reason {
                if finish_reason == "length" {
                    tracing::warn!(
                        usage = ?chat_response.usage,
                        response_len = response_text.len(),
                        "LLM response was truncated due to max_tokens limit. Consider increasing max_tokens or reducing prompt size."
                    );
                    // Log the full response for debugging
                    tracing::debug!(full_response = %response_text, "Full truncated response");
                }
            }

            Ok(choice.message.content.clone())
        } else {
            Err(anyhow::anyhow!("No response from LLM"))
        }
    }

    /// Extract JSON from response
    fn extract_json(content: &str) -> Result<String> {
        // Trim and remove leading BOM/zero-width characters that can break JSON
        let mut s = content.trim();
        // Strip common leading invisible characters (BOM, ZWSP, ZWNJ, ZWJ, WJ)
        while let Some(ch) = s.chars().next() {
            match ch {
                '\u{feff}' | '\u{200B}' | '\u{200C}' | '\u{200D}' | '\u{2060}' => {
                    s = &s[ch.len_utf8()..];
                }
                _ => break,
            }
        }

        // Prefer fenced code blocks labeled json (handle common case-insensitive variants)
        if let Some(pos) = s.find("```json") {
            let json_start = pos + 7;
            if let Some(end_offset) = s[json_start..].find("```") {
                let json_end = json_start + end_offset;
                let block = s[json_start..json_end].trim();
                if !block.is_empty() {
                    return Ok(block.to_string());
                }
            }
        }
        if let Some(pos) = s.find("```JSON") {
            let json_start = pos + 7;
            if let Some(end_offset) = s[json_start..].find("```") {
                let json_end = json_start + end_offset;
                let block = s[json_start..json_end].trim();
                if !block.is_empty() {
                    return Ok(block.to_string());
                }
            }
        }

        // Fallback: first fenced block of any type that looks like JSON
        if let Some(start) = s.find("```") {
            let first_block_start = start + 3;
            if let Some(end) = s[first_block_start..].find("```") {
                let json_end = first_block_start + end;
                let block = s[first_block_start..json_end].trim();
                if (block.starts_with('{') || block.starts_with('[')) && !block.is_empty() {
                    return Ok(block.to_string());
                }
            }
        }

        // Try extracting array or object by outermost brackets/braces
        if let Some(array_start) = s.find('[') {
            if let Some(array_end) = s.rfind(']') {
                if array_end > array_start {
                    let candidate = s[array_start..=array_end].trim();
                    if !candidate.is_empty() {
                        return Ok(candidate.to_string());
                    }
                }
            }
        }
        if let Some(obj_start) = s.find('{') {
            if let Some(obj_end) = s.rfind('}') {
                if obj_end > obj_start {
                    let candidate = s[obj_start..=obj_end].trim();
                    if !candidate.is_empty() {
                        return Ok(candidate.to_string());
                    }
                }
            }
        }

        // If we got here, we didn't find a JSON object/array
        let preview: String = s.chars().take(200).collect();
        Err(anyhow::anyhow!(
            "No JSON object/array found in response (first 200 chars): {}",
            preview
        ))
    }

    /// Trim to the first balanced JSON object or array within the given string.
    /// Returns Some(json_substring) if a balanced block is found; otherwise None.
    #[allow(dead_code)] // JSON parsing utility for future enhancement
    fn trim_to_balanced_json_block(s: &str) -> Option<String> {
        let bytes = s.as_bytes();

        // Find first '{' or '['
        let mut start = None;
        for (i, &b) in bytes.iter().enumerate() {
            if b == b'{' || b == b'[' {
                start = Some((i, b));
                break;
            }
        }
        let (start_idx, open_b) = start?;
        let (open_ch, close_ch) = if open_b == b'{' {
            ('{', '}')
        } else {
            ('[', ']')
        };

        // Scan for matching close using depth, respecting strings and escapes
        let mut depth: i32 = 0;
        let mut in_string = false;
        let mut escaped = false;
        for (offset, ch) in s[start_idx..].char_indices() {
            if in_string {
                if escaped {
                    escaped = false;
                    continue;
                }
                match ch {
                    '\\' => escaped = true,
                    '"' => in_string = false,
                    _ => {}
                }
                continue;
            }
            match ch {
                '"' => in_string = true,

                c if c == open_ch => depth += 1,
                c if c == close_ch => {
                    depth -= 1;
                    if depth == 0 {
                        let end_abs = start_idx + offset;
                        return Some(s[start_idx..=end_abs].to_string());
                    }
                }
                _ => {}
            }
        }
        None
    }

    /// Initialize iterative execution - creates initial plan and state
    #[tracing::instrument(skip(self, context, mcp_client, config))]
    pub async fn initialize_iterative_execution(
        &self,
        context: &AgentContext,
        mcp_client: &mut Option<McpClient>,
        config: Option<&AgentLlmConfig>,
    ) -> Result<IterativeExecutionState> {
        tracing::info!("Initializing iterative execution");

        // Create project context string
        let project_context = format!(
            "Total Scenes: {}\nTotal Scripts: {}",
            context.project_index.scenes.len(),
            context.project_index.scripts.len()
        );

        // Build comprehensive context
        let ctx_engine = ContextEngine::new(&self.api_key);
        let _ = ctx_engine.prefetch_common_godot_docs().await;
        let comp_ctx = ctx_engine
            .build_comprehensive_context(
                &context.user_input,
                &context.project_index,
                None,
                8,
            )
            .await
            .unwrap_or_else(|_| crate::context_engine::ComprehensiveContext {
                godot_docs: String::new(),
                project_context: project_context.clone(),
                chat_history: String::new(),
                recent_messages: vec![],
                context_query: context.user_input.clone(),
                visual_analysis: None,
            });
        let formatted_context_for_ai = ctx_engine.format_context_for_ai(&comp_ctx);

        // Prepare visual context string
        let _visual_context_str = context.visual_context.game_screenshot_path.as_ref()
            .map(|game_path| format!("Game Debug Screenshot: {}", game_path));

        // Use orchestrator to create initial plan
        let orchestrator = OrchestratorAgent::new(&self.api_key)
            .with_llm_factory(self.llm_factory.clone());
        let orch_context = AgentExecutionContext {
            user_input: context.user_input.clone(),
            project_context: formatted_context_for_ai.clone(),
            previous_output: None,
            dynamic_context_provider: None,
            project_path: None,
        };

        // Use tool calling mode if enabled in config (default is true)
        let use_tool_calling = config.map(|c| c.enable_tool_calling).unwrap_or(true);
        let orch_output = if use_tool_calling && mcp_client.is_some() {
            orchestrator.execute_with_tools(&orch_context, mcp_client).await?
        } else {
            orchestrator.execute(&orch_context).await?
        };

        // Parse orchestrator output for plan
        let mut plan_opt: Option<ExecutionPlan> = None;
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(&orch_output.content) {
            if let Some(ip) = v.get("initial_plan") {
                if ip.is_object() {
                    if let Ok(p) = serde_json::from_value::<ExecutionPlan>(ip.clone()) {
                        plan_opt = Some(p);
                    }
                }
            }
        }

        // Create plan or use fallback
        let plan = plan_opt.unwrap_or_else(|| ExecutionPlan {
            reasoning: "Iterative execution plan".to_string(),
            metadata: None,
            phases: vec![],
            steps: vec![PlanStep {
                step_number: 1,
                description: "Execute commands iteratively based on feedback".to_string(),
                commands_needed: vec![],
                step_id: String::new(),
                explanation: String::new(),
                required_tools: vec![],
                expected_outcome: String::new(),
                success_criteria: vec![],
                dependencies: vec![],
                error_recovery: vec![],
                estimated_time_minutes: 0,
                safety_considerations: vec![],
            }],
            estimated_complexity: "medium".to_string(),
            overall_goal: String::new(),
            success_criteria: vec![],
            estimated_duration: None,
            complexity: None,
            preconditions: vec![],
            post_conditions: vec![],
            fallback_strategies: vec![],
            plan_id: String::new(),
        });

        // Convert orchestrator thoughts
        let mut thoughts = Vec::new();
        for orch_thought in orch_output.thoughts.iter() {
            thoughts.push(AgentThought {
                step: thoughts.len() + 1,
                thought: format!("[{}] {}", orch_thought.phase, orch_thought.insight),
                action: Some("orchestrator".to_string()),
                observation: Some(format!("Confidence: {:.0}%", orch_thought.confidence * 100.0)),
            });
        }

        Ok(IterativeExecutionState {
            plan,
            thoughts,
            executed_commands: Vec::new(),
            execution_results: Vec::new(),
            current_step: 0,
            is_complete: false,
            session_id: uuid::Uuid::new_v4().to_string(),
        })
    }

    /// Generate next command based on current state and previous results
    #[tracing::instrument(skip(self, context, state))]
    pub async fn generate_next_command(
        &self,
        context: &AgentContext,
        state: &IterativeExecutionState,
    ) -> Result<IterativeStepResponse> {
        tracing::info!(
            step = state.current_step,
            executed = state.executed_commands.len(),
            "Generating next command"
        );

        // Check if we should stop
        if state.is_complete {
            return Ok(IterativeStepResponse {
                command: None,
                thought: None,
                is_complete: true,
                state: state.clone(),
            });
        }

        // Build context with execution history
        let execution_history = if !state.execution_results.is_empty() {
            let mut history = String::from("\n# Previous Command Execution Results:\n");
            for (idx, result) in state.execution_results.iter().enumerate() {
                history.push_str(&format!("\nCommand {}: ", idx + 1));
                if let Some(cmd) = state.executed_commands.get(idx) {
                    history.push_str(&format!("{}\n", serde_json::to_string(cmd).unwrap_or_default()));
                }
                history.push_str(&format!("Result: {}\n", serde_json::to_string(result).unwrap_or_default()));
            }
            history
        } else {
            String::new()
        };

        // Use orchestrator to generate next command
        let system_prompt = format!(
            r#"You are generating the NEXT SINGLE COMMAND for a Godot project task.

# Current Plan
{}

# Execution Progress
- Current Step: {} / {}
- Commands Executed: {}
{}

# Your Task
Generate EXACTLY ONE command to execute next, or signal completion.

Return JSON in this format:
{{
  "next_command": {{"action": "...", ...}} | null,
  "reasoning": "why this command or why complete",
  "is_complete": boolean
}}

Rules:
- Generate ONE command at a time
- Consider previous execution results
- If task is complete, set is_complete=true and next_command=null
- Use available Godoty commands: create_node, modify_node, attach_script, open_scene, play, capture_game_screenshot, desktop_commander, etc.
"#,
            serde_json::to_string_pretty(&state.plan).unwrap_or_default(),
            state.current_step + 1,
            state.plan.steps.len(),
            state.executed_commands.len(),
            execution_history
        );

        let user_msg = format!(
            "User Request: {}\nGenerate the next command based on the plan and execution history.",
            context.user_input
        );

        let response = self.call_llm_with_agent_type(&system_prompt, &user_msg, Some(AgentType::Orchestrator)).await?;

        // Parse response
        let json_str = Self::extract_json(&response)?;
        let parsed: serde_json::Value = serde_json::from_str(&json_str)?;

        let next_command = parsed.get("next_command").and_then(|v| {
            if v.is_null() {
                None
            } else {
                Some(v.clone())
            }
        });

        let is_complete = parsed
            .get("is_complete")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);

        let reasoning = parsed
            .get("reasoning")
            .and_then(|v| v.as_str())
            .unwrap_or("No reasoning provided")
            .to_string();

        // Create thought
        let thought = AgentThought {
            step: state.thoughts.len() + 1,
            thought: reasoning,
            action: Some("generate_command".to_string()),
            observation: if is_complete {
                Some("Task complete".to_string())
            } else {
                Some(format!("Generated command: {:?}", next_command))
            },
        };

        // Update state
        let mut new_state = state.clone();
        new_state.thoughts.push(thought.clone());
        new_state.is_complete = is_complete || next_command.is_none();

        Ok(IterativeStepResponse {
            command: next_command,
            thought: Some(thought),
            is_complete: new_state.is_complete,
            state: new_state,
        })
    }

    /// Record execution result and update state
    pub fn record_execution_result(
        &self,
        state: &mut IterativeExecutionState,
        command: Value,
        result: Value,
    ) {
        state.executed_commands.push(command);
        state.execution_results.push(result);
        state.current_step += 1;
    }
}

// Helper deserializer: accept either a string or any JSON value and convert to string
fn string_or_value<'de, D>(deserializer: D) -> std::result::Result<String, D::Error>
where
    D: serde::de::Deserializer<'de>,
{
    let v = serde_json::Value::deserialize(deserializer)?;
    match v {
        serde_json::Value::String(s) => Ok(s),
        other => Ok(other.to_string()),
    }
}

// Helper deserializer: accept either a single object or an array of objects and return Vec<T>
fn one_or_many<'de, D, T>(deserializer: D) -> std::result::Result<Vec<T>, D::Error>
where
    D: serde::de::Deserializer<'de>,
    T: serde::de::DeserializeOwned,
{
    let v = serde_json::Value::deserialize(deserializer)?;
    match v {
        serde_json::Value::Array(arr) => {
            let mut out = Vec::with_capacity(arr.len());
            for item in arr {
                out.push(serde_json::from_value(item).map_err(serde::de::Error::custom)?);
            }
            Ok(out)
        }
        serde_json::Value::Object(_) => {
            let t: T = serde_json::from_value(v).map_err(serde::de::Error::custom)?;
            Ok(vec![t])
        }
        other => Err(serde::de::Error::custom(format!(
            "expected array or object, got {}",
            other
        ))),
    }
}

// Helper deserializer: accept a single string or an array of strings and return Vec<String>
fn string_or_vec<'de, D>(deserializer: D) -> std::result::Result<Vec<String>, D::Error>
where
    D: serde::de::Deserializer<'de>,
{
    let v = serde_json::Value::deserialize(deserializer)?;
    match v {
        serde_json::Value::String(s) => Ok(vec![s]),
        serde_json::Value::Array(arr) => {
            let mut out = Vec::with_capacity(arr.len());
            for item in arr {
                match item {
                    serde_json::Value::String(s) => out.push(s),
                    other => {
                        return Err(serde::de::Error::custom(format!(
                            "expected string in array, got {}",
                            other
                        )))
                    }
                }
            }
            Ok(out)
        }
        other => Err(serde::de::Error::custom(format!(
            "expected string or array of strings, got {}",
            other
        ))),
    }
}


// Helper: accept number or numeric string and return usize
fn usize_or_string<'de, D>(deserializer: D) -> std::result::Result<usize, D::Error>
where
    D: serde::de::Deserializer<'de>,
{
    let v = serde_json::Value::deserialize(deserializer)?;
    match v {
        serde_json::Value::Number(n) => n
            .as_u64()
            .ok_or_else(|| serde::de::Error::custom("expected unsigned integer for step_number"))
            .map(|u| u as usize),
        serde_json::Value::String(s) => s.parse::<usize>().map_err(serde::de::Error::custom),
        other => Err(serde::de::Error::custom(format!(
            "expected integer or numeric string for step_number, got {}",
            other
        ))),
    }
}

/// Fix common JSON issues like extra closing braces
/// This function removes duplicate closing braces that appear in patterns like }}}
fn fix_common_json_issues(s: &str) -> String {
    let mut result = String::with_capacity(s.len());
    let mut in_string = false;
    let mut escaped = false;
    let chars: Vec<char> = s.chars().collect();
    let mut i = 0;

    while i < chars.len() {
        let ch = chars[i];

        if in_string {
            result.push(ch);
            if escaped {
                escaped = false;
            } else if ch == '\\' {
                escaped = true;
            } else if ch == '"' {
                in_string = false;
            }
            i += 1;
        } else {
            match ch {
                '"' => {
                    result.push(ch);
                    in_string = true;
                    i += 1;
                }
                '}' => {
                    // Count consecutive closing braces
                    let mut brace_count = 1;
                    let mut j = i + 1;
                    while j < chars.len() && chars[j] == '}' {
                        brace_count += 1;
                        j += 1;
                    }

                    // If we have 3 or more consecutive closing braces, it's likely an error
                    // Reduce to 2 closing braces (for nested objects)
                    if brace_count >= 3 {
                        // Check what comes after the braces
                        let after_braces = if j < chars.len() { Some(chars[j]) } else { None };

                        // If followed by comma or closing bracket, reduce to 2 braces
                        if matches!(after_braces, Some(',') | Some(']') | None) {
                            result.push('}');
                            result.push('}');
                            i = j; // Skip all the extra braces
                            continue;
                        }
                    }

                    // Normal case: just add the brace
                    result.push(ch);
                    i += 1;
                }
                _ => {
                    result.push(ch);
                    i += 1;
                }
            }
        }
    }

    result
}

/// Sanitize JSON by escaping ASCII control characters inside quoted strings.
fn sanitize_json_control_chars(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let mut in_string = false;
    let mut escaped = false;
    for ch in s.chars() {
        if in_string {
            if escaped {
                out.push(ch);
                escaped = false;
                continue;
            }
            match ch {
                '\\' => {
                    out.push('\\');
                    escaped = true;
                }
                '"' => {
                    out.push('"');
                    in_string = false;
                }
                c if (c as u32) <= 0x1F => match c {
                    '\n' => out.push_str("\\n"),
                    '\r' => out.push_str("\\r"),
                    '\t' => out.push_str("\\t"),
                    _ => out.push_str(&format!("\\u{:04x}", c as u32)),
                },
                _ => out.push(ch),
            }
        } else {
            match ch {
                '"' => {
                    out.push('"');
                    in_string = true;
                }
                _ => out.push(ch),
            }
        }
    }
    out
}

/// Execution plan created by the planner agent (Enhanced for new architecture)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionPlan {
    /// Legacy reasoning field for backward compatibility
    #[serde(deserialize_with = "string_or_value")]
    pub reasoning: String,

    /// Enhanced plan metadata (new field)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub metadata: Option<PlanMetadata>,

    /// Hierarchical execution phases (new architecture)
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub phases: Vec<ExecutionPhase>,

    /// Plan steps (legacy field for backward compatibility)
    #[serde(deserialize_with = "one_or_many")]
    pub steps: Vec<PlanStep>,

    /// Legacy complexity field (for backward compatibility)
    #[serde(deserialize_with = "string_or_value")]
    pub estimated_complexity: String,

    /// Overall goal of the plan (new field)
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub overall_goal: String,

    /// Success criteria for the entire plan (new field)
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub success_criteria: Vec<String>,

    /// Estimated duration for plan completion (new field)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub estimated_duration: Option<String>,

    /// Complexity assessment (new field)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub complexity: Option<String>,

    /// Pre-conditions that must be met (new field)
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub preconditions: Vec<Precondition>,

    /// Post-conditions for validation (new field)
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub post_conditions: Vec<PostCondition>,

    /// Fallback strategies (new field)
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub fallback_strategies: Vec<FallbackStrategy>,

    /// Plan identifier (new field)
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub plan_id: String,
}

/// Enhanced plan step for new architecture (backward compatible)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanStep {
    /// Step number (legacy field)
    #[serde(deserialize_with = "usize_or_string")]
    pub step_number: usize,

    /// Step description (legacy field)
    #[serde(deserialize_with = "string_or_value")]
    pub description: String,

    /// Commands needed (legacy field)
    #[serde(deserialize_with = "string_or_vec")]
    pub commands_needed: Vec<String>,

    /// Step identifier (new field)
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub step_id: String,

    /// Detailed explanation (new field)
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub explanation: String,

    /// Tools required for this step (new field)
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub required_tools: Vec<String>,

    /// Expected outcome (new field)
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub expected_outcome: String,

    /// Success criteria (new field)
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub success_criteria: Vec<String>,

    /// Dependencies on other steps (new field)
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub dependencies: Vec<String>,

    /// Error recovery strategies (new field)
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub error_recovery: Vec<String>,

    /// Estimated time for this step in minutes (new field)
    #[serde(default)]
    pub estimated_time_minutes: u32,

    /// Safety considerations (new field)
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub safety_considerations: Vec<String>,
}

/// Plan metadata (new structure)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanMetadata {
    /// Plan title
    pub title: String,

    /// Plan description
    pub description: String,

    /// Estimated complexity
    pub complexity: String,

    /// Estimated time to complete in minutes
    pub estimated_time_minutes: u32,

    /// Required tools
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub required_tools: Vec<String>,

    /// Risk assessment
    #[serde(default)]
    pub risk_level: String,
}

/// Pre-conditions for plan execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Precondition {
    /// Condition description
    pub description: String,

    /// How to verify the condition
    pub verification_method: String,

    /// Whether condition is mandatory
    #[serde(default)]
    pub mandatory: bool,
}

/// Post-conditions for plan validation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PostCondition {
    /// Condition description
    pub description: String,

    /// How to verify the condition
    pub verification_method: String,

    /// Success criteria
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub success_criteria: Vec<String>,
}

/// Fallback strategy for plan execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FallbackStrategy {
    /// Strategy name
    pub name: String,

    /// When to use this strategy
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub trigger_conditions: Vec<String>,

    /// Alternative steps
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub alternative_steps: Vec<String>,

    /// Expected success rate
    #[serde(default)]
    pub expected_success_rate: f32,
}

/// Hierarchical execution phase containing multiple tasks
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionPhase {
    /// Phase identifier
    pub id: String,

    /// Phase name
    pub name: String,

    /// Phase description
    pub description: String,

    /// Tasks within this phase
    pub tasks: Vec<PlanTask>,

    /// Dependencies on other phases (phase IDs)
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub dependencies: Vec<String>,

    /// Validation criteria for phase completion
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub validation_criteria: Vec<String>,

    /// Phase status
    #[serde(default)]
    pub status: PhaseStatus,
}

/// Individual task within a phase
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanTask {
    /// Task identifier
    pub id: String,

    /// Task name
    pub name: String,

    /// Task description
    pub description: String,

    /// Tools required for this task
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub required_tools: Vec<String>,

    /// Task dependencies
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub dependencies: Vec<TaskDependency>,

    /// Acceptance criteria for task completion
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub acceptance_criteria: Vec<String>,

    /// Preconditions that must be met
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub preconditions: Vec<String>,

    /// Post-conditions after task completion
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub post_conditions: Vec<String>,

    /// Estimated number of steps
    #[serde(default)]
    pub estimated_steps: u32,

    /// Task status
    #[serde(default)]
    pub status: TaskStatus,
}

/// Task dependency relationship
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskDependency {
    /// ID of the task this depends on
    pub task_id: String,

    /// Type of dependency
    pub dependency_type: DependencyType,

    /// Optional description of the dependency
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub description: String,
}

/// Type of dependency between tasks
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum DependencyType {
    /// Must complete before this task starts
    Sequential,

    /// Can run in parallel
    Parallel,

    /// Conditionally required
    Conditional,
}

impl Default for DependencyType {
    fn default() -> Self {
        DependencyType::Sequential
    }
}

/// Phase execution status
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum PhaseStatus {
    Pending,
    InProgress,
    Completed,
    Failed,
    Skipped,
}

impl Default for PhaseStatus {
    fn default() -> Self {
        PhaseStatus::Pending
    }
}

/// Task execution status
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum TaskStatus {
    Pending,
    InProgress,
    Completed,
    Failed,
    Skipped,
}

impl Default for TaskStatus {
    fn default() -> Self {
        TaskStatus::Pending
    }
}

/// Response from the agentic workflow
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentResponse {
    pub commands: Vec<Value>,
    pub thoughts: Vec<AgentThought>,
    pub plan: ExecutionPlan,
    pub metrics: Option<WorkflowMetrics>,
}

/// State for iterative command execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IterativeExecutionState {
    pub plan: ExecutionPlan,
    pub thoughts: Vec<AgentThought>,
    pub executed_commands: Vec<Value>,
    pub execution_results: Vec<Value>,
    pub current_step: usize,
    pub is_complete: bool,
    pub session_id: String,
}

/// Response from a single iterative step
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IterativeStepResponse {
    pub command: Option<Value>,
    pub thought: Option<AgentThought>,
    pub is_complete: bool,
    pub state: IterativeExecutionState,
}
