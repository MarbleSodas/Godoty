use crate::agent::ExecutionPlan;
use crate::knowledge_base::KnowledgeBase;
use crate::llm_client::LlmFactory;
use crate::llm_config::AgentType;
use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Base trait for all specialized agents
#[async_trait::async_trait]
pub trait StrandsAgent: Send + Sync {
    async fn execute(&self, context: &AgentExecutionContext) -> Result<AgentOutput>;
    #[allow(dead_code)]
    fn get_name(&self) -> &str;
    #[allow(dead_code)]
    fn get_model(&self) -> &str;
}

/// Context passed to agents during execution
#[derive(Clone)]
pub struct AgentExecutionContext {
    pub user_input: String,
    pub _chat_history: String,
    pub project_context: String,
    pub plugin_kb: KnowledgeBase,
    pub docs_kb: KnowledgeBase,
    pub execution_plan: Option<ExecutionPlan>,
    pub previous_output: Option<String>,
    pub visual_context: Option<String>,
}

/// Output from agent execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentOutput {
    pub content: String,
    pub tokens_used: u32,
    pub execution_time_ms: u64,
    pub metadata: serde_json::Map<String, Value>,
}

/// Planning Agent - Breaks down user requests into actionable tasks
pub struct PlanningAgent {
    api_key: String,
    client: Client,
    model: String,
    llm_factory: Option<LlmFactory>,
}

impl PlanningAgent {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
            model: "minimax/minimax-m2:free".to_string(),
            llm_factory: None,
        }
    }

    pub fn with_llm_factory(mut self, llm_factory: Option<LlmFactory>) -> Self {
        self.llm_factory = llm_factory;
        self
    }
}

#[async_trait::async_trait]
impl StrandsAgent for PlanningAgent {
    async fn execute(&self, context: &AgentExecutionContext) -> Result<AgentOutput> {
        let start_time = std::time::Instant::now();

        // Query knowledge bases for context
        let plugin_docs = context.plugin_kb.search(&context.user_input, 5).await?;
        let godot_docs = context.docs_kb.search(&context.user_input, 5).await?;

        let plugin_context = plugin_docs
            .iter()
            .map(|d| format!("- {}: {}", d.id, d.content))
            .collect::<Vec<_>>()
            .join("\n");

        let docs_context = godot_docs
            .iter()
            .map(|d| format!("- {}", d.content.chars().take(200).collect::<String>()))
            .collect::<Vec<_>>()
            .join("\n");

        // Include visual context if available
        let visual_section = if let Some(ref visual) = context.visual_context {
            format!("\n\nVisual Context (UI/Scene Analysis):\n{}\n", visual)
        } else {
            String::new()
        };

        let system_prompt = format!(
            r#"You are an AI planning agent for Godot game development.
Your task is to analyze the user's request and create a detailed execution plan.

Available Plugin Commands:
{}

Relevant Godot Documentation:
{}

Project Context:
{}{}

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
            plugin_context, docs_context, context.project_context, visual_section
        );

        let response = if let Some(factory) = &self.llm_factory {
            let client = factory.create_client_for_agent(AgentType::Planner)?;
            let sys_prev = system_prompt.chars().take(200).collect::<String>();
            let user_prev = context.user_input.chars().take(200).collect::<String>();
            tracing::debug!(
                agent = "PlanningAgent",
                model = %client.model_identifier(),
                endpoint = %client.endpoint(),
                system_prompt_preview = %sys_prev,
                user_input_preview = %user_prev,
                "Agent LLM invocation"
            );
            client
                .generate_response_streaming_with_tools(&system_prompt, &context.user_input)
                .await?
        } else {
            call_llm(
                &self.client,
                &self.api_key,
                &self.model,
                &system_prompt,
                &context.user_input,
            )
            .await?
        };

        let execution_time_ms = start_time.elapsed().as_millis() as u64;

        // Estimate tokens (rough approximation: 1 token ≈ 4 characters)
        let tokens_used =
            ((system_prompt.len() + context.user_input.len() + response.len()) / 4) as u32;

        let mut metadata = serde_json::Map::new();
        metadata.insert(
            "plugin_docs_retrieved".to_string(),
            Value::Number(plugin_docs.len().into()),
        );
        metadata.insert(
            "godot_docs_retrieved".to_string(),
            Value::Number(godot_docs.len().into()),
        );

        Ok(AgentOutput {
            content: response,
            tokens_used,
            execution_time_ms,
            metadata,
        })
    }

    fn get_name(&self) -> &str {
        "PlanningAgent"
    }

