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
    DocumentationAgent, AgentExecutionContext,
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
    pub async fn execute(
        &self,
        context: &AgentContext,
    ) -> Result<AgentResponse> {
        // Initialize metrics
        let request_id = uuid::Uuid::new_v4().to_string();
        let mut metrics = WorkflowMetrics::new(request_id.clone(), context.user_input.clone());

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

        // Parse execution plan
        let plan: ExecutionPlan = serde_json::from_str(&Self::extract_json(&plan_output.content)?)?;

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

            // Parse generated commands
            let generated_commands: Vec<Value> = serde_json::from_str(&Self::extract_json(&gen_output.content)?)?;
            metrics.commands_generated = generated_commands.len() as u32;

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
                validated_commands: Option<Vec<Value>>,
            }

            let ai_validation: AIValidationResult = serde_json::from_str(&Self::extract_json(&val_output.content)?)?;

            metrics.validation_errors += ai_validation.errors.len() as u32;
            metrics.validation_warnings += ai_validation.warnings.len() as u32;

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
"#, 
            plugin_context,
            docs_context,
            context.project_index.scenes.len(),
            context.project_index.scripts.len()
        );

        let response = self.call_llm(&system_prompt, &context.user_input).await?;
        
        // Parse the plan from response
        let plan: ExecutionPlan = serde_json::from_str(&response)
            .map_err(|e| anyhow::anyhow!("Failed to parse plan: {}", e))?;

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

        let system_prompt = format!(r#"You are a command generation agent for Godot.

Execution Plan:
{}

Plugin Command Examples:
{}

Generate a JSON array of commands to execute the plan.
Each command must be a valid JSON object matching the plugin's command schema.
Respond ONLY with the JSON array, no explanations.
"#,
            serde_json::to_string_pretty(plan)?,
            plugin_examples
        );

        let response = self.call_llm(&system_prompt, &context.user_input).await?;

        // Extract and parse commands
        let commands: Vec<Value> = serde_json::from_str(&Self::extract_json(&response)?)
            .map_err(|e| anyhow::anyhow!("Failed to parse commands: {}", e))?;

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
            max_tokens: 4096,
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
        let chat_response: ChatResponse = serde_json::from_str(&response_text)?;

        if let Some(choice) = chat_response.choices.first() {
            Ok(choice.message.content.clone())
        } else {
            Err(anyhow::anyhow!("No response from LLM"))
        }
    }

    /// Extract JSON from response
    fn extract_json(content: &str) -> Result<String> {
        let trimmed = content.trim();

        if let Some(start) = trimmed.find("```json") {
            let json_start = start + 7;
            if let Some(end_offset) = trimmed[json_start..].find("```") {
                let json_end = json_start + end_offset;
                return Ok(trimmed[json_start..json_end].trim().to_string());
            }
        }

        if let Some(start) = trimmed.find("```") {
            let first_block_start = start + 3;
            if let Some(end) = trimmed[first_block_start..].find("```") {
                let json_end = first_block_start + end;
                return Ok(trimmed[first_block_start..json_end].trim().to_string());
            }
        }

        if let Some(array_start) = trimmed.find('[') {
            if let Some(array_end) = trimmed.rfind(']') {
                if array_end > array_start {
                    return Ok(trimmed[array_start..=array_end].to_string());
                }
            }
        }

        if let Some(obj_start) = trimmed.find('{') {
            if let Some(obj_end) = trimmed.rfind('}') {
                if obj_end > obj_start {
                    return Ok(trimmed[obj_start..=obj_end].to_string());
                }
            }
        }

        Ok(trimmed.to_string())
    }
}

/// Execution plan created by the planner agent
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionPlan {
    pub reasoning: String,
    pub steps: Vec<PlanStep>,
    pub estimated_complexity: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanStep {
    pub step_number: usize,
    pub description: String,
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

