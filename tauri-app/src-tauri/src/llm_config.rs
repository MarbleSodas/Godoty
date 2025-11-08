use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Supported LLM providers
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq, Hash)]
pub enum LlmProvider {
    OpenRouter, // For services like OpenRouter that aggregate multiple providers
    ZaiGlm,     // Z.AI GLM official API
}

/// Types of agents in the agentic workflow
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq, Hash)]
pub enum AgentType {
    Planner,
    CodeGenerator,
    Vision,
    Researcher,
    Validator,
    Documentation,
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
}

impl Default for AgentLlmConfig {
    fn default() -> Self {
        let mut agents = HashMap::new();

        // Default configuration using OpenRouter with free models
        agents.insert(
            AgentType::Planner,
            ModelSelection {
                provider: LlmProvider::OpenRouter,
                model_name: "minimax/minimax-m2:free".to_string(),
            },
        );
        agents.insert(
            AgentType::CodeGenerator,
            ModelSelection {
                provider: LlmProvider::OpenRouter,
                model_name: "qwen/qwen3-coder:free".to_string(),
            },
        );
        agents.insert(
            AgentType::Vision,
            ModelSelection {
                provider: LlmProvider::OpenRouter,
                model_name: "nvidia/nemotron-nano-12b-v2-vl:free".to_string(),
            },
        );
        agents.insert(
            AgentType::Researcher,
            ModelSelection {
                provider: LlmProvider::OpenRouter,
                model_name: "qwen/qwen3-235b-a22b:free".to_string(),
            },
        );
        agents.insert(
            AgentType::Validator,
            ModelSelection {
                provider: LlmProvider::OpenRouter,
                model_name: "z-ai/glm-4.5-air:free".to_string(),
            },
        );
        agents.insert(
            AgentType::Documentation,
            ModelSelection {
                provider: LlmProvider::OpenRouter,
                model_name: "meta-llama/llama-3.3-70b-instruct:free".to_string(),
            },
        );

        Self { agents }
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

    models.insert(
        LlmProvider::OpenRouter,
        vec![
            "minimax/minimax-m2:free".to_string(),
            "qwen/qwen3-coder:free".to_string(),
            "qwen/qwen3-235b-a22b:free".to_string(),
            "meta-llama/llama-3.3-70b-instruct:free".to_string(),
            "z-ai/glm-4.5-air:free".to_string(),
            "nvidia/nemotron-nano-12b-v2-vl:free".to_string(),
            "google/gemini-2.0-flash-thinking-exp:free".to_string(),
            "google/gemini-2.0-flash-exp:free".to_string(),
            "anthropic/claude-3.5-sonnet".to_string(),
            "openai/gpt-4o".to_string(),
        ],
    );

    // Z.AI GLM official API models
    models.insert(
        LlmProvider::ZaiGlm,
        vec![
            "glm-4.5".to_string(),
            "glm-4".to_string(),
            "glm-4-air".to_string(),
            "glm-4-plus".to_string(),
            "glm-4-long".to_string(),
            "glm-4v".to_string(),
            "glm-4.5-flash".to_string(),
            "glm-4.6".to_string(),
        ],
    );

    models
}

/// Helper to list all known providers
pub fn all_providers() -> Vec<LlmProvider> {
    vec![
        LlmProvider::OpenRouter,
        LlmProvider::ZaiGlm,
    ]
}
