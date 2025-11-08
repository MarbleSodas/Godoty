use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};

#[derive(Clone)]
pub struct VisionProcessor {
    api_key: String,
    client: Client,
}

impl VisionProcessor {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
        }
    }

    pub async fn analyze_visual_context(
        &self,
        image_b64: &str,
        meta: &serde_json::Value,
    ) -> Result<String> {
        // Offline or missing image -> return lightweight description
        if std::env::var("GODOTY_OFFLINE").ok().as_deref() == Some("1") || image_b64.is_empty() {
            return Ok(format!("[Visual Analysis Offline]\nMeta: {}\n", meta));
        }

        // Some OpenRouter vision models accept base64 images via content text. We degrade gracefully if it fails.
        #[derive(Serialize)]
        struct Msg {
            role: String,
            content: String,
        }
        #[derive(Serialize)]
        struct Req {
            model: String,
            messages: Vec<Msg>,
            temperature: f32,
            max_tokens: i32,
        }
        #[derive(Deserialize)]
        struct Resp {
            choices: Vec<Choice>,
        }
        #[derive(Deserialize)]
        struct Choice {
            message: MsgResp,
        }
        #[derive(Deserialize)]
        struct MsgResp {
            content: String,
        }

        let prompt = format!(
            "You are a Godot scene visual analyzer. Given a base64 PNG of the editor viewport and inspector selection metadata, describe key nodes, UI layout, and likely scene structure. Provide concise, bullet-style findings.\n\nInspector/Scene Meta (JSON): {}\n\nIMAGE_BASE64 (PNG): {}\n",
            meta, image_b64
        );

        let req = Req {
            model: "nvidia/nemotron-nano-12b-v2-vl:free".to_string(),
            messages: vec![
                Msg {
                    role: "system".into(),
                    content: "Analyze visual context of Godot scenes and be precise.".into(),
                },
                Msg {
                    role: "user".into(),
                    content: prompt,
                },
            ],
            temperature: 0.2,
            max_tokens: 300,
        };

        let resp = self
            .client
            .post("https://openrouter.ai/api/v1/chat/completions")
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", "application/json")
            .header("HTTP-Referer", "https://github.com/godoty/godoty")
            .header("X-Title", "Godoty AI Assistant")
            .json(&req)
            .send()
            .await;

        match resp {
            Ok(rsp) if rsp.status().is_success() => {
                let body = rsp.text().await.unwrap_or_default();
                if let Ok(parsed) = serde_json::from_str::<Resp>(&body) {
                    if let Some(choice) = parsed.choices.first() {
                        return Ok(choice.message.content.clone());
                    }
                }
                Ok("[Visual Analysis] Unable to parse response".to_string())
            }
            Ok(rsp) => Ok(format!(
                "[Visual Analysis] API error status {}",
                rsp.status()
            )),
            Err(e) => Ok(format!("[Visual Analysis] Request failed: {}", e)),
        }
    }
}
