use crate::chat_session::ChatSession;
use crate::context_engine::{ComprehensiveContext, ContextEngine};
use crate::project_indexer::ProjectIndex;
use crate::unified_context::{UnifiedProjectContext, AgentContextType};
use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;

/// Requirements for building context for different agent types
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextRequirements {
    /// Type of agent requesting context
    pub agent_type: AgentContextType,

    /// Maximum tokens allowed for this context
    pub max_tokens: usize,

    /// Specific topics or concepts to focus on
    pub focus_areas: Vec<String>,

    /// Whether to include detailed code examples
    pub include_examples: bool,

    /// Whether to include historical context
    pub include_history: bool,

    /// Priority of different context sources
    pub source_priorities: HashMap<ContextSource, f32>,
}

/// Context sources that can be prioritized
#[derive(Debug, Clone, Serialize, Deserialize, Hash, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum ContextSource {
    ProjectIndex,
    RagSearch,
    GodotDocs,
    Context7,
    ToolReferences,
    ChatHistory,
    VisualContext,
}

/// Context cache entry with expiration
#[derive(Debug, Clone)]
struct ContextCacheEntry {
    context: UnifiedProjectContext,
    created_at: chrono::DateTime<chrono::Utc>,
    query_hash: u64,
}

/// Centralized context manager for all agents
pub struct ContextManager {
    /// Core context engine
    context_engine: ContextEngine,

    /// Cache for built contexts to avoid rebuilding
    context_cache: Arc<RwLock<HashMap<String, ContextCacheEntry>>>,

    /// Configuration for cache behavior
    cache_config: CacheConfig,

    /// Statistics tracking
    stats: Arc<RwLock<ContextStats>>,
}

/// Configuration for context caching
#[derive(Debug, Clone)]
pub struct CacheConfig {
    /// Maximum number of cached contexts
    max_cache_entries: usize,

    /// Cache entry TTL in seconds
    cache_ttl_seconds: u64,

    /// Whether to enable query-based caching
    enable_query_caching: bool,
}

/// Statistics for context operations
#[derive(Debug, Default, Clone)]
pub struct ContextStats {
    /// Total context builds
    pub total_builds: u64,

    /// Cache hits
    pub cache_hits: u64,

    /// Cache misses
    pub cache_misses: u64,

    /// Average build time in milliseconds
    pub avg_build_time_ms: f64,

    /// Total tokens processed
    pub total_tokens_processed: u64,
}

impl Default for CacheConfig {
    fn default() -> Self {
        Self {
            max_cache_entries: 50,
            cache_ttl_seconds: 300, // 5 minutes
            enable_query_caching: true,
        }
    }
}

impl ContextManager {
    /// Create a new context manager
    pub fn new(api_key: &str) -> Self {
        Self {
            context_engine: ContextEngine::new(api_key),
            context_cache: Arc::new(RwLock::new(HashMap::new())),
            cache_config: CacheConfig::default(),
            stats: Arc::new(RwLock::new(ContextStats::default())),
        }
    }

    /// Create a context manager with custom cache configuration
    pub fn with_config(api_key: &str, cache_config: CacheConfig) -> Self {
        Self {
            context_engine: ContextEngine::new(api_key),
            context_cache: Arc::new(RwLock::new(HashMap::new())),
            cache_config,
            stats: Arc::new(RwLock::new(ContextStats::default())),
        }
    }

    /// Build unified context for a specific agent request
    pub async fn build_unified_context(
        &self,
        user_input: &str,
        project_path: &str,
        project_index: &ProjectIndex,
        chat_session: Option<&ChatSession>,
        requirements: &ContextRequirements,
    ) -> Result<UnifiedProjectContext> {
        let start_time = std::time::Instant::now();

        // Check cache first if enabled
        let cache_key = if self.cache_config.enable_query_caching {
            Some(self.generate_cache_key(user_input, project_path, requirements))
        } else {
            None
        };

        if let Some(key) = &cache_key {
            if let Some(cached) = self.check_cache(key).await {
                let mut stats = self.stats.write().await;
                stats.cache_hits += 1;
                tracing::debug!(
                    cache_key = %key,
                    "Context cache hit"
                );
                return Ok(cached);
            }

            let mut stats = self.stats.write().await;
            stats.cache_misses += 1;
        }

        // Build comprehensive context using the existing context engine
        let max_history = if requirements.include_history { 10 } else { 0 };
        let comprehensive = self
            .context_engine
            .build_comprehensive_context(user_input, project_index, chat_session, max_history)
            .await?;

        // Convert to unified context with agent-specific optimizations
        let mut unified = UnifiedProjectContext::from_comprehensive(comprehensive, project_index.clone());

        // Apply agent-specific optimizations
        self.optimize_context_for_agent(&mut unified, requirements).await?;

        // Cache the result if caching is enabled
        if let Some(key) = cache_key {
            self.store_cache(key, unified.clone()).await;
        }

        // Update statistics
        {
            let mut stats = self.stats.write().await;
            stats.total_builds += 1;
            stats.total_tokens_processed += unified.metadata.total_tokens as u64;

            let build_time_ms = start_time.elapsed().as_millis() as f64;
            stats.avg_build_time_ms = (stats.avg_build_time_ms * (stats.total_builds - 1) as f64 + build_time_ms) / stats.total_builds as f64;
        }

        tracing::info!(
            summary = %unified.get_summary(),
            build_time_ms = %start_time.elapsed().as_millis(),
            "Built unified context"
        );

        Ok(unified)
    }

