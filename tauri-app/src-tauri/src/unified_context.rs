use crate::context_engine::ComprehensiveContext;
use crate::project_indexer::ProjectIndex;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Unified context that combines all available context sources for agents
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnifiedProjectContext {
    /// Structured project information from the Rust indexer
    pub structured_index: ProjectIndex,

    /// Vector search results from RAG (if available)
    pub vector_search_results: Option<Vec<RagResult>>,

    /// Cached and fetched documentation
    pub documentation: DocumentationCache,

    /// Recent changes in the project (for context awareness)
    pub recent_changes: Vec<ProjectChange>,

    /// Analysis metadata
    pub metadata: ContextMetadata,
}

/// Individual RAG search result with relevance scoring
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RagResult {
    /// Relevance score (0.0 to 1.0)
    pub relevance_score: f64,

    /// Source file path
    pub source_path: String,

    /// Content snippet
    pub content_snippet: String,

    /// Type of content (script, scene, config, etc.)
    pub content_type: ContentType,

    /// Line numbers if applicable
    pub line_range: Option<(usize, usize)>,

    /// Additional metadata
    pub metadata: HashMap<String, String>,
}

/// Documentation cache with different types of documentation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentationCache {
    /// Official Godot documentation relevant to the query
    pub godot_docs: String,

    /// Context7 enriched documentation (if available)
    pub context7_docs: Option<String>,

    /// Tool references and command examples
    pub tool_references: String,

    /// Best practices and patterns
    pub best_practices: Option<String>,

    /// Code examples and templates
    pub code_examples: Vec<CodeExample>,
}

/// Code example with metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CodeExample {
    /// Title of the example
    pub title: String,

    /// Code content
    pub code: String,

    /// Language (gdscript, c#, etc.)
    pub language: String,

    /// Tags for categorization
    pub tags: Vec<String>,

    /// Difficulty level
    pub difficulty: DifficultyLevel,

    /// Associated node types or concepts
    pub related_concepts: Vec<String>,
}

/// Recent project change for context awareness
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectChange {
    /// Type of change
    pub change_type: ChangeType,

    /// File path that was modified
    pub file_path: String,

    /// Description of what changed
    pub description: String,

    /// When the change occurred
    pub timestamp: chrono::DateTime<chrono::Utc>,

    /// Impact level (high, medium, low)
    pub impact_level: ImpactLevel,
}

/// Context metadata for agents
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextMetadata {
    /// When this context was built
    pub built_at: chrono::DateTime<chrono::Utc>,

    /// Total tokens in context
    pub total_tokens: usize,

    /// Context completeness score (0.0 to 1.0)
    pub completeness_score: f64,

    /// Query used to build this context
    pub original_query: String,

    /// Sources that were used
    pub sources_used: Vec<ContextSource>,

    /// Context quality indicators
    pub quality_indicators: QualityIndicators,

    /// Build errors encountered during context construction
    pub build_errors: Vec<String>,

    /// Warnings generated during context construction
    pub warnings: Vec<String>,
}

/// Quality indicators for context
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QualityIndicators {
    /// Whether project index was available and complete
    pub project_index_complete: bool,

    /// Whether RAG search was successful
    pub rag_search_successful: bool,

    /// Whether documentation was fetched successfully
    pub documentation_available: bool,
}

/// Content types for RAG results
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ContentType {
    Script,
    Scene,
    Resource,
    Config,
    Documentation,
    Example,
    Other,
}

impl ContentType {
    pub fn as_str(&self) -> &'static str {
        match self {
            ContentType::Script => "script",
            ContentType::Scene => "scene",
            ContentType::Resource => "resource",
            ContentType::Config => "config",
            ContentType::Documentation => "documentation",
            ContentType::Example => "example",
            ContentType::Other => "other",
        }
    }
}

impl std::fmt::Display for ContentType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

impl AsRef<str> for ContentType {
    fn as_ref(&self) -> &str {
        self.as_str()
    }
}

/// Difficulty levels for code examples
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum DifficultyLevel {
    Beginner,
    Intermediate,
    Advanced,
}

