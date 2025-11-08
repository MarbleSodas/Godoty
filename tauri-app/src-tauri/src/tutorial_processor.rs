use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};

#[derive(Clone)]
pub struct TutorialProcessor {
    api_key: String,
    client: Client,
}

impl TutorialProcessor {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
        }
    }

    pub async fn fetch_godot_tutorials(
        &self,
        topic: &str,
        godot_version: Option<&str>,
    ) -> Result<String> {
        if std::env::var("GODOTY_OFFLINE").ok().as_deref() == Some("1") {
            return Ok(format!(
                "[Tutorials Offline] topic='{}' version='{}'",
                topic,
                godot_version.unwrap_or("unknown")
            ));
        }

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
            "Find concise, high-quality tutorial summaries and links for Godot {} about: '{}'. If the version differs, prefer matching major.minor. Return bullet list with titles and URLs.\nIMPORTANT: Label this content as Tutorials so it is clearly tutorial-sourced.",
            godot_version.unwrap_or("4.x"), topic
        );

        let req = Req {
            model: "tngtech/deepseek-r1t2-chimera:free".to_string(),
            messages: vec![
                Msg {
                    role: "system".into(),
                    content: "You are a research assistant that finds Godot tutorials.".into(),
                },
                Msg {
                    role: "user".into(),
                    content: prompt,
                },
            ],
            temperature: 0.3,
            max_tokens: 500,
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
                Ok("[Tutorials] Unable to parse response".to_string())
            }
            Ok(rsp) => Ok(format!("[Tutorials] API error status {}", rsp.status())),
            Err(e) => Ok(format!("[Tutorials] Request failed: {}", e)),
        }
    }
}
