use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use reqwest::Client;
use crate::knowledge_base::KnowledgeBase;
use crate::agent::ExecutionPlan;

/// Base trait for all specialized agents
#[async_trait::async_trait]
pub trait StrandsAgent: Send + Sync {
    async fn execute(&self, context: &AgentExecutionContext) -> Result<AgentOutput>;
    fn get_name(&self) -> &str;
    fn get_model(&self) -> &str;
}

/// Context passed to agents during execution
#[derive(Clone)]
pub struct AgentExecutionContext {
    pub user_input: String,
    pub chat_history: String,
    pub project_context: String,
    pub plugin_kb: KnowledgeBase,
    pub docs_kb: KnowledgeBase,
    pub execution_plan: Option<ExecutionPlan>,
    pub previous_output: Option<String>,
}

/// Output from agent execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentOutput {
    pub content: String,
    pub tokens_used: u32,
    pub execution_time_ms: u64,
    pub metadata: serde_json::Map<String, Value>,
}

/// Planning Agent - Breaks down user requests into actionable tasks
pub struct PlanningAgent {
    api_key: String,
    client: Client,
    model: String,
}

impl PlanningAgent {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
            model: "minimax/minimax-m2:free".to_string(),
        }
    }
}

#[async_trait::async_trait]
impl StrandsAgent for PlanningAgent {
    async fn execute(&self, context: &AgentExecutionContext) -> Result<AgentOutput> {
        let start_time = std::time::Instant::now();

        // Query knowledge bases for context
        let plugin_docs = context.plugin_kb.search(&context.user_input, 5).await?;
        let godot_docs = context.docs_kb.search(&context.user_input, 5).await?;

        let plugin_context = plugin_docs.iter()
            .map(|d| format!("- {}: {}", d.id, d.content))
            .collect::<Vec<_>>()
            .join("\n");

        let docs_context = godot_docs.iter()
            .map(|d| format!("- {}", d.content.chars().take(200).collect::<String>()))
            .collect::<Vec<_>>()
            .join("\n");

        let system_prompt = format!(r#"You are an AI planning agent for Godot game development.
Your task is to analyze the user's request and create a detailed execution plan.

Available Plugin Commands:
{}

Relevant Godot Documentation:
{}

Project Context:
{}

Create a step-by-step plan to accomplish the user's goal.
Respond with a JSON object containing:
{{
  "reasoning": "Your analysis of the task",
  "steps": [
    {{"step_number": 1, "description": "What to do", "commands_needed": ["command_type1", "command_type2"]}},
    ...
  ],
  "estimated_complexity": "low|medium|high"
}}

STRICT OUTPUT RULES:
- Respond ONLY with a valid JSON object (no prose before/after).
- If you use a code fence, use ```json and include only valid JSON inside.
- No comments, no trailing commas, no ellipses inside JSON.
- Ensure all braces/brackets are closed; keep to <= 8 steps.

"#,
            plugin_context,
            docs_context,
            context.project_context
        );

        let response = call_llm(
            &self.client,
            &self.api_key,
            &self.model,
            &system_prompt,
            &context.user_input,
        ).await?;

        let execution_time_ms = start_time.elapsed().as_millis() as u64;

        // Estimate tokens (rough approximation: 1 token ≈ 4 characters)
        let tokens_used = ((system_prompt.len() + context.user_input.len() + response.len()) / 4) as u32;

        let mut metadata = serde_json::Map::new();
        metadata.insert("plugin_docs_retrieved".to_string(), Value::Number(plugin_docs.len().into()));
        metadata.insert("godot_docs_retrieved".to_string(), Value::Number(godot_docs.len().into()));

        Ok(AgentOutput {
            content: response,
            tokens_used,
            execution_time_ms,
            metadata,
        })
    }

    fn get_name(&self) -> &str {
        "PlanningAgent"
    }

    fn get_model(&self) -> &str {
        &self.model
    }
}

/// Code Generation Agent - Generates GDScript code and Godot commands
pub struct CodeGenerationAgent {
    api_key: String,
    client: Client,
    model: String,
}

impl CodeGenerationAgent {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
            model: "qwen/qwen3-coder:free".to_string(),
        }
    }
}

#[async_trait::async_trait]
impl StrandsAgent for CodeGenerationAgent {
    async fn execute(&self, context: &AgentExecutionContext) -> Result<AgentOutput> {
        let start_time = std::time::Instant::now();

        let plan = context.execution_plan.as_ref()
            .ok_or_else(|| anyhow::anyhow!("Execution plan required for code generation"))?;

        // Get plugin examples
        let plugin_docs = context.plugin_kb.search(&context.user_input, 5).await?;
        let plugin_examples = plugin_docs.iter()
            .map(|d| d.content.clone())
            .collect::<Vec<_>>()
            .join("\n\n");

        let system_prompt = format!(r#"You are a command generation agent for Godot.

Execution Plan:
{}

Plugin Command Examples:
{}

Generate a JSON array of commands to execute the plan.
Each command must be a valid JSON object matching the plugin's command schema.
Respond ONLY with the JSON array, no explanations.
"#,
            serde_json::to_string_pretty(plan)?,
            plugin_examples
        );

        let response = call_llm(
            &self.client,
            &self.api_key,
            &self.model,
            &system_prompt,
            &context.user_input,
        ).await?;

        let execution_time_ms = start_time.elapsed().as_millis() as u64;
        let tokens_used = ((system_prompt.len() + context.user_input.len() + response.len()) / 4) as u32;

        Ok(AgentOutput {
            content: response,
            tokens_used,
            execution_time_ms,
            metadata: serde_json::Map::new(),
        })
    }

    fn get_name(&self) -> &str {
        "CodeGenerationAgent"
    }

    fn get_model(&self) -> &str {
        &self.model
    }
}

/// Validation Agent - Validates generated commands against Plugin Tools & API
pub struct ValidationAgent {
    api_key: String,
    client: Client,
    model: String,
}

impl ValidationAgent {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
            model: "minimax/minimax-m2:free".to_string(),
        }
    }
}

#[async_trait::async_trait]
impl StrandsAgent for ValidationAgent {
    async fn execute(&self, context: &AgentExecutionContext) -> Result<AgentOutput> {
        let start_time = std::time::Instant::now();

        // Get all plugin documentation for validation
        let all_plugin_docs = context.plugin_kb.get_all_documents().await;
        let plugin_schema = all_plugin_docs.iter()
            .map(|d| d.content.clone())
            .collect::<Vec<_>>()
            .join("\n\n");

        let commands_to_validate = context.previous_output.as_ref()
            .ok_or_else(|| anyhow::anyhow!("No commands to validate"))?;

        let system_prompt = format!(r#"You are a validation agent for Godot commands.

Plugin Command Schema and Examples:
{}

Your task is to validate the following commands against the schema.
Check for:
1. Valid command types
2. Required fields present
3. Correct data types
4. No hallucinated API calls

Respond with a JSON object:
{{
  "valid": true/false,
  "errors": ["error1", "error2", ...],
  "warnings": ["warning1", "warning2", ...],
  "validated_commands": [/* corrected commands if needed */]
}}
"#,
            plugin_schema
        );

        let response = call_llm(
            &self.client,
            &self.api_key,
            &self.model,
            &system_prompt,
            commands_to_validate,
        ).await?;

        let execution_time_ms = start_time.elapsed().as_millis() as u64;
        let tokens_used = ((system_prompt.len() + commands_to_validate.len() + response.len()) / 4) as u32;

        Ok(AgentOutput {
            content: response,
            tokens_used,
            execution_time_ms,
            metadata: serde_json::Map::new(),
        })
    }

    fn get_name(&self) -> &str {
        "ValidationAgent"
    }

    fn get_model(&self) -> &str {
        &self.model
    }
}

/// GDScript Generation Agent - Generates contextually appropriate GDScript code
/// using a multi-source approach: online references, official docs, and project analysis
pub struct GDScriptAgent {
    api_key: String,
    client: Client,
    model: String,
}

#[derive(Debug)]
struct ProjectStyleAnalysis {
    indentation: String,
    naming_convention: String,
    comment_style: String,
    signal_patterns: Vec<String>,
    export_patterns: Vec<String>,
    common_functions: Vec<String>,
    godot_version: String,
    file_organization: String,
}

impl GDScriptAgent {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
            model: "qwen/qwen3-coder:free".to_string(),
        }
    }

    /// Fetch online GDScript examples and best practices
    async fn fetch_online_references(&self, query: &str, node_type: Option<&str>) -> Result<String> {
        let search_query = if let Some(nt) = node_type {
            format!("Godot 4 GDScript {} {} examples best practices", nt, query)
        } else {
            format!("Godot 4 GDScript {} examples best practices", query)
        };

        // Use web search to find current best practices
        // Note: This would integrate with the web-search tool
        // For now, we'll construct a focused query for the LLM
        let online_context = format!(
            "Search Query: {}\nNote: Look for modern Godot 4.x patterns and community best practices",
            search_query
        );

        Ok(online_context)
    }

    /// Query official Godot documentation for node type and GDScript features
    async fn fetch_official_docs(&self, node_type: Option<&str>, docs_kb: &crate::knowledge_base::KnowledgeBase) -> Result<String> {
        let query = if let Some(nt) = node_type {
            format!("{} node API methods signals properties GDScript", nt)
        } else {
            String::from("GDScript syntax features built-in methods")
        };

        let docs = docs_kb.search(&query, 5).await?;

        let docs_content = docs.iter()
            .map(|d| format!("## {}\n{}", d.id, d.content))
            .collect::<Vec<_>>()
            .join("\n\n");

        Ok(if docs_content.is_empty() {
            String::from("No specific documentation found. Use Godot 4.x standard practices.")
        } else {
            format!("Official Godot Documentation:\n{}", docs_content)
        })
    }

    /// Comprehensive analysis of existing project scripts
    fn analyze_project_integration(&self, project_context: &str) -> ProjectStyleAnalysis {
        let mut indentation = String::from("\t"); // Default to tabs
        let mut naming_convention = String::from("snake_case");
        let mut comment_style = String::from("# ");
        let mut signal_patterns = Vec::new();
        let mut export_patterns = Vec::new();
        let mut common_functions = Vec::new();
        let mut godot_version = String::from("4.x");
        let mut file_organization = String::from("res://scripts/");

        // Detect indentation style
        let mut tab_count = 0;
        let mut space_count = 0;
        for line in project_context.lines() {
            if line.starts_with('\t') {
                tab_count += 1;
            } else if line.starts_with("    ") {
                space_count += 1;
            }
        }
        if space_count > tab_count {
            indentation = String::from("    ");
        }

        // Extract signal patterns
        for line in project_context.lines() {
            let trimmed = line.trim();
            if trimmed.starts_with("signal ") {
                signal_patterns.push(trimmed.to_string());
            }
            if trimmed.starts_with("@export") {
                export_patterns.push(trimmed.to_string());
            }
            if trimmed.starts_with("func _") {
                if let Some(func_name) = trimmed.split('(').next() {
                    common_functions.push(func_name.to_string());
                }
            }
        }

        // Detect Godot version from syntax
        if project_context.contains("@export") || project_context.contains("@onready") {
            godot_version = String::from("4.x");
        } else if project_context.contains("export var") || project_context.contains("onready var") {
            godot_version = String::from("3.x");
        }

        // Detect file organization patterns
        if project_context.contains("res://scripts/") {
            file_organization = String::from("res://scripts/");
        } else if project_context.contains("res://src/") {
            file_organization = String::from("res://src/");
        }

        ProjectStyleAnalysis {
            indentation,
            naming_convention,
            comment_style,
            signal_patterns,
            export_patterns,
            common_functions,
            godot_version,
            file_organization,
        }
    }

    /// Extract node type from user request or project context
    fn extract_target_node_type(&self, user_input: &str, project_context: &str) -> Option<String> {
        // Common Godot node types
        let node_types = vec![
            "CharacterBody2D", "CharacterBody3D", "Area2D", "Area3D",
            "RigidBody2D", "RigidBody3D", "Sprite2D", "Sprite3D",
            "Node2D", "Node3D", "Control", "CanvasLayer",
            "AnimationPlayer", "Timer", "Camera2D", "Camera3D",
            "StaticBody2D", "StaticBody3D", "CollisionShape2D", "CollisionShape3D",
            "Label", "Button", "TextureRect", "Panel",
        ];

        // Check user input first
        for node_type in &node_types {
            if user_input.contains(node_type) {
                return Some(node_type.to_string());
            }
        }

        // Check project context for node type hints
        for node_type in &node_types {
            if project_context.contains(node_type) {
                return Some(node_type.to_string());
            }
        }

        None
    }
}

#[async_trait::async_trait]
impl StrandsAgent for GDScriptAgent {
    async fn execute(&self, context: &AgentExecutionContext) -> Result<AgentOutput> {
        let start_time = std::time::Instant::now();

        // STEP 1: Extract target node type
        let target_node_type = self.extract_target_node_type(
            &context.user_input,
            &context.project_context
        );

        // STEP 2: Fetch online references and best practices
        let online_refs = self.fetch_online_references(
            &context.user_input,
            target_node_type.as_deref()
        ).await?;

        // STEP 3: Query official Godot documentation
        let official_docs = self.fetch_official_docs(
            target_node_type.as_deref(),
            &context.docs_kb
        ).await?;

        // STEP 4: Analyze project integration requirements
        let project_style = self.analyze_project_integration(&context.project_context);

        // Build comprehensive context from all sources
        let node_type_section = if let Some(ref nt) = target_node_type {
            format!("Target Node Type: {}\n", nt)
        } else {
            String::from("Node type not specified - infer from context\n")
        };

        let style_guide = format!(
            r#"Project Style Guide (MUST FOLLOW):
- Indentation: {}
- Naming Convention: {}
- Comment Style: {}
- Godot Version: {}
- File Organization: {}
- Signal Patterns: {}
- Export Patterns: {}
- Common Lifecycle Methods: {}
"#,
            project_style.indentation,
            project_style.naming_convention,
            project_style.comment_style,
            project_style.godot_version,
            project_style.file_organization,
            if project_style.signal_patterns.is_empty() {
                "No signals found - use standard Godot 4.x syntax"
            } else {
                &project_style.signal_patterns.join(", ")
            },
            if project_style.export_patterns.is_empty() {
                "No exports found - use @export syntax for Godot 4.x"
            } else {
                &project_style.export_patterns.join(", ")
            },
            if project_style.common_functions.is_empty() {
                "_ready, _process, _physics_process"
            } else {
                &project_style.common_functions.join(", ")
            }
        );

        let system_prompt = format!(r#"You are an expert GDScript code generation specialist for Godot.

Your task is to generate high-quality, production-ready GDScript code by synthesizing information from multiple authoritative sources.

{}

=== SOURCE 1: ONLINE REFERENCES & BEST PRACTICES ===
{}

=== SOURCE 2: OFFICIAL GODOT DOCUMENTATION ===
{}

=== SOURCE 3: PROJECT INTEGRATION ANALYSIS ===
{}

Current Project Context:
{}

User Request:
{}

SYNTHESIS GUIDELINES:
1. **Style Consistency**: STRICTLY match the project's existing coding style (indentation, naming, comments)
2. **Best Practices**: Incorporate modern Godot 4.x best practices from online references
3. **API Accuracy**: Use correct node APIs and methods from official documentation
4. **Project Integration**: Ensure the generated code integrates seamlessly with existing scripts
5. **Version Compatibility**: Use syntax appropriate for the detected Godot version ({})
6. **File Organization**: Follow the project's file organization pattern for script paths
7. **Signal & Export Patterns**: Match existing patterns for signals and exported variables
8. **Error Handling**: Include appropriate error handling consistent with project style

CODE GENERATION REQUIREMENTS:
- Extend the correct node type (infer from context if not specified)
- Include all necessary lifecycle methods (_ready, _process, _physics_process as appropriate)
- Add @export variables for configurable parameters (Godot 4.x) or export var (Godot 3.x)
- Define signals for important events
- Add clear, helpful comments explaining functionality
- Use proper type hints for variables and function parameters
- Include error checking where appropriate
- Follow the project's indentation style exactly

Respond with a JSON object:
{{
  "script_content": "extends NodeType\n\n# Your generated GDScript code here",
  "node_type": "The node type this script is for",
  "script_path": "Suggested file path following project organization",
  "description": "Brief description of what the script does",
  "integration_notes": "Any notes about how this integrates with existing project code"
}}

STRICT OUTPUT RULES:
- Respond ONLY with a valid JSON object (no prose before/after)
- Ensure all strings properly escape special characters (use \\n for newlines, \\t for tabs)
- No comments or trailing commas in the JSON
- The script_content must be a valid GDScript string with proper escaping
- Use the exact indentation style from the project analysis
"#,
            node_type_section,
            online_refs,
            official_docs,
            style_guide,
            context.project_context,
            context.user_input,
            project_style.godot_version
        );

        let response = call_llm(
            &self.client,
            &self.api_key,
            &self.model,
            &system_prompt,
            &context.user_input,
        ).await?;

        let execution_time_ms = start_time.elapsed().as_millis() as u64;
        let tokens_used = ((system_prompt.len() + context.user_input.len() + response.len()) / 4) as u32;

        let mut metadata = serde_json::Map::new();
        metadata.insert("godot_version".to_string(), Value::String(project_style.godot_version.clone()));
        metadata.insert("indentation_style".to_string(), Value::String(
            if project_style.indentation == "\t" { "tabs".to_string() } else { "spaces".to_string() }
        ));
        if let Some(nt) = target_node_type {
            metadata.insert("target_node_type".to_string(), Value::String(nt));
        }
        metadata.insert("sources_used".to_string(), Value::String("online_refs,official_docs,project_analysis".to_string()));

        Ok(AgentOutput {
            content: response,
            tokens_used,
            execution_time_ms,
            metadata,
        })
    }

    fn get_name(&self) -> &str {
        "GDScriptAgent"
    }

    fn get_model(&self) -> &str {
        &self.model
    }
}

/// Documentation Agent - Queries Official Godot Documentation
pub struct DocumentationAgent {
    api_key: String,
    client: Client,
    model: String,
}

impl DocumentationAgent {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
            model: "minimax/minimax-m2:free".to_string(),
        }
    }
}

#[async_trait::async_trait]
impl StrandsAgent for DocumentationAgent {
    async fn execute(&self, context: &AgentExecutionContext) -> Result<AgentOutput> {
        let start_time = std::time::Instant::now();

        // Search documentation knowledge base
        let docs = context.docs_kb.search(&context.user_input, 10).await?;

        let docs_content = docs.iter()
            .map(|d| format!("## {}\n{}", d.id, d.content))
            .collect::<Vec<_>>()
            .join("\n\n");

        let system_prompt = format!(r#"You are a documentation agent for Godot.

Retrieved Documentation:
{}

Summarize the most relevant information for the user's request.
Focus on API usage, best practices, and examples.
"#,
            docs_content
        );

        let response = call_llm(
            &self.client,
            &self.api_key,
            &self.model,
            &system_prompt,
            &context.user_input,
        ).await?;

        let execution_time_ms = start_time.elapsed().as_millis() as u64;
        let tokens_used = ((system_prompt.len() + context.user_input.len() + response.len()) / 4) as u32;

        let mut metadata = serde_json::Map::new();
        metadata.insert("docs_retrieved".to_string(), Value::Number(docs.len().into()));

        Ok(AgentOutput {
            content: response,
            tokens_used,
            execution_time_ms,
            metadata,
        })
    }

    fn get_name(&self) -> &str {
        "DocumentationAgent"
    }

    fn get_model(&self) -> &str {
        &self.model
    }
}

/// Helper function to call LLM API
async fn call_llm(
    client: &Client,
    api_key: &str,
    model: &str,
    system_prompt: &str,
    user_input: &str,
) -> Result<String> {
    #[derive(Serialize)]
    struct ChatRequest {
        model: String,
        messages: Vec<ChatMessage>,
        temperature: f32,
        max_tokens: i32,
    }

    #[derive(Serialize, Deserialize)]
    struct ChatMessage {
        role: String,
        content: String,
    }

    #[derive(Deserialize)]
    struct ChatResponse {
        choices: Vec<Choice>,
    }

    #[derive(Deserialize)]
    struct Choice {
        message: ChatMessage,
    }

    let request = ChatRequest {
        model: model.to_string(),
        messages: vec![
            ChatMessage {
                role: "system".to_string(),
                content: system_prompt.to_string(),
            },
            ChatMessage {
                role: "user".to_string(),
                content: user_input.to_string(),
            },
        ],
        temperature: 0.7,
        max_tokens: 8192,
    };

    let response = client
        .post("https://openrouter.ai/api/v1/chat/completions")
        .header("Authorization", format!("Bearer {}", api_key))
        .header("Content-Type", "application/json")
        .header("HTTP-Referer", "https://github.com/godoty/godoty")
        .header("X-Title", "Godoty AI Assistant")
        .json(&request)
        .send()
        .await?;

    if !response.status().is_success() {
        return Err(anyhow::anyhow!("LLM API request failed: {}", response.status()));
    }

    let response_text = response.text().await?;
    let chat_response: ChatResponse = serde_json::from_str(&response_text)?;

    if let Some(choice) = chat_response.choices.first() {
        Ok(choice.message.content.clone())
    } else {
        Err(anyhow::anyhow!("No response from LLM"))
    }
}