    fn get_model(&self) -> &str {
        &self.model
    }
}

/// Code Generation Agent - Generates GDScript code and Godot commands
pub struct CodeGenerationAgent {
    api_key: String,
    client: Client,
    model: String,
    llm_factory: Option<LlmFactory>,
}

impl CodeGenerationAgent {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
            model: "qwen/qwen3-coder:free".to_string(),
            llm_factory: None,
        }
    }

    pub fn with_llm_factory(mut self, llm_factory: Option<LlmFactory>) -> Self {
        self.llm_factory = llm_factory;
        self
    }
}

#[async_trait::async_trait]
impl StrandsAgent for CodeGenerationAgent {
    async fn execute(&self, context: &AgentExecutionContext) -> Result<AgentOutput> {
        let start_time = std::time::Instant::now();

        let plan = context
            .execution_plan
            .as_ref()
            .ok_or_else(|| anyhow::anyhow!("Execution plan required for code generation"))?;

        // Get plugin examples
        let plugin_docs = context.plugin_kb.search(&context.user_input, 5).await?;
        let plugin_examples = plugin_docs
            .iter()
            .map(|d| d.content.clone())
            .collect::<Vec<_>>()
            .join("\n\n");

        let system_prompt = format!(
            r#"You are a command generation agent for Godot.

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

        let response = if let Some(factory) = &self.llm_factory {
            let client = factory.create_client_for_agent(AgentType::CodeGenerator)?;
            let sys_prev = system_prompt.chars().take(200).collect::<String>();
            let user_prev = context.user_input.chars().take(200).collect::<String>();
            tracing::debug!(
                agent = "CodeGenerationAgent",
                model = %client.model_identifier(),
                endpoint = %client.endpoint(),
                system_prompt_preview = %sys_prev,
                user_input_preview = %user_prev,
                "Agent LLM invocation"
            );
            client
                .generate_response_streaming_with_tools(&system_prompt, &context.user_input)
                .await?
        } else {
            call_llm(
                &self.client,
                &self.api_key,
                &self.model,
                &system_prompt,
                &context.user_input,
            )
            .await?
        };

        let execution_time_ms = start_time.elapsed().as_millis() as u64;
        let tokens_used =
            ((system_prompt.len() + context.user_input.len() + response.len()) / 4) as u32;

        Ok(AgentOutput {
            content: response,
            tokens_used,
            execution_time_ms,
            metadata: serde_json::Map::new(),
        })
    }

    fn get_name(&self) -> &str {
        "CodeGenerationAgent"
    }

    fn get_model(&self) -> &str {
        &self.model
    }
}

/// Validation Agent - Validates generated commands against Plugin Tools & API
pub struct ValidationAgent {
    api_key: String,
    client: Client,
    model: String,
    llm_factory: Option<LlmFactory>,
}

impl ValidationAgent {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
            model: "minimax/minimax-m2:free".to_string(),
            llm_factory: None,
        }
    }

    pub fn with_llm_factory(mut self, llm_factory: Option<LlmFactory>) -> Self {
        self.llm_factory = llm_factory;
        self
    }
}

#[async_trait::async_trait]
impl StrandsAgent for ValidationAgent {
    async fn execute(&self, context: &AgentExecutionContext) -> Result<AgentOutput> {
        let start_time = std::time::Instant::now();

        // Get all plugin documentation for validation
        let all_plugin_docs = context.plugin_kb.get_all_documents().await;
        let plugin_schema = all_plugin_docs
            .iter()
            .map(|d| d.content.clone())
            .collect::<Vec<_>>()
            .join("\n\n");

        let commands_to_validate = context
            .previous_output
            .as_ref()
            .ok_or_else(|| anyhow::anyhow!("No commands to validate"))?;

        let system_prompt = format!(
            r#"You are a validation agent for Godot commands.

Plugin Command Schema and Examples:
{}

Your task is to validate the following commands against the schema.
Check for:
1. Valid command types
2. Required fields present
3. Correct data types
4. No hallucinated API calls

Respond with a JSON object:
{{
  "valid": true/false,
  "errors": ["error1", "error2", ...],
  "warnings": ["warning1", "warning2", ...],
  "validated_commands": [/* corrected commands if needed */]
}}
"#,
            plugin_schema
        );

        let response = if let Some(factory) = &self.llm_factory {
            let client = factory.create_client_for_agent(AgentType::Validator)?;
            let sys_prev = system_prompt.chars().take(200).collect::<String>();
            let user_prev = commands_to_validate.chars().take(200).collect::<String>();
            tracing::debug!(
                agent = "ValidationAgent",
                model = %client.model_identifier(),
                endpoint = %client.endpoint(),
                system_prompt_preview = %sys_prev,
                user_input_preview = %user_prev,
                "Agent LLM invocation"
            );
            client
                .generate_response_streaming_with_tools(&system_prompt, commands_to_validate)
                .await?
        } else {
            call_llm(
                &self.client,
                &self.api_key,
                &self.model,
                &system_prompt,
                commands_to_validate,
            )
            .await?
        };

        let execution_time_ms = start_time.elapsed().as_millis() as u64;
        let tokens_used =
            ((system_prompt.len() + commands_to_validate.len() + response.len()) / 4) as u32;

        Ok(AgentOutput {
            content: response,
            tokens_used,
            execution_time_ms,
            metadata: serde_json::Map::new(),
        })
    }

