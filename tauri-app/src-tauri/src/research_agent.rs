use crate::unified_context::{UnifiedProjectContext, AgentContextType};
use crate::context_manager::{ContextManager, ContextRequirements};
use crate::llm_client::LlmFactory;
use crate::llm_config::AgentType;
use crate::tool_registry::ToolRegistry;
use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::sync::Arc;
use chrono::{DateTime, Utc};

/// Redesigned Research Agent focused on structured plan creation
pub struct ResearchAgent {
    /// API key for LLM access
    api_key: String,

    /// LLM factory for creating clients
    llm_factory: Option<LlmFactory>,

    /// Context manager for unified project context
    context_manager: Arc<ContextManager>,

    /// Tool registry for accessing research tools
    tool_registry: Arc<ToolRegistry>,

    /// Research agent configuration
    config: ResearchAgentConfig,
}

/// Configuration for research agent behavior
#[derive(Debug, Clone)]
pub struct ResearchAgentConfig {
    /// Maximum planning iterations
    pub max_planning_iterations: usize,

    /// Whether to use sequential thinking for complex research
    pub enable_sequential_thinking: bool,

    /// Maximum research depth (how many levels of detail to explore)
    pub max_research_depth: usize,

    /// Whether to validate plans against project constraints
    pub enable_plan_validation: bool,

    /// Research timeout in seconds
    pub research_timeout_seconds: u64,
}

impl Default for ResearchAgentConfig {
    fn default() -> Self {
        Self {
            max_planning_iterations: 3,
            enable_sequential_thinking: true,
            max_research_depth: 3,
            enable_plan_validation: true,
            research_timeout_seconds: 120,
        }
    }
}

/// Input for research phase
#[derive(Debug, Clone)]
pub struct ResearchInput {
    /// User's original request
    pub user_input: String,

    /// Unified project context
    pub project_context: UnifiedProjectContext,

    /// Previous research results (for iterative refinement)
    pub previous_research: Option<ResearchResult>,

    /// Research constraints and requirements
    pub constraints: ResearchConstraints,
}

/// Constraints for research planning
#[derive(Debug, Clone)]
pub struct ResearchConstraints {
    /// Maximum complexity allowed
    pub max_complexity: ComplexityLevel,

    /// Focus areas for research
    pub focus_areas: Vec<String>,

    /// Exclusion criteria
    pub exclusions: Vec<String>,

    /// Time constraints
    pub time_limit_seconds: Option<u64>,

    /// Resource constraints (file operations, network calls, etc.)
    pub resource_limits: ResourceLimits,
}

/// Resource usage limits for research
#[derive(Debug, Clone)]
pub struct ResourceLimits {
    /// Maximum number of files to analyze
    pub max_files_to_analyze: usize,

    /// Maximum documentation topics to research
    pub max_documentation_topics: usize,

    /// Maximum RAG queries to perform
    pub max_rag_queries: usize,
}

/// Complexity levels for plans
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ComplexityLevel {
    Simple,    // Single step, minimal changes
    Medium,    // Multiple steps, moderate complexity
    Complex,   // Many steps, high complexity
    Critical,  // System-critical changes requiring careful planning
}

/// Result of research phase
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResearchResult {
    /// Research identifier
    pub research_id: String,

    /// When research was completed
    pub timestamp: DateTime<Utc>,

    /// Research findings and analysis
    pub findings: Vec<ResearchFinding>,

    /// Generated execution plan
    pub execution_plan: Option<ExecutionPlan>,

    /// Recommended approaches
    pub recommended_approaches: Vec<RecommendedApproach>,

    /// Identified risks and mitigations
    pub risks_and_mitigations: Vec<RiskMitigation>,

    /// Research metadata
    pub metadata: ResearchMetadata,
}

/// Individual research finding
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResearchFinding {
    /// Finding category
    pub category: FindingCategory,

    /// Finding description
    pub description: String,

    /// Supporting evidence
    pub evidence: Vec<Evidence>,

    /// Confidence level (0.0-1.0)
    pub confidence: f32,

    /// Relevance to user request (0.0-1.0)
    pub relevance: f32,
}

/// Categories of research findings
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FindingCategory {
    ProjectStructure,
    ExistingImplementation,
    Documentation,
    BestPractices,
    PotentialIssues,
    Dependencies,
    Performance,
}