    /// Optimize context based on agent requirements
    async fn optimize_context_for_agent(
        &self,
        unified: &mut UnifiedProjectContext,
        requirements: &ContextRequirements,
    ) -> Result<()> {
        match requirements.agent_type {
            AgentContextType::Research => {
                self.optimize_for_research(unified, requirements).await?;
            }
            AgentContextType::Orchestrator => {
                self.optimize_for_orchestrator(unified, requirements).await?;
            }
        }

        // Apply token limit if specified
        if requirements.max_tokens > 0 && unified.metadata.total_tokens > requirements.max_tokens {
            self.truncate_to_token_limit(unified, requirements.max_tokens).await?;
        }

        Ok(())
    }

    /// Optimize context for research agent needs
    async fn optimize_for_research(
        &self,
        unified: &mut UnifiedProjectContext,
        requirements: &ContextRequirements,
    ) -> Result<()> {
        // Prioritize comprehensive documentation and code analysis
        let mut docs = unified.documentation.godot_docs.clone();

        // Add focus areas to documentation if specified
        if !requirements.focus_areas.is_empty() {
            let focus_section = requirements.focus_areas.join(", ");
            docs = format!(
                "{}\n\n# Research Focus Areas\n{}\n",
                docs, focus_section
            );
        }

        // For research, include more detailed code examples if requested
        if requirements.include_examples {
            // TODO: Fetch more detailed examples based on focus areas
            docs.push_str("\n\n# Code Examples\nSee project scripts for concrete implementations.\n");
        }

        unified.documentation.godot_docs = docs;

        // Ensure RAG results are prioritized for research
        if let Some(rag_results) = &unified.vector_search_results {
            if !rag_results.is_empty() {
                tracing::debug!(
                    rag_count = rag_results.len(),
                    "RAG results available for research context"
                );
            }
        }

        Ok(())
    }

    /// Optimize context for orchestrator agent needs
    async fn optimize_for_orchestrator(
        &self,
        unified: &mut UnifiedProjectContext,
        requirements: &ContextRequirements,
    ) -> Result<()> {
        // For orchestrator, prioritize tool references and execution context
        let mut tool_refs = unified.documentation.tool_references.clone();

        if tool_refs.is_empty() {
            // Add basic tool references if not available
            tool_refs = r#"# Available Tools
- Godot Editor Commands (create_node, modify_node, attach_script, etc.)
- Desktop Commander MCP Tools (file operations, search, process management)
- Sequential Thinking Tools (analysis, brainstorming)
- Context7 Documentation Access
"#.to_string();
        }

        unified.documentation.tool_references = tool_refs;

        // Add execution-specific metadata
        let execution_context = format!(
            "\n# Execution Context\nProject: {}\nAgent: Orchestrator\nTimestamp: {}\n",
            unified.structured_index.project_path,
            unified.metadata.built_at.format("%Y-%m-%d %H:%M:%S UTC")
        );

        unified.metadata.build_errors.push(execution_context);

        Ok(())
    }

    /// Truncate context to fit within token limits
    async fn truncate_to_token_limit(&self, unified: &mut UnifiedProjectContext, max_tokens: usize) -> Result<()> {
        let current_tokens = unified.metadata.total_tokens;
        if current_tokens <= max_tokens {
            return Ok(());
        }

        tracing::warn!(
            current_tokens = current_tokens,
            max_tokens = max_tokens,
            "Truncating context to fit token limit"
        );

        // Prioritize truncation:
        // 1. Reduce documentation first (keep essential parts)
        // 2. Reduce RAG results (keep highest scored)
        // 3. Reduce project details (keep most relevant)

        let reduction_needed = current_tokens - max_tokens;
        let mut reduced = 0;

        // Truncate documentation (keep 70%)
        if unified.documentation.godot_docs.len() > 1000 {
            let target_len = (unified.documentation.godot_docs.len() * 7) / 10;
            let reduction = unified.documentation.godot_docs.len() - target_len;
            unified.documentation.godot_docs.truncate(target_len);
            reduced += reduction / 4; // Rough token estimate
        }

        // Reduce RAG results if still over limit
        if let Some(rag_results) = &mut unified.vector_search_results {
            let target_results = (rag_results.len() * 7) / 10;
            let removed_count = rag_results.len() - target_results;
            rag_results.truncate(target_results);
            reduced += removed_count * 50; // Estimate tokens per RAG result
        }

        // Update token count
        unified.metadata.total_tokens = current_tokens - reduced;
        unified.metadata.warnings.push(format!(
            "Context truncated from {} to {} tokens to fit limit",
            current_tokens,
            unified.metadata.total_tokens
        ));

        Ok(())
    }

