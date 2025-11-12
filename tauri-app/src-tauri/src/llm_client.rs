use crate::llm_config::{AgentLlmConfig, AgentType, ApiKeyStore, LlmProvider, ModelSelection};
use crate::mcp_tools::{ToolDefinition, ToolCall};
use anyhow::{anyhow, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};

use std::sync::{Mutex, OnceLock};

/// Usage information returned by LLM APIs
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct LlmUsage {
    pub prompt_tokens: u32,
    pub completion_tokens: u32,
    pub total_tokens: u32,
    /// Actual cost in USD (OpenRouter returns this directly)
    pub cost: Option<f64>,
}


/// Response from LLM including usage information
#[derive(Debug, Clone)]
pub struct LlmResponse {
    pub content: String,
    pub usage: Option<LlmUsage>,
    pub tool_calls: Option<Vec<ToolCall>>,
}

/// Chat message that supports tool calls and tool results
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatMessageWithTools {
    pub role: String,
    pub content: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_calls: Option<Vec<ToolCall>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_call_id: Option<String>,
}

/// Generic trait for LLM clients
#[async_trait]
pub trait LlmClient: Send + Sync {
    async fn generate_response(&self, system_prompt: &str, user_input: &str) -> Result<String>;

    /// Generate response with usage tracking
    async fn generate_response_with_usage(&self, system_prompt: &str, user_input: &str) -> Result<LlmResponse> {
        // Default implementation for backward compatibility
        let content = self.generate_response(system_prompt, user_input).await?;
        Ok(LlmResponse {
            content,
            usage: None,
            tool_calls: None,
        })
    }