/// Evidence supporting a finding
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Evidence {
    /// Source of evidence
    pub source: EvidenceSource,

    /// Content snippet
    pub content: String,

    /// Source file or reference
    pub reference: String,

    /// Confidence in this evidence
    pub confidence: f32,
}

/// Sources of evidence
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EvidenceSource {
    ProjectFile,
    Documentation,
    RagResult,
    ToolOutput,
    DomainKnowledge,
}

/// Enhanced execution plan for orchestrator
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionPlan {
    /// Plan identifier
    pub plan_id: String,

    /// Plan metadata
    pub metadata: PlanMetadata,

    /// Pre-conditions that must be met
    pub preconditions: Vec<Precondition>,

    /// Execution steps
    pub steps: Vec<PlanStep>,

    /// Post-conditions for validation
    pub post_conditions: Vec<PostCondition>,

    /// Fallback strategies
    pub fallback_strategies: Vec<FallbackStrategy>,
}

/// Plan metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanMetadata {
    /// Plan title
    pub title: String,

    /// Plan description
    pub description: String,

    /// Estimated complexity
    pub complexity: ComplexityLevel,

    /// Estimated time to complete
    pub estimated_time_minutes: u32,

    /// Required tools
    pub required_tools: Vec<String>,

    /// Risk assessment
    pub risk_level: RiskLevel,
}

/// Risk levels
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum RiskLevel {
    Low,
    Medium,
    High,
    Critical,
}

/// Execution preconditions
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Precondition {
    /// Condition description
    pub description: String,

    /// How to verify the condition
    pub verification_method: String,

    /// Whether condition is mandatory
    pub mandatory: bool,
}

/// Enhanced plan step
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanStep {
    /// Step identifier
    pub step_id: String,

    /// Step number for ordering
    pub step_number: usize,

    /// Step description
    pub description: String,

    /// Detailed explanation
    pub explanation: String,

    /// Tools required for this step
    pub required_tools: Vec<String>,

    /// Expected outcome
    pub expected_outcome: String,

    /// Success criteria
    pub success_criteria: Vec<String>,

    /// Dependencies on other steps
    pub dependencies: Vec<String>,

    /// Error recovery strategies
    pub error_recovery: Vec<String>,

    /// Estimated time for this step
    pub estimated_time_minutes: u32,

    /// Safety considerations
    pub safety_considerations: Vec<String>,
}

/// Post-conditions for plan validation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PostCondition {
    /// Condition description
    pub description: String,

    /// How to verify the condition
    pub verification_method: String,

    /// Success criteria
    pub success_criteria: Vec<String>,
}

/// Fallback strategy for plan execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FallbackStrategy {
    /// Strategy name
    pub name: String,

    /// When to use this strategy
    pub trigger_conditions: Vec<String>,

    /// Alternative steps
    pub alternative_steps: Vec<PlanStep>,

    /// Expected success rate
    pub expected_success_rate: f32,
}

/// Recommended approach
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RecommendedApproach {
    /// Approach name
    pub name: String,

    /// Approach description
    pub description: String,

    /// Pros of this approach
    pub pros: Vec<String>,

    /// Cons of this approach
    pub cons: Vec<String>,

    /// When to use this approach
    pub best_for: Vec<String>,

    /// Confidence level
    pub confidence: f32,
}

/// Risk and mitigation strategy
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RiskMitigation {
    /// Risk description
    pub risk: String,

    /// Risk probability (0.0-1.0)
    pub probability: f32,

    /// Risk impact level
    pub impact: RiskLevel,

    /// Mitigation strategies
    pub mitigations: Vec<String>,

    /// Contingency plans
    pub contingency_plans: Vec<String>,
}

/// Research metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResearchMetadata {
    /// Research duration in seconds
    pub research_duration_seconds: u64,

    /// Number of sources consulted
    pub sources_consulted: usize,

    /// Tools used during research
    pub tools_used: Vec<String>,

    /// Iterations performed
    pub iterations_performed: usize,

    /// Confidence in overall research
    pub overall_confidence: f32,
}

impl ResearchAgent {
    /// Create a new research agent
    pub fn new(api_key: &str, context_manager: Arc<ContextManager>, tool_registry: Arc<ToolRegistry>) -> Self {
        Self {
            api_key: api_key.to_string(),
            llm_factory: None,
            context_manager,
            tool_registry,
            config: ResearchAgentConfig::default(),
        }
    }

