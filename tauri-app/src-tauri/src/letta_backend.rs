use anyhow::{anyhow, Result};
use reqwest::Client;
use serde::Serialize;
use serde_json::{json, Value};
use tauri::Emitter;

use crate::agent::{AgentContext, AgentResponse, AgentThought, ExecutionPlan, KnowledgeUsed};
use crate::metrics::WorkflowMetrics;

#[derive(Clone)]
pub struct LettaBackend {
    base_url: String,
    api_key: String,
    model: String,
    client: Client,
}

impl LettaBackend {
    pub fn new_from_env() -> Result<Self> {
        let base = std::env::var("LETTA_BASE_URL").unwrap_or_default();
        let key = std::env::var("LETTA_API_KEY").unwrap_or_default();
        if base.trim().is_empty() || key.trim().is_empty() {
            return Err(anyhow!(
                "Letta not configured. Set LETTA_BASE_URL and LETTA_API_KEY."
            ));
        }
        // Default model Letta will route to; can be overridden later via agent config
        let model =
            std::env::var("LETTA_MODEL").unwrap_or_else(|_| "openai/gpt-4o-mini".to_string());
        Ok(Self {
            base_url: base,
            api_key: key,
            model,
            client: Client::new(),
        })
    }

    async fn create_agent(&self) -> Result<String> {
        #[derive(Serialize)]
        struct CreateAgent {
            name: String,
            model: String,
            embedding: String,
            #[serde(skip_serializing_if = "Option::is_none")]
            memory_blocks: Option<Vec<MemoryBlock>>,
        }
        #[derive(Serialize)]
        struct MemoryBlock {
            label: String,
            value: String,
        }
        let url = format!("{}/v1/agents", self.base_url.trim_end_matches('/'));
        let ade = std::env::var("LETTA_ADE_MODE")
            .unwrap_or_else(|_| "false".into())
            .to_lowercase()
            == "true";
        let name = if ade {
            "Godoty Agent (ADE)"
        } else {
            "Godoty Agent"
        };
        let embedding = std::env::var("LETTA_EMBEDDING")
            .unwrap_or_else(|_| "openai/text-embedding-3-small".to_string());
        let body = CreateAgent {
            name: name.to_string(),
            model: self.model.clone(),
            embedding,
            memory_blocks: None,
        };
        let resp = self
            .client
            .post(url)
            .bearer_auth(&self.api_key)
            .json(&body)
            .send()
            .await?;
        if !resp.status().is_success() {
            let status = resp.status();
            let s = resp.text().await.unwrap_or_default();
            return Err(anyhow!(
                "Letta create agent failed: {} - {}",
                status,
                s.chars().take(300).collect::<String>()
            ));
        }
        let txt = resp.text().await?;
        let v: Value = serde_json::from_str(&txt)
            .map_err(|e| anyhow!("Letta create agent parse error: {} raw:{}", e, txt))?;
        let id = v
            .get("id")
            .and_then(|x| x.as_str())
            .ok_or_else(|| anyhow!("Letta create agent: missing id"))?;
        Ok(id.to_string())
    }