    /// Generate cache key for context request
    fn generate_cache_key(&self, user_input: &str, project_path: &str, requirements: &ContextRequirements) -> String {
        use std::hash::{Hash, Hasher};
        let mut hasher = std::collections::hash_map::DefaultHasher::new();

        user_input.hash(&mut hasher);
        project_path.hash(&mut hasher);

        // Include agent type in hash
        format!("{:?}", requirements.agent_type).hash(&mut hasher);

        // Include focus areas in hash
        requirements.focus_areas.join(",").hash(&mut hasher);

        format!("ctx_{:x}", hasher.finish())
    }

    /// Check if context is cached and still valid
    async fn check_cache(&self, cache_key: &str) -> Option<UnifiedProjectContext> {
        let cache = self.context_cache.read().await;
        if let Some(entry) = cache.get(cache_key) {
            let age = chrono::Utc::now() - entry.created_at;
            if age.num_seconds() < self.cache_config.cache_ttl_seconds as i64 {
                return Some(entry.context.clone());
            }
        }
        None
    }

    /// Store context in cache
    async fn store_cache(&self, cache_key: String, context: UnifiedProjectContext) {
        let mut cache = self.context_cache.write().await;

        // Remove old entries if cache is full
        if cache.len() >= self.cache_config.max_cache_entries {
            // Simple LRU: remove the oldest entry
            if let Some(oldest_key) = cache
                .iter()
                .min_by_key(|(_, entry)| entry.created_at)
                .map(|(k, _)| k.clone())
            {
                cache.remove(&oldest_key);
            }
        }

        let entry = ContextCacheEntry {
            context,
            created_at: chrono::Utc::now(),
            query_hash: self.calculate_query_hash(&cache_key),
        };

        cache.insert(cache_key, entry);
    }

    /// Calculate query hash for cache tracking
    fn calculate_query_hash(&self, cache_key: &str) -> u64 {
        use std::hash::{Hash, Hasher};
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        cache_key.hash(&mut hasher);
        hasher.finish()
    }

    /// Clear expired cache entries
    pub async fn clear_expired_cache(&self) {
        let mut cache = self.context_cache.write().await;
        let now = chrono::Utc::now();

        cache.retain(|_, entry| {
            let age = now - entry.created_at;
            age.num_seconds() < self.cache_config.cache_ttl_seconds as i64
        });
    }

    /// Get context statistics
    pub async fn get_stats(&self) -> ContextStats {
        self.stats.read().await.clone()
    }

    /// Reset statistics
    pub async fn reset_stats(&self) {
        let mut stats = self.stats.write().await;
        *stats = ContextStats::default();
    }

    /// Preload common contexts for better performance
    pub async fn preload_common_contexts(
        &self,
        project_index: &ProjectIndex,
        common_queries: &[&str],
    ) -> Result<()> {
        tracing::info!(
            query_count = common_queries.len(),
            "Preloading common contexts"
        );

        for query in common_queries {
            let requirements = ContextRequirements {
                agent_type: AgentContextType::Research,
                max_tokens: 4000,
                focus_areas: vec![],
                include_examples: true,
                include_history: false,
                source_priorities: HashMap::new(),
            };

            // Build and cache context (ignore result, just caching)
            let _ = self
                .build_unified_context(query, &project_index.project_path, project_index, None, &requirements)
                .await;
        }

        tracing::info!("Preloaded common contexts");
        Ok(())
    }

    /// Create default requirements for research agent
    pub fn research_requirements() -> ContextRequirements {
        ContextRequirements {
            agent_type: AgentContextType::Research,
            max_tokens: 6000,
            focus_areas: vec![],
            include_examples: true,
            include_history: false,
            source_priorities: {
                let mut priorities = HashMap::new();
                priorities.insert(ContextSource::ProjectIndex, 1.0);
                priorities.insert(ContextSource::RagSearch, 0.9);
                priorities.insert(ContextSource::GodotDocs, 0.8);
                priorities.insert(ContextSource::Context7, 0.7);
                priorities
            },
        }
    }

    /// Create default requirements for orchestrator agent
    pub fn orchestrator_requirements() -> ContextRequirements {
        ContextRequirements {
            agent_type: AgentContextType::Orchestrator,
            max_tokens: 4000,
            focus_areas: vec![],
            include_examples: false,
            include_history: true,
            source_priorities: {
                let mut priorities = HashMap::new();
                priorities.insert(ContextSource::ToolReferences, 1.0);
                priorities.insert(ContextSource::ProjectIndex, 0.8);
                priorities.insert(ContextSource::GodotDocs, 0.6);
                priorities.insert(ContextSource::ChatHistory, 0.7);
                priorities
            },
        }
    }
}