use crate::llm_config::{AgentLlmConfig, AgentType, ApiKeyStore, LlmProvider, ModelSelection};
use anyhow::{anyhow, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};

use std::sync::{Mutex, OnceLock};


/// Generic trait for LLM clients
#[async_trait]
pub trait LlmClient: Send + Sync {
    async fn generate_response(&self, system_prompt: &str, user_input: &str) -> Result<String>;

    /// Optional: streaming with tool support. Default falls back to non-streaming
    async fn generate_response_streaming_with_tools(
        &self,
        system_prompt: &str,
        user_input: &str,
    ) -> Result<String> {
        self.generate_response(system_prompt, user_input).await
    }

    /// Model identifier used by this client (e.g., "qwen/qwen3-coder:free", "glm-4.5")
    fn model_identifier(&self) -> &str;

    /// API endpoint base URL used by this client
    fn endpoint(&self) -> &'static str;
}

/// Global context for emitting tool-call events (set by lib.rs before agentic run)
static TOOL_EVENT_CONTEXT: OnceLock<Mutex<(Option<tauri::Window>, Option<String>)>> =
    OnceLock::new();

fn tool_context() -> &'static Mutex<(Option<tauri::Window>, Option<String>)> {
    TOOL_EVENT_CONTEXT.get_or_init(|| Mutex::new((None, None)))
}

pub fn set_tool_event_context(window: Option<tauri::Window>, session_id: Option<String>) {
    let mut guard = tool_context().lock().unwrap();
    *guard = (window, session_id);
}


/// OpenRouter client (currently used in the codebase)
pub struct OpenRouterClient {
    api_key: String,
    model: String,
    client: Client,
}

impl OpenRouterClient {
    pub fn new(api_key: String, model: String) -> Self {
        Self {
            api_key,
            model,
            client: Client::new(),
        }
    }
}

#[async_trait]
impl LlmClient for OpenRouterClient {
    async fn generate_response(&self, system_prompt: &str, user_input: &str) -> Result<String> {
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

        // Debug log: model, endpoint, and prompt previews
        let sys_prev = system_prompt.chars().take(200).collect::<String>();
        let user_prev = user_input.chars().take(200).collect::<String>();
        tracing::debug!(
            provider = "OpenRouter",
            model = %self.model,
            endpoint = %self.endpoint(),
            system_prompt_len = system_prompt.len(),
            user_input_len = user_input.len(),
            system_prompt_preview = %sys_prev,
            user_input_preview = %user_prev,
            "LLM call starting"
        );

        let request = ChatRequest {
            model: self.model.clone(),
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

        let response = self
            .client
            .post(self.endpoint())
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
            let preview = response_text.chars().take(200).collect::<String>();
            anyhow::anyhow!(
                "Failed to parse LLM chat response JSON: {}. Raw preview: {}",
                e,
                preview
            )
        })?;

        if let Some(choice) = chat_response.choices.first() {
            Ok(choice.message.content.clone())
        } else {
            Err(anyhow::anyhow!("No response from LLM"))
        }
    }

    // Keep default fallback for streaming-with-tools

    fn model_identifier(&self) -> &str {
        &self.model
    }
    fn endpoint(&self) -> &'static str {
        "https://openrouter.ai/api/v1/chat/completions"
    }
}

/// Factory for creating LLM clients based on configuration
#[derive(Clone)]
pub struct LlmFactory {
    config: AgentLlmConfig,
    api_keys: ApiKeyStore,
}

impl LlmFactory {
    pub fn new(config: AgentLlmConfig, api_keys: ApiKeyStore) -> Self {
        Self { config, api_keys }
    }

    /// Create a client for a specific agent type
    pub fn create_client_for_agent(&self, agent_type: AgentType) -> Result<Box<dyn LlmClient>> {
        let model_selection = self.config.agents.get(&agent_type).ok_or_else(|| {
            anyhow::anyhow!("No model configured for agent type: {:?}", agent_type)
        })?;

        self.create_client(model_selection)
    }

    /// Create a client from a model selection
    fn create_client(&self, selection: &ModelSelection) -> Result<Box<dyn LlmClient>> {
        let api_key = self
            .api_keys
            .get_key(&selection.provider)
            .ok_or_else(|| {
                anyhow!(
                    "No API key configured for provider: {:?}",
                    selection.provider
                )
            })?
            .clone();

        // Basic API key validation before constructing clients
        validate_api_key(&selection.provider, &api_key)?;

        match selection.provider {
            LlmProvider::OpenRouter => Ok(Box::new(OpenRouterClient::new(
                api_key,
                selection.model_name.clone(),
            ))),
        }
    }
}

/// Provider-specific API key validation (non-strict; prevents obvious mistakes)
fn validate_api_key(_provider: &LlmProvider, key: &str) -> Result<()> {
    let trimmed = key.trim();
    if trimmed.is_empty() {
        return Err(anyhow!("API key is empty"));
    }
    if trimmed.contains(char::is_whitespace) {
        return Err(anyhow!("API key cannot contain whitespace"));
    }
    Ok(())
}