    async fn stream_message(
        &self,
        window: &tauri::Window,
        agent_id: &str,
        content: &str,
        session_id: Option<&str>,
    ) -> Result<(String, Vec<String>, Option<u32>)> {
        // Returns (assistant_text, reasoning_chunks, total_tokens)
        #[derive(Serialize)]
        struct Msg {
            role: String,
            content: String,
        }
        #[derive(Serialize)]
        struct Body {
            messages: Vec<Msg>,
            #[serde(skip_serializing_if = "Option::is_none", rename = "stream_tokens")]
            stream_tokens: Option<bool>,
        }
        let url = format!(
            "{}/v1/agents/{}/messages/stream",
            self.base_url.trim_end_matches('/'),
            agent_id
        );
        let body = Body {
            messages: vec![Msg {
                role: "user".into(),
                content: content.to_string(),
            }],
            stream_tokens: Some(true),
        };
        let mut resp = self
            .client
            .post(url)
            .bearer_auth(&self.api_key)
            .json(&body)
            .send()
            .await?;
        if !resp.status().is_success() {
            let status = resp.status();
            let s = resp.text().await.unwrap_or_default();
            return Err(anyhow!(
                "Letta stream failed: {} - {}",
                status,
                s.chars().take(300).collect::<String>()
            ));
        }
        let mut buffer = String::new();
        let mut full_out = String::new();
        let mut reasoning: Vec<String> = Vec::new();
        let mut total_tokens: Option<u32> = None;

        while let Some(chunk) = resp.chunk().await? {
            let s = String::from_utf8_lossy(&chunk);
            buffer.push_str(&s);
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
                        if let Ok(v) = serde_json::from_str::<Value>(data) {
                            if let Some(mt) = v.get("message_type").and_then(|x| x.as_str()) {
                                match mt {
                                    "assistant_message" => {
                                        if let Some(piece) =
                                            v.get("content").and_then(|x| x.as_str())
                                        {
                                            full_out.push_str(piece);
                                            let _ = window.emit(
                                                "tool-call-delta",
                                                json!({
                                                    "event": "llm_stream",
                                                    "delta": piece,
                                                    "model": "letta",
                                                    "sessionId": session_id,
                                                }),
                                            );
                                        }
                                    }
                                    "reasoning_message" => {
                                        if let Some(p) = v.get("reasoning").and_then(|x| x.as_str())
                                        {
                                            reasoning.push(p.to_string());
                                        }
                                    }
                                    "usage_statistics" => {
                                        if let Some(t) =
                                            v.get("total_tokens").and_then(|x| x.as_u64())
                                        {
                                            total_tokens = Some(t as u32);
                                        }
                                    }
                                    "tool_call" | "tool_call_message" => {
                                        let name = v
                                            .get("tool_name")
                                            .and_then(|x| x.as_str())
                                            .or_else(|| {
                                                v.get("tool")
                                                    .and_then(|t| t.get("name"))
                                                    .and_then(|x| x.as_str())
                                            })
                                            .unwrap_or("");
                                        let args = v
                                            .get("parameters")
                                            .cloned()
                                            .or_else(|| v.get("arguments").cloned())
                                            .unwrap_or_else(|| json!({}));
                                        reasoning.push(format!("TOOL CALL: {} {}", name, args));
                                        let _ = window.emit(
                                            "tool-call-delta",
                                            json!({
                                                "event": "tool_call",
                                                "name": name,
                                                "args": args,
                                                "model": "letta",
                                                "sessionId": session_id,
                                            }),
                                        );
                                    }
                                    "tool_return" | "tool_return_message" => {
                                        let result = v
                                            .get("tool_return")
                                            .cloned()
                                            .or_else(|| v.get("result").cloned())
                                            .unwrap_or_else(|| json!(null));
                                        reasoning.push(format!("TOOL RETURN: {}", result));
                                        let _ = window.emit(
                                            "tool-call-delta",
                                            json!({
                                                "event": "tool_return",
                                                "result": result,
                                                "model": "letta",
                                                "sessionId": session_id,
                                            }),
                                        );
                                    }
                                    _ => {}
                                }
                            }
                        }
                    }
                } else {
                    break;
                }
            }
        }
        let _ = window.emit(
            "tool-call-delta",
            json!({
                "event": "llm_stream_completed",
                "text": full_out,
                "model": "letta",
                "sessionId": session_id,
            }),
        );
        Ok((full_out, reasoning, total_tokens))
    }

    pub async fn execute(
        &self,
        window: &tauri::Window,
        session_id: Option<&str>,
        context: &AgentContext,
        existing_agent_id: Option<&str>,
    ) -> Result<(AgentResponse, String)> {
        // Build knowledge snippets
        let plugin_docs = context
            .plugin_kb
            .search(&context.user_input, 5)
            .await
            .unwrap_or_default();
        let docs_docs = context
            .docs_kb
            .search(&context.user_input, 5)
            .await
            .unwrap_or_default();
        let plugin_snips = plugin_docs
            .iter()
            .map(|d| format!("- {}: {}", d.id, d.content))
            .collect::<Vec<_>>()
            .join("\n");
        let docs_snips = docs_docs
            .iter()
            .map(|d| format!("- {}", d.content.chars().take(200).collect::<String>()))
            .collect::<Vec<_>>()
            .join("\n");

        let sys = format!(
            r#"You are Godoty's agent for Godot development. You may either:
(1) return a strict JSON plan + commands, or
(2) call tools to search knowledge bases and run Godot commands.
Prefer tools when additional context or actions are needed.

STRICT JSON OUTPUT (when not using tools):
- Object with keys: reasoning, steps, estimated_complexity, commands
- steps: array of {{"step_number": number, "description": string, "commands_needed": [string]}}
- commands: array of command objects matching the plugin schema (action, type/name/path/properties...)
No prose outside the JSON. Ensure valid JSON without trailing commas.

Project Context: Total Scenes: {} | Total Scripts: {}
Plugin Command Examples:\n{}
Relevant Godot Docs:\n{}
"#,
            context.project_index.scenes.len(),
            context.project_index.scripts.len(),
            plugin_snips,
            docs_snips
        );
        let user = context.user_input.clone();
        let agent_id = match existing_agent_id {
            Some(id) if !id.is_empty() => id.to_string(),
            _ => self.create_agent().await?,
        };
        let prompt = format!("{}\n\nUSER:\n{}", sys, user);
        let (text, reasoning_chunks, total_tokens) = self
            .stream_message(window, &agent_id, &prompt, session_id)
            .await?;

        // Extract JSON from response
        let json_str =
            extract_json_simple(&text).ok_or_else(|| anyhow!("No JSON found in Letta response"))?;
        let val: Value = serde_json::from_str(&json_str)
            .map_err(|e| anyhow!("Invalid JSON from Letta: {}", e))?;
        let plan: ExecutionPlan =
            serde_json::from_value(val.clone()).map_err(|e| anyhow!("Plan parse failed: {}", e))?;
        let commands = val
            .get("commands")
            .cloned()
            .and_then(|v| v.as_array().cloned())
            .unwrap_or_default();

        // Build thoughts from reasoning chunks
        let mut thoughts: Vec<AgentThought> = Vec::new();
        for (i, t) in reasoning_chunks.iter().enumerate() {
            thoughts.push(AgentThought {
                step: i + 1,
                thought: t.clone(),
                action: Some("reasoning".into()),
                observation: None,
            });
        }

        // Minimal metrics
        let mut metrics =
            WorkflowMetrics::new(uuid::Uuid::new_v4().to_string(), context.user_input.clone());
        metrics.total_tokens = total_tokens.unwrap_or(0) as u32;
        metrics.finalize(true, None);

        Ok((
            AgentResponse {
                commands: commands.into_iter().collect(),
                thoughts,
                plan,
                knowledge_used: KnowledgeUsed {
                    plugin_docs: plugin_docs.iter().map(|d| d.id.clone()).collect(),
                    godot_docs: docs_docs.iter().map(|d| d.id.clone()).collect(),
                },
                metrics: Some(metrics),
            },
            agent_id,
        ))
    }
}

fn extract_json_simple(s: &str) -> Option<String> {
    // Try fenced code block first
    if let Some(pos) = s.find("```json") {
        let start = pos + 7;
        if let Some(end) = s[start..].find("```") {
            return Some(s[start..start + end].trim().to_string());
        }
    }
    // Fallback: outermost braces
    if let (Some(a), Some(b)) = (s.find('{'), s.rfind('}')) {
        if b > a {
            return Some(s[a..=b].to_string());
        }
    }
    None
}