    /// Create research agent with custom configuration
    pub fn with_config(
        api_key: &str,
        context_manager: Arc<ContextManager>,
        tool_registry: Arc<ToolRegistry>,
        config: ResearchAgentConfig,
    ) -> Self {
        Self {
            api_key: api_key.to_string(),
            llm_factory: None,
            context_manager,
            tool_registry,
            config,
        }
    }

    /// Set LLM factory for this agent
    pub fn with_llm_factory(mut self, llm_factory: Option<LlmFactory>) -> Self {
        self.llm_factory = llm_factory;
        self
    }

    /// Main entry point: create execution plan from research
    pub async fn create_execution_plan(&self, input: ResearchInput) -> Result<ResearchResult> {
        let research_id = uuid::Uuid::new_v4().to_string();
        let start_time = Utc::now();

        tracing::info!(
            research_id = %research_id,
            user_input_preview = %input.user_input.chars().take(100).collect::<String>(),
            "Starting structured research"
        );

        // Phase 1: Analyze request and context
        let analysis = self.analyze_request_and_context(&input).await?;

        // Phase 2: Conduct research based on analysis
        let findings = self.conduct_research(&input, &analysis).await?;

        // Phase 3: Generate execution plan from findings
        let execution_plan = self.generate_execution_plan(&input, &findings).await?;

        // Phase 4: Identify risks and mitigations
        let risks_and_mitigations = self.identify_risks_and_mitigations(&input, &findings, &execution_plan).await?;

        // Phase 5: Recommend alternative approaches
        let recommended_approaches = self.recommend_approaches(&input, &findings, &execution_plan).await?;

        let end_time = Utc::now();
        let research_duration = end_time.signed_duration_since(start_time);

        Ok(ResearchResult {
            research_id,
            timestamp: end_time,
            findings,
            execution_plan: Some(execution_plan),
            recommended_approaches,
            risks_and_mitigations,
            metadata: ResearchMetadata {
                research_duration_seconds: research_duration.num_seconds() as u64,
                sources_consulted: 0, // TODO: Track actual sources
                tools_used: vec![], // TODO: Track tools used
                iterations_performed: 1, // TODO: Track iterations
                overall_confidence: 0.8, // TODO: Calculate from findings
            },
        })
    }

    /// Analyze the user request and project context
    async fn analyze_request_and_context(&self, input: &ResearchInput) -> Result<RequestAnalysis> {
        // Use LLM to analyze request complexity and requirements
        let llm_client = self.llm_factory.as_ref()
            .ok_or_else(|| anyhow::anyhow!("LLM factory not configured for research agent"))?
            .create_client_for_agent(AgentType::Planning)?;

        let context_summary = input.project_context.get_summary();
        let context_relevant = input.project_context.get_relevant_sections(AgentContextType::Research);

        let system_prompt = r#"You are a research analysis AI for a Godot game development assistant.
Analyze the user's request and the project context to determine:

1. Request complexity (Simple/Medium/Complex/Critical)
2. Required research areas
3. Potential dependencies and constraints
4. Key files and components that need to be analyzed

Focus on understanding what needs to be researched to create a solid execution plan."#;

        let user_prompt = format!(
            r#"User Request: {}
Project Context: {}

Please analyze this request and provide a structured analysis in JSON format:
{{
  "complexity": "simple|medium|complex|critical",
  "research_areas": ["area1", "area2", ...],
  "key_components": ["component1", "component2", ...],
  "dependencies": ["dep1", "dep2", ...],
  "constraints": ["constraint1", "constraint2", ...],
  "estimated_steps": number,
  "reasoning": "detailed explanation of the analysis"
}}"#,
            input.user_input,
            context_relevant
        );

        let response = llm_client.generate_response(system_prompt, &user_prompt).await?;

        // Parse the JSON response
        let analysis: RequestAnalysis = serde_json::from_str(&response)
            .map_err(|e| anyhow::anyhow!("Failed to parse research analysis: {}", e))?;

        Ok(analysis)
    }

