use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Supported LLM providers
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq, Hash)]
pub enum LlmProvider {
    OpenRouter, // For services like OpenRouter that aggregate multiple providers
}

/// Types of agents in the agentic workflow
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq, Hash)]
pub enum AgentType {
    Orchestrator,
    Planning,
}

/// Model selection for a specific agent
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct ModelSelection {
    pub provider: LlmProvider,
    pub model_name: String,
}

/// Main configuration struct that maps each agent to a model
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct AgentLlmConfig {
    pub agents: HashMap<AgentType, ModelSelection>,
    /// Enable tool calling mode for orchestrator (allows direct MCP tool access)
    #[serde(default)]
    pub enable_tool_calling: bool,
}

impl Default for AgentLlmConfig {
    fn default() -> Self {
        let mut agents = HashMap::new();

        // Default configuration using OpenRouter with high-performance models
        agents.insert(
            AgentType::Orchestrator,
            ModelSelection {
                provider: LlmProvider::OpenRouter,
                model_name: "minimax/minimax-m2".to_string(),
            },
        );

        agents.insert(
            AgentType::Planning,
            ModelSelection {
                provider: LlmProvider::OpenRouter,
                model_name: "openai/gpt-5.1-codex".to_string(),
            },
        );


        Self {
            agents,
            enable_tool_calling: true, // Enable by default for better context gathering
        }
    }
}

/// Secure storage for API keys per provider
#[derive(Serialize, Deserialize, Debug, Clone, Default)]
pub struct ApiKeyStore {
    pub keys: HashMap<LlmProvider, String>,
}

impl ApiKeyStore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn set_key(&mut self, provider: LlmProvider, key: String) {
        self.keys.insert(provider, key);
    }

    pub fn get_key(&self, provider: &LlmProvider) -> Option<&String> {
        self.keys.get(provider)
    }

    #[allow(dead_code)]
    pub fn remove_key(&mut self, provider: &LlmProvider) {
        self.keys.remove(provider);
    }
}

/// Available models per provider (can be expanded or fetched dynamically)
pub fn get_available_models() -> HashMap<LlmProvider, Vec<String>> {
    let mut models = HashMap::new();

    // Models routed via OpenRouter (direct HTTP)
    models.insert(
        LlmProvider::OpenRouter,
        vec![
            "x-ai/grok-4-fast".to_string(),
            "deepseek/deepseek-v3.2-exp".to_string(),
            "openai/gpt-5.1-codex".to_string(),
            "minimax/minimax-m2".to_string(),
        ],
    );

    models
}

/// Helper to list all known providers
pub fn all_providers() -> Vec<LlmProvider> {
    vec![
        LlmProvider::OpenRouter,
    ]
}