    /// Generate response with tool calling support
    async fn generate_response_with_tools(
        &self,
        messages: Vec<ChatMessageWithTools>,
        _tools: Option<Vec<ToolDefinition>>,
    ) -> Result<LlmResponse> {
        // Default implementation falls back to simple generation
        let system_msg = messages.iter()
            .find(|m| m.role == "system")
            .map(|m| m.content.clone())
            .unwrap_or_default();
        let user_msg = messages.iter()
            .filter(|m| m.role == "user")
            .next_back()
            .map(|m| m.content.clone())
            .unwrap_or_default();
        self.generate_response_with_usage(&system_msg, &user_msg).await
    }

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
        let response = self.generate_response_with_usage(system_prompt, user_input).await?;
        Ok(response.content)
    }

    async fn generate_response_with_usage(&self, system_prompt: &str, user_input: &str) -> Result<LlmResponse> {
        #[derive(Serialize)]
        struct UsageConfig {
            include: bool,
        }

        #[derive(Serialize)]
        struct ChatRequest {
            model: String,
            messages: Vec<ChatMessage>,
            temperature: f32,
            max_tokens: i32,
            usage: UsageConfig,
        }

        #[derive(Serialize, Deserialize)]
        struct ChatMessage {
            role: String,
            content: String,
        }

        #[derive(Deserialize)]
        struct ApiUsage {
            prompt_tokens: u32,
            completion_tokens: u32,
            total_tokens: u32,
            #[serde(default)]
            cost: Option<f64>,
        }

        #[derive(Deserialize)]
        struct ChatResponse {
            choices: Vec<Choice>,
            #[serde(default)]
            usage: Option<ApiUsage>,
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
            usage: UsageConfig { include: true },
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
            let usage = chat_response.usage.map(|u| LlmUsage {
                prompt_tokens: u.prompt_tokens,
                completion_tokens: u.completion_tokens,
                total_tokens: u.total_tokens,
                cost: u.cost,
            });

            // Log usage information if available
            if let Some(ref usage_info) = usage {
                if let Some(cost) = usage_info.cost {
                    tracing::info!(
                        model = %self.model,
                        prompt_tokens = usage_info.prompt_tokens,
                        completion_tokens = usage_info.completion_tokens,
                        total_tokens = usage_info.total_tokens,
                        cost_usd = cost,
                        "OpenRouter API usage tracked with cost"
                    );
                } else {
                    tracing::warn!(
                        model = %self.model,
                        prompt_tokens = usage_info.prompt_tokens,
                        completion_tokens = usage_info.completion_tokens,
                        total_tokens = usage_info.total_tokens,
                        "OpenRouter API usage tracked but NO COST returned - ensure 'usage.include=true' is set"
                    );
                }
            } else {
                tracing::warn!(
                    model = %self.model,
                    "OpenRouter API response contained NO USAGE information"
                );
            }

            Ok(LlmResponse {
                content: choice.message.content.clone(),
                usage,
                tool_calls: None,
            })
        } else {
            Err(anyhow::anyhow!("No response from LLM"))
        }
    }

    async fn generate_response_with_tools(
        &self,
        messages: Vec<ChatMessageWithTools>,
        tools: Option<Vec<ToolDefinition>>,
    ) -> Result<LlmResponse> {
        #[derive(Serialize)]
        struct UsageConfig {
            include: bool,
        }

        #[derive(Serialize)]
        struct ChatRequestWithTools {
            model: String,
            messages: Vec<ChatMessageWithTools>,
            temperature: f32,
            max_tokens: i32,
            usage: UsageConfig,
            #[serde(skip_serializing_if = "Option::is_none")]
            tools: Option<Vec<ToolDefinition>>,
        }

        #[derive(Deserialize)]
        struct ApiUsage {
            prompt_tokens: u32,
            completion_tokens: u32,
            total_tokens: u32,
            #[serde(default)]
            cost: Option<f64>,
        }

        #[derive(Deserialize)]
        struct ChatResponseWithTools {
            choices: Vec<ChoiceWithTools>,
            #[serde(default)]
            usage: Option<ApiUsage>,
        }

        #[derive(Deserialize)]
        struct ChoiceWithTools {
            message: MessageWithTools,
        }

        #[derive(Deserialize)]
        struct MessageWithTools {
            #[allow(dead_code)]
            role: String,
            content: Option<String>,
            #[serde(default)]
            tool_calls: Option<Vec<ToolCall>>,
        }

        tracing::debug!(
            provider = "OpenRouter",
            model = %self.model,
            endpoint = %self.endpoint(),
            message_count = messages.len(),
            has_tools = tools.is_some(),
            tool_count = tools.as_ref().map(|t| t.len()).unwrap_or(0),
            "LLM call with tools starting"
        );

        let request = ChatRequestWithTools {
            model: self.model.clone(),
            messages,
            temperature: 0.7,
            max_tokens: 8192,
            usage: UsageConfig { include: true },
            tools,
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
            let status = response.status();
            let error_text = response.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!(
                "LLM API request failed: {} - {}",
                status,
                error_text
            ));
        }

        let response_text = response.text().await?;
        let chat_response: ChatResponseWithTools = serde_json::from_str(&response_text).map_err(|e| {
            let preview = response_text.chars().take(500).collect::<String>();
            anyhow::anyhow!(
                "Failed to parse LLM chat response JSON: {}. Raw preview: {}",
                e,
                preview
            )
        })?;

        if let Some(choice) = chat_response.choices.first() {
            let usage = chat_response.usage.map(|u| LlmUsage {
                prompt_tokens: u.prompt_tokens,
                completion_tokens: u.completion_tokens,
                total_tokens: u.total_tokens,
                cost: u.cost,
            });

            if let Some(ref usage_info) = usage {
                if let Some(cost) = usage_info.cost {
                    tracing::info!(
                        model = %self.model,
                        prompt_tokens = usage_info.prompt_tokens,
                        completion_tokens = usage_info.completion_tokens,
                        total_tokens = usage_info.total_tokens,
                        cost_usd = cost,
                        has_tool_calls = choice.message.tool_calls.is_some(),
                        "OpenRouter API usage tracked with cost (tool calling mode)"
                    );
                } else {
                    tracing::warn!(
                        model = %self.model,
                        prompt_tokens = usage_info.prompt_tokens,
                        completion_tokens = usage_info.completion_tokens,
                        total_tokens = usage_info.total_tokens,
                        has_tool_calls = choice.message.tool_calls.is_some(),
                        "OpenRouter API usage tracked but NO COST returned (tool calling mode)"
                    );
                }
            } else {
                tracing::warn!(
                    model = %self.model,
                    has_tool_calls = choice.message.tool_calls.is_some(),
                    "OpenRouter API response contained NO USAGE information (tool calling mode)"
                );
            }

            Ok(LlmResponse {
                content: choice.message.content.clone().unwrap_or_default(),
                usage,
                tool_calls: choice.message.tool_calls.clone(),
            })
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
