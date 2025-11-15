use crate::dynamic_context_provider::{DynamicProjectContextProvider, FileWatcherConfig};
use crate::strands_agent::{OrchestratorAgent, PlanningAgent};
use crate::context_engine::ContextEngine;
use crate::project_indexer::ProjectIndexer;
use std::path::PathBuf;
use std::sync::Arc;
use anyhow::Result;

/// Factory for creating agents with dynamic context support
#[allow(dead_code)] // Agent factory - enhancement plan Phase 1
pub struct AgentFactory;

#[allow(dead_code)] // Agent factory methods - enhancement plan Phase 1
impl AgentFactory {
    /// Create an OrchestratorAgent with dynamic context enabled
    pub async fn create_orchestrator_with_dynamic_context(
        api_key: &str,
        project_path: &str,
        watcher_config: Option<FileWatcherConfig>,
    ) -> Result<OrchestratorAgent> {
        // Create required components
        let context_engine = Arc::new(ContextEngine::new(api_key));
        let project_path = PathBuf::from(project_path);
        let indexer = Arc::new(ProjectIndexer::new(&project_path.to_string_lossy()));

        // Create dynamic context provider
        let (provider, _update_rx) = DynamicProjectContextProvider::new(
            project_path,
            Some(watcher_config.unwrap_or_default()),
            context_engine,
            indexer,
        ).await?;

        // Start file watching
        provider.start_watching().await?;

        // Create and return orchestrator with dynamic context
        Ok(OrchestratorAgent::new(api_key)
            .with_dynamic_context_provider(Some(Arc::new(provider))))
    }

    /// Create a PlanningAgent with dynamic context enabled
    pub async fn create_planner_with_dynamic_context(
        api_key: &str,
        project_path: &str,
        watcher_config: Option<FileWatcherConfig>,
    ) -> Result<PlanningAgent> {
        // Create required components
        let context_engine = Arc::new(ContextEngine::new(api_key));
        let project_path = PathBuf::from(project_path);
        let indexer = Arc::new(ProjectIndexer::new(&project_path.to_string_lossy()));

        // Create dynamic context provider
        let (provider, _update_rx) = DynamicProjectContextProvider::new(
            project_path,
            Some(watcher_config.unwrap_or_default()),
            context_engine,
            indexer,
        ).await?;

        // Start file watching
        provider.start_watching().await?;

        // Create and return planner with dynamic context
        Ok(PlanningAgent::new(api_key)
            .with_dynamic_context_provider(Some(Arc::new(provider))))
    }

    /// Create both agents sharing the same dynamic context provider
    pub async fn create_agent_pair_with_shared_context(
        api_key: &str,
        project_path: &str,
        watcher_config: Option<FileWatcherConfig>,
    ) -> Result<(OrchestratorAgent, PlanningAgent)> {
        // Create required components
        let context_engine = Arc::new(ContextEngine::new(api_key));
        let project_path = PathBuf::from(project_path);
        let indexer = Arc::new(ProjectIndexer::new(&project_path.to_string_lossy()));

        // Create shared dynamic context provider
        let (provider, _update_rx) = DynamicProjectContextProvider::new(
            project_path,
            Some(watcher_config.unwrap_or_default()),
            context_engine.clone(),
            indexer,
        ).await?;

        // Start file watching
        provider.start_watching().await?;

        // Wrap in Arc for sharing
        let provider_arc = Arc::new(provider);

        // Create both agents with the same dynamic context provider
        let orchestrator = OrchestratorAgent::new(api_key)
            .with_dynamic_context_provider(Some(provider_arc.clone()));

        let planner = PlanningAgent::new(api_key)
            .with_dynamic_context_provider(Some(provider_arc));

        Ok((orchestrator, planner))
    }
}

/// Configuration for agent creation
#[derive(Debug, Clone)]
#[allow(dead_code)] // Agent configuration - enhancement plan Phase 1
pub struct AgentConfig {
    pub project_path: String,
    pub enable_file_watching: bool,
    pub watcher_config: Option<FileWatcherConfig>,
    pub llm_factory: Option<crate::llm_client::LlmFactory>,
}

impl Default for AgentConfig {
    fn default() -> Self {
        Self {
            project_path: "".to_string(),
            enable_file_watching: true,
            watcher_config: None,
            llm_factory: None,
        }
    }
}

/// Extended factory with configuration support
#[allow(dead_code)] // Agent factory methods - enhancement plan Phase 1
impl AgentFactory {
    /// Create agents with full configuration
    pub async fn create_with_config(
        api_key: &str,
        config: AgentConfig,
    ) -> Result<(OrchestratorAgent, PlanningAgent)> {
        let (mut orchestrator, mut planner) = if config.enable_file_watching && !config.project_path.is_empty() {
            Self::create_agent_pair_with_shared_context(
                api_key,
                &config.project_path,
                config.watcher_config,
            ).await?
        } else {
            (
                OrchestratorAgent::new(api_key),
                PlanningAgent::new(api_key),
            )
        };

        // Apply LLM factory if provided
        if let Some(factory) = config.llm_factory {
            orchestrator = orchestrator.with_llm_factory(Some(factory.clone()));
            planner = planner.with_llm_factory(Some(factory));
        }

        Ok((orchestrator, planner))
    }
}