/// Types of project changes
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ChangeType {
    Created,
    Modified,
    Deleted,
    Moved,
    Renamed,
}

/// Impact levels for changes
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ImpactLevel {
    High,
    Medium,
    Low,
}

/// Sources that can contribute to context
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ContextSource {
    ProjectIndex,
    RagSearch,
    GodotDocs,
    Context7,
    BundledDocs,
    ToolReferences,
    UserInput,
}

impl UnifiedProjectContext {
    /// Create a new unified context from a comprehensive context
    pub fn from_comprehensive(
        comprehensive: ComprehensiveContext,
        project_index: ProjectIndex,
    ) -> Self {
        let mut vector_search_results = Vec::new();
        let mut documentation = DocumentationCache {
            godot_docs: comprehensive.godot_docs.clone(),
            context7_docs: None,
            tool_references: String::new(),
            best_practices: None,
            code_examples: Vec::new(),
        };

        // Extract tool references from the formatted context
        if comprehensive.project_context.contains("# Godoty Command Executor") {
            if let Some(tool_start) = comprehensive.project_context.find("# Godoty Command Executor") {
                documentation.tool_references = comprehensive.project_context[tool_start..].to_string();
            }
        }

        // Parse RAG results if available in the project context
        Self::parse_rag_results(&comprehensive.project_context, &mut vector_search_results);

        let total_tokens = Self::estimate_tokens(&comprehensive);

        Self {
            structured_index: project_index,
            vector_search_results: if vector_search_results.is_empty() {
                None
            } else {
                Some(vector_search_results.clone())
            },
            documentation,
            recent_changes: Vec::new(), // TODO: Implement change tracking
            metadata: ContextMetadata {
                built_at: chrono::Utc::now(),
                total_tokens,
                completeness_score: Self::calculate_completeness(&comprehensive),
                original_query: comprehensive.context_query.clone(),
                sources_used: Self::identify_sources(&comprehensive),
                quality_indicators: QualityIndicators {
                    project_index_complete: true, // TODO: Add proper checking
                    rag_search_successful: vector_search_results.len() > 0,
                    documentation_available: !comprehensive.godot_docs.is_empty(),
                },
                build_errors: Vec::new(),
                warnings: Vec::new(),
            },
        }
    }

