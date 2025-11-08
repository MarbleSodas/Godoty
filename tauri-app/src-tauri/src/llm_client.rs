use crate::llm_config::{AgentLlmConfig, AgentType, ModelSelection};
use anyhow::{anyhow, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::sync::{Mutex, OnceLock};
use tauri::Emitter;

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

    /// Model identifier used by this client (e.g., "qwen/qwen3-coder:free", "claude-3.5-sonnet")
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

fn emit_tool_event(_event: &str, payload: Value) {
    let guard = tool_context().lock().unwrap();
    if let (Some(win), _) = &*guard {
        let _ = win.emit("tool-call-delta", payload);
    }
}

fn current_session_id() -> Option<String> {
    let guard = tool_context().lock().unwrap();
    guard.1.clone()
}

/// LiteLLM (OpenAI-compatible) client routed via LiteLLM Proxy
pub struct LiteLlmClient {
    base_url: String,
    api_key: String,
    model: String,
    client: Client,
}

impl LiteLlmClient {
    pub fn new(base_url: String, api_key: String, model: String) -> Self {
        Self {
            base_url,
            api_key,
            model,
            client: Client::new(),
        }
    }
    fn chat_completions_url(&self) -> String {
        let base = self.base_url.trim_end_matches('/');
        format!("{}/v1/chat/completions", base)
    }
}

#[async_trait]
impl LlmClient for LiteLlmClient {
    async fn generate_response(&self, system_prompt: &str, user_input: &str) -> Result<String> {
        #[derive(Serialize, Deserialize)]
        struct ChatMessage {
            role: String,
            content: String,
        }
        #[derive(Serialize)]
        struct ChatRequest {
            model: String,
            messages: Vec<ChatMessage>,
            temperature: f32,
            max_tokens: i32,
        }
        #[derive(Deserialize)]
        struct Choice {
            message: ChatMessage,
        }
        #[derive(Deserialize)]
        struct ChatResponse {
            choices: Vec<Choice>,
        }

        let req = ChatRequest {
            model: self.model.clone(),
            messages: vec![
                ChatMessage {
                    role: "system".into(),
                    content: system_prompt.to_string(),
                },
                ChatMessage {
                    role: "user".into(),
                    content: user_input.to_string(),
                },
            ],
            temperature: 0.7,
            max_tokens: 8192,
        };

        let url = self.chat_completions_url();
        let resp = self
            .client
            .post(&url)
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", "application/json")
            .json(&req)
            .send()
            .await?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!(
                "LiteLLM request failed: {} - {}",
                status,
                body.chars().take(300).collect::<String>()
            ));
        }

        let text = resp.text().await?;
        let parsed: ChatResponse = serde_json::from_str(&text).map_err(|e| {
            anyhow::anyhow!(
                "LiteLLM parse error: {}. Raw: {}",
                e,
                text.chars().take(200).collect::<String>()
            )
        })?;
        if let Some(choice) = parsed.choices.first() {
            Ok(choice.message.content.clone())
        } else {
            Err(anyhow::anyhow!("LiteLLM: no choices in response"))
        }
    }

    async fn generate_response_streaming_with_tools(
        &self,
        system_prompt: &str,
        user_input: &str,
    ) -> Result<String> {
        // OpenAI-compatible SSE stream parsing
        #[derive(Serialize)]
        struct ChatMessage {
            role: String,
            content: String,
        }
        #[derive(Serialize)]
        struct ChatRequest {
            model: String,
            messages: Vec<ChatMessage>,
            temperature: f32,
            max_tokens: i32,
            stream: bool,
        }

        let req = ChatRequest {
            model: self.model.clone(),
            messages: vec![
                ChatMessage {
                    role: "system".into(),
                    content: system_prompt.to_string(),
                },
                ChatMessage {
                    role: "user".into(),
                    content: user_input.to_string(),
                },
            ],
            temperature: 0.7,
            max_tokens: 8192,
            stream: true,
        };

        let url = self.chat_completions_url();
        let mut resp = self
            .client
            .post(&url)
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", "application/json")
            .json(&req)
            .send()
            .await?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!(
                "LiteLLM stream request failed: {} - {}",
                status,
                body.chars().take(300).collect::<String>()
            ));
        }

        let mut buffer = String::new();
        let mut full_output = String::new();

        // Read streaming chunks and split on double-newline frames
        while let Some(chunk) = resp.chunk().await? {
            let s = String::from_utf8_lossy(&chunk);
            buffer.push_str(&s);

            // Process complete frames
            loop {
                if let Some(idx) = buffer.find("\n\n") {
                    let frame = buffer[..idx].to_string();
                    buffer = buffer[idx + 2..].to_string();

                    for line in frame.lines() {
                        let line = line.trim();
                        if !line.starts_with("data:") {
                            continue;
                        }
                        let data = line.trim_start_matches("data:").trim();
                        if data == "[DONE]" {
                            break;
                        }
                        // Parse JSON delta
                        if let Ok(v) = serde_json::from_str::<Value>(data) {
                            if let Some(choices) = v.get("choices").and_then(|c| c.as_array()) {
                                if let Some(delta) = choices.get(0).and_then(|c| c.get("delta")) {
                                    if let Some(piece) =
                                        delta.get("content").and_then(|x| x.as_str())
                                    {
                                        full_output.push_str(piece);
                                        emit_tool_event(
                                            "llm_stream",
                                            json!({
                                                "event": "llm_stream",
                                                "delta": piece,
                                                "model": self.model,
                                                "sessionId": current_session_id(),
                                            }),
                                        );
                                    }
                                }
                            }
                        }
                    }
                } else {
                    break;
                }
            }
        }

        // Emit completion event
        emit_tool_event(
            "llm_stream",
            json!({
                "event": "llm_stream_completed",
                "text": full_output,
                "model": self.model,
                "sessionId": current_session_id(),
            }),
        );

        Ok(full_output)
    }

    fn model_identifier(&self) -> &str {
        &self.model
    }
    fn endpoint(&self) -> &'static str {
        "/v1/chat/completions"
    }
}

/// Factory for creating LLM clients based on configuration
#[derive(Clone)]
pub struct LlmFactory {
    config: AgentLlmConfig,
}

impl LlmFactory {
    pub fn new(config: AgentLlmConfig) -> Self {
        Self { config }
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
        // Route all models exclusively through LiteLLM Proxy. No provider-specific fallbacks.
        let litellm_base = std::env::var("LITELLM_BASE_URL").unwrap_or_default();
        let litellm_key = std::env::var("LITELLM_API_KEY").unwrap_or_default();
        if litellm_base.trim().is_empty() || litellm_key.trim().is_empty() {
            return Err(anyhow!(
                "LiteLLM not configured. Set LITELLM_BASE_URL and LITELLM_API_KEY in environment."
            ));
        }

        Ok(Box::new(LiteLlmClient::new(
            litellm_base,
            litellm_key,
            selection.model_name.clone(),
        )))
    }
}