    /// Conduct research based on analysis
    async fn conduct_research(&self, input: &ResearchInput, analysis: &RequestAnalysis) -> Result<Vec<ResearchFinding>> {
        let mut findings = Vec::new();

        // Research project structure
        if analysis.key_components.iter().any(|c| c.contains("scene") || c.contains("node")) {
            let structure_findings = self.research_project_structure(&input.project_context).await?;
            findings.extend(structure_findings);
        }

        // Research existing implementations
        if analysis.key_components.iter().any(|c| c.contains("script") || c.contains("code")) {
            let implementation_findings = self.research_existing_implementations(&input.project_context).await?;
            findings.extend(implementation_findings);
        }

        // Research documentation
        if analysis.research_areas.iter().any(|a| a.contains("documentation") || a.contains("learning")) {
            let doc_findings = self.research_documentation(&input, &analysis.research_areas).await?;
            findings.extend(doc_findings);
        }

        // Research best practices
        let best_practice_findings = self.research_best_practices(&input, &analysis).await?;
        findings.extend(best_practice_findings);

        // Research potential issues
        let issue_findings = self.research_potential_issues(&input, &analysis).await?;
        findings.extend(issue_findings);

        Ok(findings)
    }

    /// Generate execution plan from research findings
    async fn generate_execution_plan(&self, input: &ResearchInput, findings: &[ResearchFinding]) -> Result<ExecutionPlan> {
        let llm_client = self.llm_factory.as_ref()
            .ok_or_else(|| anyhow::anyhow!("LLM factory not configured for research agent"))?
            .create_client_for_agent(AgentType::Planning)?;

        // Prepare findings summary
        let findings_summary = findings
            .iter()
            .map(|f| format!("{}: {}", f.category.as_str(), f.description))
            .collect::<Vec<_>>()
            .join("\n");

        let system_prompt = r#"You are a planning AI for Godot game development. Based on research findings, create a detailed execution plan that an orchestrator agent can follow.

The plan should include:
1. Clear, sequential steps
2. Required tools for each step
3. Success criteria
4. Error handling strategies
5. Safety considerations

Format the response as JSON according to the ExecutionPlan schema."#;

        let user_prompt = format!(
            r#"User Request: {}
Research Findings:
{}

Create a comprehensive execution plan in JSON format that addresses all findings and constraints.
Focus on creating steps that can be executed by an orchestrator agent with access to Godot editor commands and file operations."#,
            input.user_input,
            findings_summary
        );

        let response = llm_client.generate_response(system_prompt, &user_prompt).await?;

        // Parse and enhance the plan
        let mut plan: ExecutionPlan = serde_json::from_str(&response)
            .map_err(|e| anyhow::anyhow!("Failed to parse execution plan: {}", e))?;

        // Enhance plan with additional metadata
        plan.metadata = PlanMetadata {
            title: format!("Plan for: {}", input.user_input.chars().take(50).collect::<String>()),
            description: format!("Generated plan with {} steps based on research findings", plan.steps.len()),
            complexity: self.determine_plan_complexity(&plan),
            estimated_time_minutes: self.estimate_plan_time(&plan),
            required_tools: self.extract_required_tools(&plan),
            risk_level: self.assess_plan_risk(&plan, findings),
        };

        Ok(plan)
    }

    // Helper methods for research phases
    async fn research_project_structure(&self, context: &UnifiedProjectContext) -> Result<Vec<ResearchFinding>> {
        let mut findings = Vec::new();

        // Analyze project structure from context
        if !context.structured_index.scenes.is_empty() {
            findings.push(ResearchFinding {
                category: FindingCategory::ProjectStructure,
                description: format!(
                    "Project contains {} scenes with root types ranging from {} to {}",
                    context.structured_index.scenes.len(),
                    context.structured_index.scenes.iter()
                        .filter_map(|s| s.root_type.as_ref())
                        .min()
                        .unwrap_or(&"Unknown".to_string()),
                    context.structured_index.scenes.iter()
                        .filter_map(|s| s.root_type.as_ref())
                        .max()
                        .unwrap_or(&"Unknown".to_string())
                ),
                evidence: vec![],
                confidence: 1.0,
                relevance: 0.8,
            });
        }

        if !context.structured_index.scripts.is_empty() {
            findings.push(ResearchFinding {
                category: FindingCategory::ProjectStructure,
                description: format!(
                    "Project contains {} GDScript files with various class implementations",
                    context.structured_index.scripts.len()
                ),
                evidence: vec![],
                confidence: 1.0,
                relevance: 0.7,
            });
        }

        Ok(findings)
    }

    async fn research_existing_implementations(&self, context: &UnifiedProjectContext) -> Result<Vec<ResearchFinding>> {
        let mut findings = Vec::new();

        // Analyze existing scripts and patterns
        for script in &context.structured_index.scripts {
            if !script.classes.is_empty() {
                findings.push(ResearchFinding {
                    category: FindingCategory::ExistingImplementation,
                    description: format!(
                        "Script '{}' implements {} classes: {}",
                        script.name,
                        script.classes.len(),
                        script.classes.join(", ")
                    ),
                    evidence: vec![],
                    confidence: 0.9,
                    relevance: 0.6,
                });
            }
        }

        Ok(findings)
    }

