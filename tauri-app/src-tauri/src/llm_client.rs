use crate::llm_config::{AgentLlmConfig, AgentType, ApiKeyStore, LlmProvider, ModelSelection};
use crate::storage::Storage;
use crate::web_search::{SearchResults, TavilyClient};
use anyhow::{anyhow, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};
use tauri::Emitter;
use tokio::time::{sleep, Duration};

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

/// Z.AI GLM official client
pub struct ZaiGlmClient {
    api_key: String,
    model: String,
    client: Client,
}

impl ZaiGlmClient {
    pub fn new(api_key: String, model: String) -> Self {
        Self {
            api_key,
            model,
            client: Client::new(),
        }
    }

    fn web_search_tool_schema() -> Value {
        json!({
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5}
            },
            "required": ["query"],
            "additionalProperties": false
        })
    }
}

#[async_trait]
impl LlmClient for ZaiGlmClient {
    async fn generate_response(&self, system_prompt: &str, user_input: &str) -> Result<String> {
        // Fallback non-streaming basic completion
        #[derive(Serialize)]
        struct ChatRequest {
            model: String,
            messages: Vec<ChatMessage>,
            #[serde(skip_serializing_if = "Option::is_none")]
            temperature: Option<f32>,
            #[serde(skip_serializing_if = "Option::is_none")]
            max_tokens: Option<i32>,
            #[serde(skip_serializing_if = "Option::is_none")]
            stream: Option<bool>,
        }

        #[derive(Serialize, Deserialize, Clone)]
        struct ChatMessage {
            role: String,
            content: String,
        }

        #[derive(Deserialize)]
        struct Choice {
            message: ChatMessage,
        }
        #[derive(Deserialize)]
        struct ChatResponse {
            choices: Vec<Choice>,
        }

        // Debug log: model, endpoint, and prompt previews
        let sys_prev = system_prompt.chars().take(200).collect::<String>();
        let user_prev = user_input.chars().take(200).collect::<String>();
        tracing::debug!(
            provider = "ZaiGlm",
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
                    role: "system".into(),
                    content: system_prompt.to_string(),
                },
                ChatMessage {
                    role: "user".into(),
                    content: user_input.to_string(),
                },
            ],
            temperature: Some(0.7),
            max_tokens: Some(8192),
            stream: Some(false),
        };

        let url = self.endpoint();

        let mut attempt = 0u8;
        loop {
            let resp = self
                .client
                .post(url)
                .header("Authorization", format!("Bearer {}", self.api_key))
                .header("Content-Type", "application/json")
                .json(&request)
                .send()
                .await?;

            if resp.status().is_success() {
                let text = resp.text().await?;
                let parsed: ChatResponse = serde_json::from_str(&text).map_err(|e| {
                    let preview = text.chars().take(200).collect::<String>();
                    anyhow!(
                        "Failed to parse Z.AI GLM response JSON: {}. Raw preview: {}",
                        e,
                        preview
                    )
                })?;
                if let Some(choice) = parsed.choices.first() {
                    return Ok(choice.message.content.clone());
                } else {
                    return Err(anyhow!("Z.AI GLM returned no choices"));
                }
            }

            let status = resp.status();
            let body_preview = resp
                .text()
                .await
                .unwrap_or_default()
                .chars()
                .take(200)
                .collect::<String>();
            if (status.as_u16() == 429 || status.is_server_error()) && attempt < 2 {
                // retry up to 2 times
                attempt += 1;
                let backoff_ms = 250u64 * (attempt as u64).pow(2);
                sleep(Duration::from_millis(backoff_ms)).await;
                continue;
            }
            return Err(anyhow!(
                "Z.AI GLM request failed: {} - {}",
                status,
                body_preview
            ));
        }
    }

    async fn generate_response_streaming_with_tools(
        &self,
        system_prompt: &str,
        user_input: &str,
    ) -> Result<String> {
        // Types to match OpenAI/Zhipu-like tool/function-calling payloads
        #[derive(Serialize, Deserialize, Clone)]
        struct ToolFunction {
            name: String,
            arguments: String,
        }
        #[derive(Serialize, Deserialize, Clone)]
        struct AssistantToolCall {
            #[serde(rename = "type")]
            call_type: String,
            id: Option<String>,
            function: ToolFunction,
        }

        #[derive(Serialize, Deserialize, Clone)]
        struct ChatMessage {
            role: String,
            #[serde(skip_serializing_if = "Option::is_none")]
            content: Option<String>,
            #[serde(skip_serializing_if = "Option::is_none")]
            tool_calls: Option<Vec<AssistantToolCall>>,
            #[serde(skip_serializing_if = "Option::is_none")]
            name: Option<String>,
            #[serde(skip_serializing_if = "Option::is_none")]
            tool_call_id: Option<String>,
        }

        #[derive(Serialize)]
        struct FunctionDef {
            name: String,
            description: String,
            parameters: Value,
        }
        #[derive(Serialize)]
        struct ToolDef {
            #[serde(rename = "type")]
            tool_type: String,
            function: FunctionDef,
        }

        #[derive(Serialize)]
        struct ChatRequest {
            model: String,
            messages: Vec<ChatMessage>,
            #[serde(skip_serializing_if = "Option::is_none")]
            temperature: Option<f32>,
            #[serde(skip_serializing_if = "Option::is_none")]
            max_tokens: Option<i32>,
            #[serde(skip_serializing_if = "Option::is_none")]
            stream: Option<bool>,
            #[serde(skip_serializing_if = "Option::is_none")]
            tools: Option<Vec<ToolDef>>,
        }

        // Debug log: model, endpoint, and prompt previews for streaming-call-with-tools
        let sys_prev = system_prompt.chars().take(200).collect::<String>();
        let user_prev = user_input.chars().take(200).collect::<String>();
        tracing::debug!(
            provider = "ZaiGlm",
            model = %self.model,
            endpoint = %self.endpoint(),
            system_prompt_len = system_prompt.len(),
            user_input_len = user_input.len(),
            system_prompt_preview = %sys_prev,
            user_input_preview = %user_prev,
            streaming = true,
            "LLM call starting"
        );

        let mut messages = vec![
            ChatMessage {
                role: "system".into(),
                content: Some(system_prompt.to_string()),
                tool_calls: None,
                name: None,
                tool_call_id: None,
            },
            ChatMessage {
                role: "user".into(),
                content: Some(user_input.to_string()),
                tool_calls: None,
                name: None,
                tool_call_id: None,
            },
        ];

        // Define web_search tool in OpenAI-compatible function-call format
        let tools = vec![ToolDef {
            tool_type: "function".into(),
            function: FunctionDef {
                name: "web_search".into(),
                description: "Search the web and return relevant results (title, url, snippet)."
                    .to_string(),
                parameters: ZaiGlmClient::web_search_tool_schema(),
            },
        }];

        let req = ChatRequest {
            model: self.model.clone(),
            messages: messages.clone(),
            temperature: Some(0.7),
            max_tokens: Some(8192),
            stream: Some(true),
            tools: Some(tools),
        };

        let url = self.endpoint();
        let mut resp = self
            .client
            .post(url)
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", "application/json")
            .json(&req)
            .send()
            .await?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            return Err(anyhow!(
                "GLM streaming request failed: {} - {}",
                status,
                body.chars().take(300).collect::<String>()
            ));
        }

        // Stream parse SSE-like "data: ..." chunks
        let mut buffer = String::new();
        let mut content_accum = String::new();
        let mut tool_arg_buffers: HashMap<usize, (String, String, String)> = HashMap::new(); // idx -> (id, name, args_buf)

        while let Some(chunk) = resp.chunk().await? {
            let s = String::from_utf8_lossy(&chunk);
            buffer.push_str(&s);

            // Process complete SSE events separated by double newlines
            while let Some(split_idx) = buffer.find("\n\n") {
                let event_block = buffer[..split_idx].to_string();
                buffer = buffer[split_idx + 2..].to_string();

                for line in event_block.lines() {
                    let line = line.trim_start();
                    if !line.starts_with("data:") {
                        continue;
                    }
                    let data = line.trim_start_matches("data:").trim();
                    if data == "[DONE]" {
                        break;
                    }
                    if data.is_empty() {
                        continue;
                    }
                    if let Ok(val) = serde_json::from_str::<Value>(data) {
                        // Try to read OpenAI-like structure: { choices: [ { delta: { content?, tool_calls? }, finish_reason? } ] }
                        if let Some(choice0) = val.get("choices").and_then(|c| c.get(0)) {
                            if let Some(delta) = choice0.get("delta") {
                                if let Some(piece) = delta.get("content").and_then(|v| v.as_str()) {
                                    content_accum.push_str(piece);
                                    // emit partial content? (not required for this task)
                                }
                                if let Some(tc_array) =
                                    delta.get("tool_calls").and_then(|v| v.as_array())
                                {
                                    for (i, tc) in tc_array.iter().enumerate() {
                                        let idx = tc
                                            .get("index")
                                            .and_then(|v| v.as_u64())
                                            .unwrap_or(i as u64)
                                            as usize;
                                        let id = tc
                                            .get("id")
                                            .and_then(|v| v.as_str())
                                            .unwrap_or("")
                                            .to_string();
                                        let func_opt = tc.get("function");
                                        let name = func_opt
                                            .and_then(|v| v.get("name"))
                                            .and_then(|v| v.as_str())
                                            .unwrap_or("")
                                            .to_string();
                                        let args_piece = func_opt
                                            .and_then(|v| v.get("arguments"))
                                            .and_then(|v| v.as_str())
                                            .unwrap_or("");

                                        let entry =
                                            tool_arg_buffers.entry(idx).or_insert_with(|| {
                                                (id.clone(), name.clone(), String::new())
                                            });
                                        if entry.0.is_empty() && !id.is_empty() {
                                            entry.0 = id.clone();
                                        }
                                        if entry.1.is_empty() && !name.is_empty() {
                                            entry.1 = name.clone();
                                        }
                                        if !args_piece.is_empty() {
                                            entry.2.push_str(args_piece);

                                            // Emit streaming delta
                                            emit_tool_event(
                                                "tool-call-delta",
                                                json!({
                                                    "session_id": current_session_id(),
                                                    "status": "streaming",
                                                    "tool_call_id": entry.0,
                                                    "name": entry.1,
                                                    "arguments_delta": args_piece,
                                                }),
                                            );
                                        } else if entry.2.is_empty() {
                                            // First sighting -> started
                                            emit_tool_event(
                                                "tool-call-delta",
                                                json!({
                                                    "session_id": current_session_id(),
                                                    "status": "started",
                                                    "tool_call_id": entry.0,
                                                    "name": entry.1,
                                                }),
                                            );
                                        }
                                    }
                                }
                            }

                            // If finish_reason indicates tool_calls, execute them
                            if let Some(fr) = choice0.get("finish_reason").and_then(|v| v.as_str())
                            {
                                if fr == "tool_calls" || fr == "tool" {
                                    // Execute tool(s) synchronously and continue the conversation
                                    for (_idx, (id, name, args_buf)) in tool_arg_buffers.clone() {
                                        if name == "web_search" {
                                            // Parse arguments (best-effort)
                                            let (query, max_results) =
                                                match serde_json::from_str::<Value>(&args_buf) {
                                                    Ok(v) => {
                                                        let q = v
                                                            .get("query")
                                                            .and_then(|x| x.as_str())
                                                            .unwrap_or("")
                                                            .to_string();
                                                        let mr = v
                                                            .get("max_results")
                                                            .and_then(|x| x.as_u64())
                                                            .unwrap_or(5)
                                                            as usize;
                                                        (q, mr)
                                                    }
                                                    Err(_) => (args_buf.clone(), 5),
                                                };

                                            // Execute Tavily search
                                            let storage = Storage::new();
                                            let (_provider, api_key_opt) =
                                                storage.get_web_search_settings();
                                            if let Some(api_key) = api_key_opt {
                                                let tavily = TavilyClient::new(api_key);
                                                let start = std::time::Instant::now();
                                                let result: Result<SearchResults> = tavily
                                                    .search(&query, max_results)
                                                    .await
                                                    .map_err(|e| anyhow!(e));
                                                let took_ms = start.elapsed().as_millis() as u64;

                                                match result {
                                                    Ok(res) => {
                                                        emit_tool_event(
                                                            "tool-call-delta",
                                                            json!({
                                                                "session_id": current_session_id(),
                                                                "status": "completed",
                                                                "tool_call_id": id,
                                                                "name": name,
                                                                "duration_ms": took_ms,
                                                                "result_preview": res.results.iter().take(1).map(|r| &r.title).collect::<Vec<_>>()
                                                            }),
                                                        );

                                                        // Append assistant tool_calls message + tool result message
                                                        messages.push(ChatMessage {
                                                            role: "assistant".into(),
                                                            content: None,
                                                            tool_calls: Some(vec![
                                                                AssistantToolCall {
                                                                    call_type: "function".into(),
                                                                    id: Some(id.clone()),
                                                                    function: ToolFunction {
                                                                        name: name.clone(),
                                                                        arguments: args_buf.clone(),
                                                                    },
                                                                },
                                                            ]),
                                                            name: None,
                                                            tool_call_id: None,
                                                        });
                                                        messages.push(ChatMessage {
                                                            role: "tool".into(),
                                                            content: Some(
                                                                serde_json::to_string(&res)
                                                                    .unwrap_or_else(|_| {
                                                                        "{}".to_string()
                                                                    }),
                                                            ),
                                                            tool_calls: None,
                                                            name: Some("web_search".into()),
                                                            tool_call_id: Some(id.clone()),
                                                        });
                                                    }
                                                    Err(err) => {
                                                        emit_tool_event(
                                                            "tool-call-delta",
                                                            json!({
                                                                "session_id": current_session_id(),
                                                                "status": "error",
                                                                "tool_call_id": id,
                                                                "name": name,
                                                                "error": err.to_string()
                                                            }),
                                                        );

                                                        // Append error tool result
                                                        messages.push(ChatMessage {
                                                            role: "assistant".into(),
                                                            content: None,
                                                            tool_calls: Some(vec![
                                                                AssistantToolCall {
                                                                    call_type: "function".into(),
                                                                    id: Some(id.clone()),
                                                                    function: ToolFunction {
                                                                        name: name.clone(),
                                                                        arguments: args_buf.clone(),
                                                                    },
                                                                },
                                                            ]),
                                                            name: None,
                                                            tool_call_id: None,
                                                        });
                                                        messages.push(ChatMessage {
                                                            role: "tool".into(),
                                                            content: Some(
                                                                json!({"error": err.to_string()})
                                                                    .to_string(),
                                                            ),
                                                            tool_calls: None,
                                                            name: Some("web_search".into()),
                                                            tool_call_id: Some(id.clone()),
                                                        });
                                                    }
                                                }
                                            } else {
                                                // No API key configured
                                                emit_tool_event(
                                                    "tool-call-delta",
                                                    json!({
                                                        "session_id": current_session_id(),
                                                        "status": "error",
                                                        "tool_call_id": id,
                                                        "name": name,
                                                        "error": "Web search API key not configured"
                                                    }),
                                                );
                                            }
                                        }
                                    }

                                    // After tool execution, call model again (non-streaming) to get final answer
                                    let followup_req = ChatRequest {
                                        model: self.model.clone(),
                                        messages: messages.clone(),
                                        temperature: Some(0.7),
                                        max_tokens: Some(8192),
                                        stream: Some(false),
                                        tools: None,
                                    };
                                    let followup = self
                                        .client
                                        .post(url)
                                        .header("Authorization", format!("Bearer {}", self.api_key))
                                        .header("Content-Type", "application/json")
                                        .json(&followup_req)
                                        .send()
                                        .await?;
                                    let txt = followup.text().await?;
                                    // Try OpenAI-like format first, else fallback to plain content field
                                    if let Ok(obj) = serde_json::from_str::<Value>(&txt) {
                                        if let Some(choice) =
                                            obj.get("choices").and_then(|c| c.get(0))
                                        {
                                            if let Some(msg) = choice.get("message") {
                                                if let Some(c) =
                                                    msg.get("content").and_then(|v| v.as_str())
                                                {
                                                    return Ok(c.to_string());
                                                }
                                            }
                                        }
                                    }
                                    return Ok(txt);
                                }
                            }
                        }
                    }
                }
            }
        }

        Ok(content_accum)
    }
    // Trait metadata helpers
    fn model_identifier(&self) -> &str {
        &self.model
    }
    fn endpoint(&self) -> &'static str {
        "https://open.bigmodel.cn/api/paas/v4/chat/completions"
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
            LlmProvider::ZaiGlm => Ok(Box::new(ZaiGlmClient::new(
                api_key,
                selection.model_name.clone(),
            ))),
        }
    }
}

/// Provider-specific API key validation (non-strict; prevents obvious mistakes)
fn validate_api_key(provider: &LlmProvider, key: &str) -> Result<()> {
    let trimmed = key.trim();
    if trimmed.is_empty() {
        return Err(anyhow!("API key is empty"));
    }
    if trimmed.contains(char::is_whitespace) {
        return Err(anyhow!("API key cannot contain whitespace"));
    }

    if provider == &LlmProvider::ZaiGlm {
        // ZhipuAI keys are typically lengthy tokens; enforce basic length check
        if trimmed.len() < 20 {
            return Err(anyhow!("Z.AI GLM API key looks too short"));
        }
    }
    Ok(())
}
