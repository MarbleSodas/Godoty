use crate::llm_client::{LiteLlmClient, LlmClient};
use anyhow::{anyhow, Result};

#[derive(Clone)]
pub struct TutorialProcessor;

impl TutorialProcessor {
    pub fn new() -> Self {
        Self
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

        let prompt = format!(
            "Find concise, high-quality tutorial summaries and links for Godot {} about: '{}'. If the version differs, prefer matching major.minor. Return bullet list with titles and URLs.\nIMPORTANT: Label this content as Tutorials so it is clearly tutorial-sourced.",
            godot_version.unwrap_or("4.x"), topic
        );

        // Route via LiteLLM unified client
        let base = std::env::var("LITELLM_BASE_URL").unwrap_or_default();
        let key = std::env::var("LITELLM_API_KEY").unwrap_or_default();
        if base.trim().is_empty() || key.trim().is_empty() {
            return Err(anyhow!(
                "LiteLLM not configured. Set LITELLM_BASE_URL and LITELLM_API_KEY."
            ));
        }
        let client = LiteLlmClient::new(base, key, "docs-free".to_string());
        let system = "You are a research assistant that finds Godot tutorials.";
        let out = client.generate_response(system, &prompt).await?;
        Ok(out)
    }
}