    fn get_name(&self) -> &str {
        "ValidationAgent"
    }

    fn get_model(&self) -> &str {
        &self.model
    }
}

/// Documentation Agent - Queries Official Godot Documentation
pub struct DocumentationAgent {
    api_key: String,
    client: Client,
    model: String,
    llm_factory: Option<LlmFactory>,
}

impl DocumentationAgent {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
            model: "minimax/minimax-m2:free".to_string(),
            llm_factory: None,
        }
    }

    pub fn with_llm_factory(mut self, llm_factory: Option<LlmFactory>) -> Self {
        self.llm_factory = llm_factory;
        self
    }
}

#[async_trait::async_trait]
impl StrandsAgent for DocumentationAgent {
    async fn execute(&self, context: &AgentExecutionContext) -> Result<AgentOutput> {
        let start_time = std::time::Instant::now();

        // Search documentation knowledge base
        let docs = context.docs_kb.search(&context.user_input, 10).await?;

        let docs_content = docs
            .iter()
            .map(|d| format!("## {}\n{}", d.id, d.content))
            .collect::<Vec<_>>()
            .join("\n\n");

        let system_prompt = format!(
            r#"You are a documentation agent for Godot.

Retrieved Documentation:
{}

Summarize the most relevant information for the user's request.
Focus on API usage, best practices, and examples.
"#,
            docs_content
        );

        let response = if let Some(factory) = &self.llm_factory {
            let client = factory.create_client_for_agent(AgentType::Documentation)?;
            let sys_prev = system_prompt.chars().take(200).collect::<String>();
            let user_prev = context.user_input.chars().take(200).collect::<String>();
            tracing::debug!(
                agent = "DocumentationAgent",
                model = %client.model_identifier(),
                endpoint = %client.endpoint(),
                system_prompt_preview = %sys_prev,
                user_input_preview = %user_prev,
                "Agent LLM invocation"
            );
            client
                .generate_response_streaming_with_tools(&system_prompt, &context.user_input)
                .await?
        } else {
            call_llm(
                &self.client,
                &self.api_key,
                &self.model,
                &system_prompt,
                &context.user_input,
            )
            .await?
        };

        let execution_time_ms = start_time.elapsed().as_millis() as u64;
        let tokens_used =
            ((system_prompt.len() + context.user_input.len() + response.len()) / 4) as u32;

        let mut metadata = serde_json::Map::new();
        metadata.insert(
            "docs_retrieved".to_string(),
            Value::Number(docs.len().into()),
        );

        Ok(AgentOutput {
            content: response,
            tokens_used,
            execution_time_ms,
            metadata,
        })
    }

    fn get_name(&self) -> &str {
        "DocumentationAgent"
    }

    fn get_model(&self) -> &str {
        &self.model
    }
}

/// Helper function to call LLM API
async fn call_llm(
    client: &Client,
    api_key: &str,
    model: &str,
    system_prompt: &str,
    user_input: &str,
) -> Result<String> {
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
        model: model.to_string(),
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
    tracing::debug!(
        provider = "OpenRouter",
        model = %model,
        endpoint = "https://openrouter.ai/api/v1/chat/completions",
        system_prompt_preview = %sys_prev,
        user_input_preview = %user_prev,
        "Agent LLM invocation (fallback)"
    );

    let response = client
        .post("https://openrouter.ai/api/v1/chat/completions")
        .header("Authorization", format!("Bearer {}", api_key))
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
            "Failed to parse LLM response JSON: {}. Raw preview: {}",
            e,
            preview
        )
    })?;

    if let Some(choice) = chat_response.choices.first() {
        // Check if response was truncated due to token limit
        if let Some(ref finish_reason) = choice.finish_reason {
            if finish_reason == "length" {
                tracing::warn!(
                    model = %model,
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
