use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use reqwest::Client;
use crate::knowledge_base::KnowledgeBase;
use crate::project_indexer::ProjectIndex;
use crate::metrics::{WorkflowMetrics, MetricsStore};
use crate::guardrails::{Guardrails, GuardrailConfig, ValidationResult};
use crate::strands_agent::{
    StrandsAgent, PlanningAgent, CodeGenerationAgent, ValidationAgent,
    DocumentationAgent, GDScriptAgent, AgentExecutionContext,
};

/// Represents a thought or reasoning step in the agent's decision-making process
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentThought {
    pub step: usize,
    pub thought: String,
    pub action: Option<String>,
    pub observation: Option<String>,
}

/// Agent context containing all information needed for decision-making
#[derive(Clone)]
pub struct AgentContext {
    pub user_input: String,
    pub project_index: ProjectIndex,
    pub chat_history: String,
    pub plugin_kb: KnowledgeBase,
    pub docs_kb: KnowledgeBase,
}

/// Agentic workflow orchestrator with Strands agents
#[derive(Clone)]
pub struct AgenticWorkflow {
    api_key: String,
    client: Client,
    guardrails: Guardrails,
    metrics_store: Option<MetricsStore>,
}

impl AgenticWorkflow {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
            guardrails: Guardrails::with_defaults(),
            metrics_store: None,
        }
    }

    pub fn with_guardrails(api_key: &str, config: GuardrailConfig) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
            guardrails: Guardrails::new(config),
            metrics_store: None,
        }
    }

    pub fn with_metrics_store(mut self, metrics_store: MetricsStore) -> Self {
        self.metrics_store = Some(metrics_store);
        self
    }

    /// Execute the agentic workflow with Strands agents
    #[tracing::instrument(skip(self, context))]
    pub async fn execute(
        &self,
        context: &AgentContext,
    ) -> Result<AgentResponse> {
        // Initialize metrics
        let request_id = uuid::Uuid::new_v4().to_string();
        let mut metrics = WorkflowMetrics::new(request_id.clone(), context.user_input.clone());

        // Trace start of workflow
        let input_preview: String = context.user_input.chars().take(120).collect();
        tracing::info!(%request_id, input_len = context.user_input.len(), input_preview = %input_preview, "Starting agentic workflow");

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

        // Step 1: Documentation Agent - Retrieve relevant Godot documentation
        let doc_agent = DocumentationAgent::new(&self.api_key);
        let doc_context = AgentExecutionContext {
            user_input: context.user_input.clone(),
            chat_history: context.chat_history.clone(),
            project_context: project_context.clone(),
            plugin_kb: context.plugin_kb.clone(),
            docs_kb: context.docs_kb.clone(),
            execution_plan: None,
            previous_output: None,
        };

        let doc_start = std::time::Instant::now();
        let doc_output = doc_agent.execute(&doc_context).await?;
        metrics.kb_search_time_ms += doc_start.elapsed().as_millis() as u64;
        metrics.documentation_tokens += doc_output.tokens_used;
        metrics.docs_kb_queries += 1;

        tracing::debug!(
            docs_kb_queries = metrics.docs_kb_queries,
            documentation_tokens = metrics.documentation_tokens,
            kb_search_time_ms = metrics.kb_search_time_ms,
            "Documentation agent completed"
        );

        thoughts.push(AgentThought {
            step: 1,
            thought: "Retrieved relevant Godot documentation".to_string(),
            action: Some("documentation_retrieval".to_string()),
            observation: Some(format!("Retrieved {} docs",
                doc_output.metadata.get("docs_retrieved").and_then(|v| v.as_u64()).unwrap_or(0))),
        });
        metrics.reasoning_steps += 1;

        // Step 2: Planning Agent - Create execution plan
        iteration += 1;
        self.guardrails.check_iteration_limit(iteration)?;

        let planning_agent = PlanningAgent::new(&self.api_key);
        let planning_context = AgentExecutionContext {
            user_input: context.user_input.clone(),
            chat_history: context.chat_history.clone(),
            project_context: project_context.clone(),
            plugin_kb: context.plugin_kb.clone(),
            docs_kb: context.docs_kb.clone(),
            execution_plan: None,
            previous_output: Some(doc_output.content.clone()),
        };

        let plan_start = std::time::Instant::now();
        let plan_output = planning_agent.execute(&planning_context).await?;
        metrics.planning_time_ms = plan_start.elapsed().as_millis() as u64;
        metrics.planning_tokens = plan_output.tokens_used;
        metrics.plugin_kb_queries += plan_output.metadata.get("plugin_docs_retrieved")
            .and_then(|v| v.as_u64()).unwrap_or(0) as u32;
        metrics.docs_kb_queries += plan_output.metadata.get("godot_docs_retrieved")
            .and_then(|v| v.as_u64()).unwrap_or(0) as u32;

        tracing::debug!(
            planning_tokens = metrics.planning_tokens,
            planning_time_ms = metrics.planning_time_ms,
            plugin_kb_queries = metrics.plugin_kb_queries,
            docs_kb_queries = metrics.docs_kb_queries,
            "Planning agent completed"
        );

        // Log planning response preview for debugging truncated/malformed JSON
        let plan_resp_len = plan_output.content.len();
        let plan_preview: String = plan_output.content.chars().take(200).collect();
        tracing::debug!(plan_response_len = plan_resp_len, plan_response_preview = %plan_preview, "Planning agent raw response preview");

        // Parse execution plan with salvage/repair
        let plan_raw = Self::extract_json(&plan_output.content)?;
        let plan: ExecutionPlan = match serde_json::from_str::<ExecutionPlan>(&plan_raw) {
            Ok(p) => p,
            Err(e1) => {
                if let Some(trimmed) = Self::trim_to_balanced_json_block(&plan_raw) {
                    match serde_json::from_str::<ExecutionPlan>(&trimmed) {
                        Ok(p2) => p2,
                        Err(_e2) => {
                            // Last resort: ask LLM to repair malformed JSON into valid object
                            let repair_prompt = r#"You will receive a malformed execution plan as text.
Return ONLY a valid JSON object with this exact shape (no extra text):
{
  "reasoning": string,
  "steps": [{"step_number": number, "description": string, "commands_needed": [string]}],
  "estimated_complexity": "low" | "medium" | "high"
}
Ensure all braces/brackets are closed. No comments or trailing commas."#;
                            let repaired = self.call_llm(repair_prompt, &plan_raw).await?;
                            let repaired_json = Self::extract_json(&repaired)?;
                            serde_json::from_str::<ExecutionPlan>(&repaired_json).map_err(|e3| {
                                let prev = plan_raw.chars().take(500).collect::<String>();
                                anyhow::anyhow!("Failed to parse plan after repair. First error: {}. Raw preview: {}. Repair error: {}", e1, prev, e3)
                            })?
                        }
                    }
                } else {
                    // Could not find a balanced block; attempt repair once
                    let repair_prompt = r#"You will receive a malformed execution plan as text.
Return ONLY a valid JSON object with this exact shape (no extra text):
{
  "reasoning": string,
  "steps": [{"step_number": number, "description": string, "commands_needed": [string]}],
  "estimated_complexity": "low" | "medium" | "high"
}
Ensure all braces/brackets are closed. No comments or trailing commas."#;
                    let repaired = self.call_llm(repair_prompt, &plan_raw).await?;
                    let repaired_json = Self::extract_json(&repaired)?;
                    serde_json::from_str::<ExecutionPlan>(&repaired_json).map_err(|e3| {
                        let prev = plan_raw.chars().take(500).collect::<String>();
                        anyhow::anyhow!("Failed to parse plan after repair. First error: {}. Raw preview: {}. Repair error: {}", e1, prev, e3)
                    })?
                }
            }
        };

        thoughts.push(AgentThought {
            step: 2,
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

            let code_gen_agent = CodeGenerationAgent::new(&self.api_key);
            let code_gen_context = AgentExecutionContext {
                user_input: context.user_input.clone(),
                chat_history: context.chat_history.clone(),
                project_context: project_context.clone(),
                plugin_kb: context.plugin_kb.clone(),
                docs_kb: context.docs_kb.clone(),
                execution_plan: Some(plan.clone()),
                previous_output: validation_result.as_ref().map(|v| {
                    format!("Previous validation errors: {:?}\nPlease fix these issues.", v.errors)
                }),
            };

            let gen_start = std::time::Instant::now();
            let gen_output = code_gen_agent.execute(&code_gen_context).await?;
            metrics.generation_time_ms += gen_start.elapsed().as_millis() as u64;
            metrics.generation_tokens += gen_output.tokens_used;

            // Parse generated commands (accept array or single object) with robust salvage
            let gen_raw = Self::extract_json(&gen_output.content)?;
            // Attempt direct parse
            let gen_val: serde_json::Value = match serde_json::from_str(&gen_raw) {
                Ok(v) => v,
                Err(first_err) => {
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
Ensure all strings escape control characters correctly (e.g., use \\n, \\t)."#;
                                    let repaired = self.call_llm(repair_prompt, &gen_raw).await?;
                                    let repaired_json = Self::extract_json(&repaired)?;
                                    let repaired_sanitized = sanitize_json_control_chars(&repaired_json);
                                    serde_json::from_str::<serde_json::Value>(&repaired_sanitized).map_err(|e| {
                                        let preview = gen_raw.chars().take(500).collect::<String>();
                                        anyhow::anyhow!("Failed to parse generated commands JSON: {}. Raw preview: {}. First error: {}", e, preview, first_err)
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
                                let preview = gen_raw.chars().take(500).collect::<String>();
                                return Err(anyhow::anyhow!("Failed to parse generated commands JSON: {}. Raw preview: {}. First error: {}", e, preview, first_err));
                            }
                        }
                    }
                }
            };
            let generated_commands: Vec<Value> = match gen_val {
                serde_json::Value::Array(arr) => arr,
                serde_json::Value::Object(_) => vec![gen_val],
                other => return Err(anyhow::anyhow!(format!("Expected JSON array or object for generated commands, got {}", other))),
            };
            metrics.commands_generated = generated_commands.len() as u32;
            tracing::debug!(attempt = retry + 1, commands_generated = metrics.commands_generated, generation_tokens = metrics.generation_tokens, "Code generation completed");

            thoughts.push(AgentThought {
                step: thoughts.len() + 1,
                thought: format!("Generated {} commands (attempt {})", generated_commands.len(), retry + 1),
                action: Some("command_generation".to_string()),
                observation: Some(format!("Commands ready for validation")),
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
                tracing::warn!(errors = metrics.validation_errors, warnings = metrics.validation_warnings, attempt = retry + 1, "Guardrail validation failed");

                thoughts.push(AgentThought {
                    step: thoughts.len() + 1,
                    thought: format!("Guardrail validation failed with {} errors", guardrail_validation.errors.len()),
                    action: Some("guardrail_validation".to_string()),
                    observation: Some(guardrail_validation.errors.join("; ")),
                });
                metrics.reasoning_steps += 1;

                if retry < max_retries {
                    validation_result = Some(guardrail_validation);
                    metrics.retry_attempts += 1;
                    continue;
                } else {
                    return Err(anyhow::anyhow!("Validation failed after {} retries: {:?}",
                        max_retries, guardrail_validation.errors));
                }
            }

            // Then use AI validation agent for deeper validation
            let validation_agent = ValidationAgent::new(&self.api_key);
            let validation_context = AgentExecutionContext {
                user_input: context.user_input.clone(),
                chat_history: context.chat_history.clone(),
                project_context: project_context.clone(),
                plugin_kb: context.plugin_kb.clone(),
                docs_kb: context.docs_kb.clone(),
                execution_plan: Some(plan.clone()),
                previous_output: Some(serde_json::to_string(&generated_commands)?),
            };

            let val_start = std::time::Instant::now();
            let val_output = validation_agent.execute(&validation_context).await?;
            metrics.validation_time_ms += val_start.elapsed().as_millis() as u64;
            metrics.validation_tokens += val_output.tokens_used;

            // Parse validation result
            #[derive(Deserialize)]
            struct AIValidationResult {
                valid: bool,
                errors: Vec<String>,
                warnings: Vec<String>,
                #[serde(default, deserialize_with = "opt_one_or_many")]
                validated_commands: Option<Vec<Value>>,
            }

            let val_raw = Self::extract_json(&val_output.content)?;
            let ai_validation: AIValidationResult = serde_json::from_str(&val_raw).map_err(|e| {
                let preview = if val_raw.len() > 500 { &val_raw[..500] } else { &val_raw };
                anyhow::anyhow!("Failed to parse validation JSON: {}. Raw preview: {}", e, preview)
            })?;

            metrics.validation_errors += ai_validation.errors.len() as u32;
            metrics.validation_warnings += ai_validation.warnings.len() as u32;
            tracing::debug!(ai_valid = ai_validation.valid, ai_errors = ai_validation.errors.len(), ai_warnings = ai_validation.warnings.len(), "AI validation completed");

            thoughts.push(AgentThought {
                step: thoughts.len() + 1,
                thought: format!("AI validation: {} errors, {} warnings",
                    ai_validation.errors.len(), ai_validation.warnings.len()),
                action: Some("ai_validation".to_string()),
                observation: Some(if ai_validation.valid {
                    "Commands validated successfully".to_string()
                } else {
                    ai_validation.errors.join("; ")
                }),
            });
            metrics.reasoning_steps += 1;

            if ai_validation.valid {
                commands = ai_validation.validated_commands.unwrap_or(generated_commands);
                metrics.commands_validated = commands.len() as u32;
                break;
            } else if retry < max_retries {
                validation_result = Some(ValidationResult {
                    valid: false,
                    errors: ai_validation.errors,
                    warnings: ai_validation.warnings,
                });
                metrics.retry_attempts += 1;
            } else {
                return Err(anyhow::anyhow!("AI validation failed after {} retries: {:?}",
                    max_retries, ai_validation.errors));
            }
        }

        // Check token budget
        metrics.total_tokens = metrics.planning_tokens + metrics.generation_tokens +
            metrics.validation_tokens + metrics.documentation_tokens;
        self.guardrails.check_token_budget(metrics.total_tokens)?;

        // Record request for rate limiting
        self.guardrails.record_request(metrics.total_tokens).await;

        // Finalize metrics
        metrics.finalize(true, None);
        tracing::info!(total_tokens = metrics.total_tokens, commands_generated = metrics.commands_generated, commands_validated = metrics.commands_validated, retry_attempts = metrics.retry_attempts, "Agentic workflow completed successfully");

        // Save metrics if store is available
        if let Some(store) = &self.metrics_store {
            let _ = store.add_metrics(metrics.clone()).await;
            let _ = store.save_to_disk().await;
        }

        // Get knowledge used
        let plugin_knowledge = context.plugin_kb.search(&context.user_input, 5).await?;
        let docs_knowledge = context.docs_kb.search(&context.user_input, 5).await?;

        Ok(AgentResponse {
            commands,
            thoughts,
            plan,
            knowledge_used: KnowledgeUsed {
                plugin_docs: plugin_knowledge.iter().map(|d| d.id.clone()).collect(),
                godot_docs: docs_knowledge.iter().map(|d| d.id.clone()).collect(),
            },
            metrics: Some(metrics),
        })
    }

    /// Plan the task by breaking it down into steps

    async fn plan_task(
        &self,
        context: &AgentContext,
        plugin_knowledge: &[crate::knowledge_base::KnowledgeDocument],
        docs_knowledge: &[crate::knowledge_base::KnowledgeDocument],
    ) -> Result<ExecutionPlan> {
        let plugin_context = plugin_knowledge.iter()
            .map(|d| format!("- {}: {}", d.id, d.content))
            .collect::<Vec<_>>()
            .join("\n");

        let docs_context = docs_knowledge.iter()
            .map(|d| format!("- {}", d.content.chars().take(200).collect::<String>()))
            .collect::<Vec<_>>()
            .join("\n");

        let system_prompt = format!(r#"You are an AI planning agent for Godot game development.
Your task is to analyze the user's request and create a detailed execution plan.

Available Plugin Commands Context:
{}

Relevant Godot Documentation:
{}

Project Context:
- Total Scenes: {}
- Total Scripts: {}

Create a step-by-step plan to accomplish the user's goal.
Respond with a JSON object containing:
{{
  "reasoning": "Your analysis of the task",
  "steps": [
    {{"step_number": 1, "description": "What to do", "commands_needed": ["command_type1", "command_type2"]}},
    ...
  ],
  "estimated_complexity": "low|medium|high"
}}

STRICT OUTPUT RULES:
- Respond ONLY with a valid JSON object (no prose before/after).
- If you use a code fence, use ```json and include only valid JSON inside.
- No comments, no trailing commas, no ellipses inside JSON.
- Ensure all braces/brackets are closed; keep to <= 8 steps.

"#,
            plugin_context,
            docs_context,
            context.project_index.scenes.len(),
            context.project_index.scripts.len()
        );

        let response = self.call_llm(&system_prompt, &context.user_input).await?;
        // Extract potential JSON from the response (handles code fences and extra text)
        let plan_json = Self::extract_json(&response)?;
        // Parse the plan with salvage/repair
        let plan: ExecutionPlan = match serde_json::from_str::<ExecutionPlan>(&plan_json) {
            Ok(p) => p,
            Err(e1) => {
                if let Some(trimmed) = Self::trim_to_balanced_json_block(&plan_json) {
                    match serde_json::from_str::<ExecutionPlan>(&trimmed) {
                        Ok(p2) => p2,
                        Err(_e2) => {
                            let repair_prompt = r#"You will receive a malformed execution plan as text.
Return ONLY a valid JSON object with this exact shape (no extra text):
{
  "reasoning": string,
  "steps": [{"step_number": number, "description": string, "commands_needed": [string]}],
  "estimated_complexity": "low" | "medium" | "high"
}
Ensure all braces/brackets are closed. No comments or trailing commas."#;
                            let repaired = self.call_llm(repair_prompt, &plan_json).await?;
                            let repaired_json = Self::extract_json(&repaired)?;
                            serde_json::from_str::<ExecutionPlan>(&repaired_json).map_err(|e3| {
                                let prev = plan_json.chars().take(500).collect::<String>();
                                anyhow::anyhow!("Failed to parse plan after repair. First error: {}. Raw preview: {}. Repair error: {}", e1, prev, e3)
                            })?
                        }
                    }
                } else {
                    let repair_prompt = r#"You will receive a malformed execution plan as text.
Return ONLY a valid JSON object with this exact shape (no extra text):
{
  "reasoning": string,
  "steps": [{"step_number": number, "description": string, "commands_needed": [string]}],
  "estimated_complexity": "low" | "medium" | "high"
}
Ensure all braces/brackets are closed. No comments or trailing commas."#;
                    let repaired = self.call_llm(repair_prompt, &plan_json).await?;
                    let repaired_json = Self::extract_json(&repaired)?;
                    serde_json::from_str::<ExecutionPlan>(&repaired_json).map_err(|e3| {
                        let prev = plan_json.chars().take(500).collect::<String>();
                        anyhow::anyhow!("Failed to parse plan after repair. First error: {}. Raw preview: {}. Repair error: {}", e1, prev, e3)
                    })?
                }
            }
        };

        Ok(plan)
    }

    /// Generate commands based on the execution plan
    async fn generate_commands(
        &self,
        context: &AgentContext,
        plan: &ExecutionPlan,
        plugin_knowledge: &[crate::knowledge_base::KnowledgeDocument],
        _docs_knowledge: &[crate::knowledge_base::KnowledgeDocument],
    ) -> Result<Vec<Value>> {
        // Build comprehensive context for command generation
        let plugin_examples = plugin_knowledge.iter()
            .map(|d| d.content.clone())
            .collect::<Vec<_>>()
            .join("\n\n");

        let allowed_actions_list = self.guardrails.config.allowed_command_types.join(", ");

        let system_prompt = format!(r#"You are a command generation agent for Godot.

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
Each command must be a valid JSON object matching the plugin's command schema.
Respond ONLY with the JSON array, no explanations.
"#,
            serde_json::to_string_pretty(plan)?,
            plugin_examples,
            allowed_actions_list
        );

        let response = self.call_llm(&system_prompt, &context.user_input).await?;

        // Extract and parse commands (accept array or single object)
        let raw = Self::extract_json(&response)?;
        let val: serde_json::Value = serde_json::from_str(&raw).map_err(|e| {
            let preview = if raw.len() > 500 { &raw[..500] } else { &raw };
            anyhow::anyhow!("Failed to parse commands JSON: {}. Raw preview: {}", e, preview)
        })?;
        let commands: Vec<Value> = match val {
            serde_json::Value::Array(arr) => arr,
            serde_json::Value::Object(_) => vec![val],
            other => return Err(anyhow::anyhow!(format!("Expected JSON array or object for commands, got {}", other))),
        };

        Ok(commands)
    }

    /// Call the LLM API
    async fn call_llm(&self, system_prompt: &str, user_input: &str) -> Result<String> {
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
        }

        #[derive(Deserialize)]
        struct Choice {
            message: ChatMessage,
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
            max_tokens: 8192,
        };

        let response = self.client
            .post("https://openrouter.ai/api/v1/chat/completions")
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", "application/json")
            .header("HTTP-Referer", "https://github.com/godoty/godoty")
            .header("X-Title", "Godoty AI Assistant")
            .json(&request)
            .send()
            .await?;

        if !response.status().is_success() {
            return Err(anyhow::anyhow!("LLM API request failed: {}", response.status()));
        }

        let response_text = response.text().await?;
        let chat_response: ChatResponse = serde_json::from_str(&response_text).map_err(|e| {
            let preview = response_text.chars().take(200).collect::<String>();
            anyhow::anyhow!("Failed to parse LLM chat response JSON: {}. Raw preview: {}", e, preview)
        })?;

        if let Some(choice) = chat_response.choices.first() {
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
                if !block.is_empty() { return Ok(block.to_string()); }
            }
        }
        if let Some(pos) = s.find("```JSON") {
            let json_start = pos + 7;
            if let Some(end_offset) = s[json_start..].find("```") {
                let json_end = json_start + end_offset;
                let block = s[json_start..json_end].trim();
                if !block.is_empty() { return Ok(block.to_string()); }
            }
        }


        // Fallback: first fenced block of any type that looks like JSON
        if let Some(start) = s.find("```") {
            let first_block_start = start + 3;
            if let Some(end) = s[first_block_start..].find("```") {
                let json_end = first_block_start + end;
                let block = s[first_block_start..json_end].trim();
                if block.starts_with('{') || block.starts_with('[') {
                    if !block.is_empty() { return Ok(block.to_string()); }
                }
            }
        }

        // Try extracting array or object by outermost brackets/braces
        if let Some(array_start) = s.find('[') {
            if let Some(array_end) = s.rfind(']') {
                if array_end > array_start {
                    let candidate = s[array_start..=array_end].trim();
                    if !candidate.is_empty() { return Ok(candidate.to_string()); }
                }
            }
        }
        if let Some(obj_start) = s.find('{') {
            if let Some(obj_end) = s.rfind('}') {
                if obj_end > obj_start {
                    let candidate = s[obj_start..=obj_end].trim();
                    if !candidate.is_empty() { return Ok(candidate.to_string()); }
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
            let (open_ch, close_ch) = if open_b == b'{' { ('{', '}') } else { ('[', ']') };

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

// Helper deserializer for Option<Vec<Value>> to accept null/missing, array, or single object
fn opt_one_or_many<'de, D>(deserializer: D) -> std::result::Result<Option<Vec<serde_json::Value>>, D::Error>
where
    D: serde::de::Deserializer<'de>,
{
    let opt = Option::<serde_json::Value>::deserialize(deserializer)?;
    match opt {
        None => Ok(None),
        Some(serde_json::Value::Array(arr)) => Ok(Some(arr)),
        Some(v @ serde_json::Value::Object(_)) => Ok(Some(vec![v])),
        Some(other) => Err(serde::de::Error::custom(format!(
            "expected array or object for validated_commands, got {}",
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
        serde_json::Value::Number(n) => n.as_u64()
            .ok_or_else(|| serde::de::Error::custom("expected unsigned integer for step_number"))
            .map(|u| u as usize),
        serde_json::Value::String(s) => s.parse::<usize>().map_err(serde::de::Error::custom),
        other => Err(serde::de::Error::custom(format!(
            "expected integer or numeric string for step_number, got {}",
            other
        ))),
    }
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
                '\\' => { out.push('\\'); escaped = true; }
                '"' => { out.push('"'); in_string = false; }
                c if (c as u32) <= 0x1F => {
                    match c {
                        '\n' => out.push_str("\\n"),
                        '\r' => out.push_str("\\r"),
                        '\t' => out.push_str("\\t"),
                        _ => out.push_str(&format!("\\u{:04x}", c as u32)),
                    }
                }
                _ => out.push(ch),
            }
        } else {
            match ch {
                '"' => { out.push('"'); in_string = true; }
                _ => out.push(ch),
            }
        }
    }
    out
}


/// Execution plan created by the planner agent
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionPlan {
    #[serde(deserialize_with = "string_or_value")]
    pub reasoning: String,
    #[serde(deserialize_with = "one_or_many")]
    pub steps: Vec<PlanStep>,
    #[serde(deserialize_with = "string_or_value")]
    pub estimated_complexity: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanStep {
    #[serde(deserialize_with = "usize_or_string")]
    pub step_number: usize,
    #[serde(deserialize_with = "string_or_value")]
    pub description: String,
    #[serde(deserialize_with = "string_or_vec")]
    pub commands_needed: Vec<String>,
}

/// Response from the agentic workflow
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentResponse {
    pub commands: Vec<Value>,
    pub thoughts: Vec<AgentThought>,
    pub plan: ExecutionPlan,
    pub knowledge_used: KnowledgeUsed,
    pub metrics: Option<WorkflowMetrics>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KnowledgeUsed {
    pub plugin_docs: Vec<String>,
    pub godot_docs: Vec<String>,
}