    /// Parse RAG results from project context text
    fn parse_rag_results(project_context: &str, results: &mut Vec<RagResult>) {
        if let Some(rag_start) = project_context.find("# Project Vector Index (RAG) Results") {
            let rag_section = &project_context[rag_start..];
            for line in rag_section.lines() {
                if line.starts_with('-') && line.contains(':') {
                    // Parse lines like "- 0.876 player.gd: func move_player(): ..."
                    if let Some(score_end) = line.find(' ') {
                        let score_str = &line[2..score_end];
                        if let Ok(score) = score_str.parse::<f64>() {
                            if let Some(source_end) = line[score_end + 1..].find(' ') {
                                let source = &line[score_end + 1..score_end + 1 + source_end];
                                if let Some(content_start) = line.find(':') {
                                    let content = &line[content_start + 2..];
                                    results.push(RagResult {
                                        relevance_score: score,
                                        source_path: source.to_string(),
                                        content_snippet: content.trim().to_string(),
                                        content_type: ContentType::Script, // TODO: Better type detection
                                        line_range: None,
                                        metadata: HashMap::new(),
                                    });
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    /// Estimate total tokens in context
    fn estimate_tokens(context: &ComprehensiveContext) -> usize {
        let total_chars = context.godot_docs.len()
            + context.project_context.len()
            + context.chat_history.len()
            + context.context_query.len()
            + context.visual_analysis.as_ref().map(|s| s.len()).unwrap_or(0);

        // Rough estimation: ~4 characters per token
        total_chars / 4
    }

    /// Calculate context completeness score
    fn calculate_completeness(context: &ComprehensiveContext) -> f64 {
        let mut score = 0.0;
        let mut factors = 0;

        // Godot docs availability
        if !context.godot_docs.is_empty() {
            score += 0.3;
        }
        factors += 1;

        // Project context availability
        if !context.project_context.is_empty() {
            score += 0.3;
        }
        factors += 1;

        // Context query quality
        if !context.context_query.is_empty() && context.context_query.len() > 10 {
            score += 0.2;
        }
        factors += 1;

        // Visual analysis if available
        if context.visual_analysis.is_some() {
            score += 0.1;
        }
        factors += 1;

        // Chat history for context
        if !context.chat_history.is_empty() {
            score += 0.1;
        }
        factors += 1;

        if factors == 0 {
            0.0
        } else {
            score
        }
    }

    /// Identify which sources contributed to context
    fn identify_sources(context: &ComprehensiveContext) -> Vec<ContextSource> {
        let mut sources = Vec::new();

        if !context.godot_docs.is_empty() {
            sources.push(ContextSource::GodotDocs);
        }

        if !context.project_context.is_empty() {
            sources.push(ContextSource::ProjectIndex);

            // Check for RAG content
            if context.project_context.contains("Project Vector Index (RAG)") {
                sources.push(ContextSource::RagSearch);
            }

            // Check for tool references
            if context.project_context.contains("Godoty Command Executor") {
                sources.push(ContextSource::ToolReferences);
            }
        }

        if !context.context_query.is_empty() {
            sources.push(ContextSource::UserInput);
        }

        sources
    }

    /// Get a summary of the context for logging/debugging
    pub fn get_summary(&self) -> String {
        format!(
            "UnifiedContext: {} scenes, {} scripts, {} resources | RAG: {} results | Docs: {} chars | Tokens: {}",
            self.structured_index.scenes.len(),
            self.structured_index.scripts.len(),
            self.structured_index.resources.len(),
            self.vector_search_results.as_ref().map(|r| r.len()).unwrap_or(0),
            self.documentation.godot_docs.len(),
            self.metadata.total_tokens
        )
    }

    /// Check if context has sufficient information for research planning
    pub fn is_sufficient_for_research(&self) -> bool {
        self.metadata.completeness_score > 0.5
            && !self.structured_index.scenes.is_empty()
            && !self.documentation.godot_docs.is_empty()
    }

    /// Check if context has sufficient information for execution planning
    pub fn is_sufficient_for_execution(&self) -> bool {
        self.metadata.completeness_score > 0.7
            && !self.documentation.tool_references.is_empty()
    }

    /// Get relevant sections based on agent type needs
    pub fn get_relevant_sections(&self, agent_type: AgentContextType) -> String {
        match agent_type {
            AgentContextType::Research => {
                format!(
                    "# Project Structure\n{}\n\n# Documentation\n{}\n\n# Relevant Code Snippets\n{}",
                    self.format_project_summary(),
                    self.documentation.godot_docs.chars().take(2000).collect::<String>(),
                    self.format_rag_results()
                )
            }
            AgentContextType::Orchestrator => {
                format!(
                    "# Project Overview\n{}\n\n# Tool References\n{}\n\n# Execution Context\n{}",
                    self.format_project_summary(),
                    self.documentation.tool_references,
                    self.format_execution_context()
                )
            }
        }
    }

    fn format_project_summary(&self) -> String {
        format!(
            "Scenes: {}, Scripts: {}, Resources: {}",
            self.structured_index.scenes.len(),
            self.structured_index.scripts.len(),
            self.structured_index.resources.len()
        )
    }

    fn format_rag_results(&self) -> String {
        if let Some(results) = &self.vector_search_results {
            results
                .iter()
                .take(10)
                .map(|r| format!("- {:.3} {} ({}): {}", r.relevance_score, r.source_path, r.content_type.as_ref(), r.content_snippet.chars().take(100).collect::<String>()))
                .collect::<Vec<_>>()
                .join("\n")
        } else {
            "No RAG results available".to_string()
        }
    }

    fn format_execution_context(&self) -> String {
        format!(
            "Project path: {}\nContext built at: {}\nCompleteness: {:.1}%",
            self.structured_index.project_path,
            self.metadata.built_at.format("%Y-%m-%d %H:%M:%S UTC"),
            self.metadata.completeness_score * 100.0
        )
    }
}

/// Types of agent context needs
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AgentContextType {
    Research,
    Orchestrator,
}