    async fn research_documentation(&self, input: &ResearchInput, research_areas: &[String]) -> Result<Vec<ResearchFinding>> {
        let mut findings = Vec::new();

        // Check what documentation is available
        if !input.project_context.documentation.godot_docs.is_empty() {
            findings.push(ResearchFinding {
                category: FindingCategory::Documentation,
                description: "Comprehensive Godot documentation available for reference".to_string(),
                evidence: vec![],
                confidence: 0.8,
                relevance: 0.7,
            });
        }

        Ok(findings)
    }

    async fn research_best_practices(&self, input: &ResearchInput, analysis: &RequestAnalysis) -> Result<Vec<ResearchFinding>> {
        let mut findings = Vec::new();

        // Add best practices based on complexity
        if matches!(analysis.complexity, ComplexityLevel::Complex | ComplexityLevel::Critical) {
            findings.push(ResearchFinding {
                category: FindingCategory::BestPractices,
                description: "Complex implementation requires careful testing and incremental development".to_string(),
                evidence: vec![],
                confidence: 0.9,
                relevance: 0.8,
            });
        }

        Ok(findings)
    }

    async fn research_potential_issues(&self, input: &ResearchInput, analysis: &RequestAnalysis) -> Result<Vec<ResearchFinding>> {
        let mut findings = Vec::new();

        // Identify potential issues based on complexity and dependencies
        if !analysis.dependencies.is_empty() {
            findings.push(ResearchFinding {
                category: FindingCategory::PotentialIssues,
                description: format!(
                    "Implementation has {} dependencies that must be carefully managed",
                    analysis.dependencies.len()
                ),
                evidence: vec![],
                confidence: 0.7,
                relevance: 0.8,
            });
        }

        Ok(findings)
    }

    async fn identify_risks_and_mitigations(&self, input: &ResearchInput, findings: &[ResearchFinding], plan: &ExecutionPlan) -> Result<Vec<RiskMitigation>> {
        // TODO: Implement risk identification logic
        Ok(vec![])
    }

    async fn recommend_approaches(&self, input: &ResearchInput, findings: &[ResearchFinding], plan: &ExecutionPlan) -> Result<Vec<RecommendedApproach>> {
        // TODO: Implement approach recommendation logic
        Ok(vec![])
    }

    // Helper methods for plan enhancement
    fn determine_plan_complexity(&self, plan: &ExecutionPlan) -> ComplexityLevel {
        match plan.steps.len() {
            1..=3 => ComplexityLevel::Simple,
            4..=7 => ComplexityLevel::Medium,
            8..=12 => ComplexityLevel::Complex,
            _ => ComplexityLevel::Critical,
        }
    }

    fn estimate_plan_time(&self, plan: &ExecutionPlan) -> u32 {
        plan.steps.iter().map(|s| s.estimated_time_minutes).sum()
    }

    fn extract_required_tools(&self, plan: &ExecutionPlan) -> Vec<String> {
        let mut tools = Vec::new();
        for step in &plan.steps {
            for tool in &step.required_tools {
                if !tools.contains(tool) {
                    tools.push(tool.clone());
                }
            }
        }
        tools
    }

    fn assess_plan_risk(&self, plan: &ExecutionPlan, findings: &[ResearchFinding]) -> RiskLevel {
        // TODO: Implement risk assessment logic
        RiskLevel::Medium
    }
}

/// Request analysis result
#[derive(Debug, Clone, Deserialize)]
struct RequestAnalysis {
    complexity: ComplexityLevel,
    research_areas: Vec<String>,
    key_components: Vec<String>,
    dependencies: Vec<String>,
    constraints: Vec<String>,
    estimated_steps: usize,
    reasoning: String,
}

impl FindingCategory {
    fn as_str(&self) -> &'static str {
        match self {
            FindingCategory::ProjectStructure => "Project Structure",
            FindingCategory::ExistingImplementation => "Existing Implementation",
            FindingCategory::Documentation => "Documentation",
            FindingCategory::BestPractices => "Best Practices",
            FindingCategory::PotentialIssues => "Potential Issues",
            FindingCategory::Dependencies => "Dependencies",
            FindingCategory::Performance => "Performance",
        }
    }
}