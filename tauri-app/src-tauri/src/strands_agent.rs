use crate::agent::ExecutionPlan;
use crate::llm_client::{ChatMessageWithTools, LlmFactory, LlmResponse};
use crate::llm_config::AgentType;
use crate::mcp_client::McpClient;
use crate::mcp_tools::get_mcp_tool_definitions;
use crate::tool_executor::{format_tool_results_as_messages, ToolExecutor};
use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::time::SystemTime;

/// Represents a single thought/reasoning step from the orchestrator
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrchestratorThought {
    /// Phase of decision-making (e.g., "analyzing_input", "checking_context", "selecting_tools", "planning")
    pub phase: String,
    /// Human-readable insight about what the orchestrator is thinking
    pub insight: String,
    /// Confidence level (0.0-1.0)
    pub confidence: f32,
    /// When this thought occurred (skipped in serialization)
    #[serde(skip, default = "SystemTime::now")]
    #[allow(dead_code)]
    pub timestamp: SystemTime,
}

impl OrchestratorThought {
    pub fn new(phase: impl Into<String>, insight: impl Into<String>, confidence: f32) -> Self {
        Self {
            phase: phase.into(),
            insight: insight.into(),
            confidence: confidence.clamp(0.0, 1.0),
            timestamp: SystemTime::now(),
        }
    }
}

/// Base trait for all specialized agents
#[async_trait::async_trait]
pub trait StrandsAgent: Send + Sync {
    async fn execute(&self, context: &AgentExecutionContext) -> Result<AgentOutput>;
}

/// Context passed to agents during execution
#[derive(Clone)]
pub struct AgentExecutionContext {
    pub user_input: String,
    pub _chat_history: String,
    pub project_context: String,
    #[allow(dead_code)]
    pub execution_plan: Option<ExecutionPlan>,
    pub previous_output: Option<String>,
    #[allow(dead_code)]
    pub visual_context: Option<String>,
}

/// Output from agent execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentOutput {
    pub content: String,
    pub tokens_used: u32,
    pub execution_time_ms: u64,
    pub metadata: serde_json::Map<String, Value>,
    #[serde(default)]
    pub cost_usd: Option<f64>,
    /// Orchestrator's thought process (reasoning steps)
    #[serde(default)]
    pub thoughts: Vec<OrchestratorThought>,
}






/// Helper function to call LLM API
#[allow(dead_code)]
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
        #[serde(default)]
        usage: Option<Usage>,
    }

    #[derive(Deserialize)]
    struct Choice {
        message: ChatMessage,
        #[serde(default)]
        finish_reason: Option<String>,
    }

    #[derive(Debug, Deserialize)]
    struct Usage {
        #[allow(dead_code)]
        #[serde(default)]
        prompt_tokens: u32,
        #[allow(dead_code)]
        #[serde(default)]
        completion_tokens: u32,
        #[allow(dead_code)]
        #[serde(default)]
        total_tokens: u32,
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
        max_tokens: 16384, // Increased from 8192 to prevent truncation
    };

    let sys_prev = system_prompt.chars().take(200).collect::<String>();
    let user_prev = user_input.chars().take(200).collect::<String>();
    tracing::debug!(
        provider = "OpenRouter",
        model = %model,
        endpoint = "https://openrouter.ai/api/v1/chat/completions",
        system_prompt_preview = %sys_prev,
        user_input_preview = %user_prev,
        "Agent LLM invocation (fallback)"
    );

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
        return Err(anyhow::anyhow!(
            "LLM API request failed: {}",
            response.status()
        ));
    }

    let response_text = response.text().await?;
    let chat_response: ChatResponse = serde_json::from_str(&response_text).map_err(|e| {
        let preview = response_text.chars().take(500).collect::<String>();
        anyhow::anyhow!(
            "Failed to parse LLM response JSON: {}. Raw preview: {}",
            e,
            preview
        )
    })?;

    if let Some(choice) = chat_response.choices.first() {
        // Check if response was truncated due to token limit
        if let Some(ref finish_reason) = choice.finish_reason {
            if finish_reason == "length" {
                tracing::warn!(
                    model = %model,
                    usage = ?chat_response.usage,
                    response_len = response_text.len(),
                    "LLM response was truncated due to max_tokens limit. Consider increasing max_tokens or reducing prompt size."
                );
                // Log the full response for debugging
                tracing::debug!(full_response = %response_text, "Full truncated response");
            }
        }

        Ok(choice.message.content.clone())
    } else {
        Err(anyhow::anyhow!("No response from LLM"))
    }
}



/// Orchestrator Agent - routes the workflow and decides if research is needed
pub struct OrchestratorAgent {
    api_key: String,
    client: Client,
    model: String,
    llm_factory: Option<LlmFactory>,
}

impl OrchestratorAgent {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
            model: "x-ai/grok-4-fast".to_string(),
            llm_factory: None,
        }
    }

    pub fn with_llm_factory(mut self, llm_factory: Option<LlmFactory>) -> Self {
        self.llm_factory = llm_factory;
        self
    }

    /// Analyze user input and fetch relevant Godot documentation if needed
    async fn fetch_documentation_if_needed(
        &self,
        user_input: &str,
        thoughts: &mut Vec<OrchestratorThought>,
    ) -> Option<String> {
        use crate::context_engine::ContextEngine;

        // Common Godot node types and concepts that might need documentation
        let godot_keywords = [
            "CharacterBody2D", "CharacterBody3D", "RigidBody2D", "RigidBody3D",
            "Sprite2D", "Sprite3D", "AnimatedSprite2D", "AnimatedSprite3D",
            "CollisionShape2D", "CollisionShape3D", "Area2D", "Area3D",
            "Camera2D", "Camera3D", "Control", "Button", "Label", "Panel",
            "Node2D", "Node3D", "PackedScene", "Resource", "Signal",
            "TileMap", "NavigationAgent2D", "NavigationAgent3D",
            "AnimationPlayer", "AnimationTree", "AudioStreamPlayer",
        ];

        // Check if input contains any Godot-specific terms
        let input_lower = user_input.to_lowercase();
        let detected_keywords: Vec<&str> = godot_keywords
            .iter()
            .filter(|&&keyword| input_lower.contains(&keyword.to_lowercase()))
            .copied()
            .collect();

        if detected_keywords.is_empty() {
            thoughts.push(OrchestratorThought::new(
                "documentation_check",
                "No specific Godot types detected - using general knowledge",
                0.8,
            ));
            return None;
        }

        // Fetch documentation for detected keywords
        let topic = detected_keywords.join(" ");
        thoughts.push(OrchestratorThought::new(
            "documentation_fetch",
            format!(
                "Detected Godot types: {} - fetching documentation",
                detected_keywords.join(", ")
            ),
            0.9,
        ));

        let ctx_engine = ContextEngine::new(&self.api_key);
        match ctx_engine.fetch_from_context7(&topic).await {
            Ok(docs) => {
                thoughts.push(OrchestratorThought::new(
                    "documentation_retrieved",
                    format!("Retrieved {} chars of documentation for {}", docs.len(), topic),
                    0.95,
                ));
                Some(docs)
            }
            Err(e) => {
                thoughts.push(OrchestratorThought::new(
                    "documentation_error",
                    format!("Failed to fetch documentation: {} - proceeding with general knowledge", e),
                    0.6,
                ));
                None
            }
        }
    }
    /// Generate executable commands for a given execution plan using the Orchestrator model
    pub async fn generate_actions_for_plan(
        &self,
        plan: &ExecutionPlan,
        user_input: &str,
        plugin_examples: &str,
        allowed_actions_list: &str,
    ) -> Result<LlmResponse> {
        let system_prompt = format!(
            r#"You are a command generation agent for Godot.

Execution Plan:
{}

Plugin Command Examples:
{}

STRICT SCHEMA RULES:
- Every command MUST include an 'action' field; it must be one of: [{}].
- Map Godot UI/node types to the 'type' field ONLY when action = 'create_node' (or when searching by type). Do NOT use node types as command actions.
- Required fields by action:
  - create_node: type, name
  - create_scene: name, root_type
  - modify_node: path, properties
  - delete_node: path
  - attach_script: path, script_content
  - open_scene: path
  - select_nodes: paths
  - focus_node: path
  - rename_node: path, new_name
  - reparent_node: path, new_parent
- Use only fields defined in the schema. Do not invent new fields.

Generate a JSON array of commands to execute the plan.
Each command must be a valid JSON object matching the plugin's command schema OR the Desktop Commander MCP command schema.
- Desktop Commander MCP command shape: {{"action":"desktop_commander","tool": one of ["read_file","write_file","edit_block","create_directory","list_directory","move_file","start_search","get_more_search_results","stop_search","get_file_info"], "args": object}}
- Prefer "edit_block" for surgical edits to existing files; "write_file" for new files; use search/directory tools as needed.
- Keep ALL file/directory paths within the project root.
Respond ONLY with the JSON array, no explanations.
"#,
            serde_json::to_string_pretty(plan)?,
            plugin_examples,
            allowed_actions_list
        );

        if let Some(factory) = &self.llm_factory {
            let client = factory.create_client_for_agent(AgentType::Orchestrator)?;
            let sys_prev = system_prompt.chars().take(200).collect::<String>();
            let user_prev = user_input.chars().take(200).collect::<String>();
            tracing::debug!(
                agent = "OrchestratorAgent",
                model = %client.model_identifier(),
                endpoint = %client.endpoint(),
                system_prompt_preview = %sys_prev,
                user_input_preview = %user_prev,
                "Agent LLM invocation (generate_actions_for_plan)"
            );
            client.generate_response_with_usage(&system_prompt, user_input).await
        } else {
            // Fallback to OpenRouter call - wrap in LlmResponse
            let content = call_llm(&self.client, &self.api_key, &self.model, &system_prompt, user_input).await?;
            Ok(LlmResponse {
                content,
                usage: None,
                tool_calls: None,
            })
        }
    }

    /// Execute with tool calling support - allows the LLM to call MCP tools during decision-making
    pub async fn execute_with_tools(
        &self,
        context: &AgentExecutionContext,
        mcp_client: &mut Option<McpClient>,
    ) -> Result<AgentOutput> {
        let start_time = std::time::Instant::now();
        let mut thoughts = Vec::new();

        thoughts.push(OrchestratorThought::new(
            "tool_calling_mode",
            "Using tool calling mode - LLM can directly call MCP tools",
            0.95,
        ));

        // Get the LLM client
        let llm_client = if let Some(factory) = &self.llm_factory {
            factory.create_client_for_agent(AgentType::Orchestrator)?
        } else {
            return Err(anyhow::anyhow!("LLM factory required for tool calling mode"));
        };

        // Prepare system prompt with comprehensive instructions
        let system_prompt = format!(r#"You are the Orchestrator Agent for a Godot game development assistant with direct access to MCP tools.

## Available MCP Tools

You have DIRECT access to these tools - use them proactively to gather context and manage files/scripts:

**File Operations:**
- read_file(path): Read file contents from the project
- read_multiple_files(paths): Read multiple files simultaneously for efficiency
- write_file(path, content): Write content to a file (creates if doesn't exist)
- edit_block(path, old_text, new_text): Make surgical edits to existing files
- list_directory(path): List files and directories
- get_file_info(path): Get file metadata (size, modified time, etc.)
- move_file(source, destination): Move or rename files
- create_directory(path): Create new directories

**Search & Discovery:**
- start_search(query, path): Search for files or content in the project
- get_more_search_results(): Get additional results from ongoing search
- stop_search(): Stop an ongoing search
- fetch_documentation(topic): Fetch official Godot documentation for specific topics

**Process & Script Management:**
- start_process(command, timeout_ms, shell?): Start a new process/script with intelligent state detection
- interact_with_process(pid, input, timeout_ms?): Send input to running process and get response
- read_process(pid, timeout_ms?): Read output from a running process
- list_processes(): List all active terminal sessions/processes
- kill_process(pid): Force terminate a running process

**Use Cases for Process Tools:**
- Running GDScript validation scripts
- Executing build commands or asset processing scripts
- Running test suites or linters
- Interactive Python/Node.js REPLs for data processing
- Any command-line tool execution

## Your Workflow

**STEP 1: GATHER COMPLETE CONTEXT** (CRITICAL - DO THIS FIRST!)
Before making ANY decisions, you MUST gather comprehensive context:

1. **Review the project structure** provided below - understand what scenes and scripts already exist
2. **Use list_directory** to explore relevant directories (e.g., "res://scenes", "res://scripts")
3. **Use read_file or read_multiple_files** to examine existing scenes/scripts that are related to the task
4. **Use fetch_documentation** to get Godot API docs for node types you'll be working with
5. **Use start_search** to find similar implementations or related code

DO NOT skip context gathering! The project structure below is just an overview - you need to read actual files.

**SCRIPT & FILE MANAGEMENT BEST PRACTICES:**
When managing scripts and files:
- **Use write_file** for creating new scripts/files
- **Use edit_block** for modifying existing files (more precise than rewriting entire file)
- **Use read_multiple_files** when you need to examine several related files at once
- **Use start_process** to run validation scripts, tests, or build commands
- **Use interact_with_process** for interactive script execution (e.g., Python REPL for data processing)
- **Always validate** scripts after creation by running them with start_process if applicable

**STEP 2: ANALYZE & PLAN**
After gathering context, analyze the user's request:
- Is this a simple task that can be done with direct commands?
- Does it require research from the Research Agent?
- What's the best approach given the existing project structure?

**STEP 3: CREATE MODULAR PLAN**
When creating scenes, follow these principles:
- **Separate concerns**: Create individual scene files for each logical component
- **Reusable components**: Make scenes that can be instantiated multiple times
- **Proper hierarchy**: Use scene inheritance and composition appropriately
- **Follow Godot conventions**: Use appropriate root node types (Control for UI, Node2D/3D for gameplay)

Example: For a "player with health UI", create:
1. `player.tscn` - CharacterBody2D with movement logic
2. `health_bar.tscn` - Control-based UI component
3. `player_hud.tscn` - Combines health bar and other UI elements
4. Main scene that instances the player and HUD

**STEP 4: PROVIDE DECISION**
Return your decision as JSON:
{{
  "research_needed": boolean,  // true if Research Agent should gather more info
  "research_queries": string[],  // specific queries for Research Agent
  "simple_enough": boolean,  // true if you can handle this directly
  "initial_plan": {{
    "reasoning": string,  // explain your approach and why
    "steps": [{{
      "step_number": number,
      "description": string,  // what this step accomplishes
      "commands_needed": [string]  // Godot commands: create_scene, add_node, attach_script, etc.
    }}],
    "estimated_complexity": "low" | "medium" | "high"
  }},
  "direct_commands": []  // only for trivial tasks
}}

## Project Context

{}

## User Request

{}"#, context.project_context, context.user_input);

        // Initialize conversation with system message and user input
        let mut messages = vec![
            ChatMessageWithTools {
                role: "system".to_string(),
                content: system_prompt,
                tool_calls: None,
                tool_call_id: None,
            },
            ChatMessageWithTools {
                role: "user".to_string(),
                content: format!(
                    "{}\n\nREMINDER: Start by using MCP tools to gather context. Use list_directory, read_file, and fetch_documentation to understand the project before making decisions.",
                    context.user_input
                ),
                tool_calls: None,
                tool_call_id: None,
            },
        ];

        // Get tool definitions
        let tools = get_mcp_tool_definitions();
        let tool_executor = ToolExecutor::new(self.api_key.clone());

        // Tool calling loop (max 10 iterations to allow thorough context gathering)
        let max_iterations = 10;
        let mut final_response = String::new();

        for iteration in 0..max_iterations {
            thoughts.push(OrchestratorThought::new(
                "llm_call",
                format!("Making LLM call with {} available tools (iteration {}/{})", tools.len(), iteration + 1, max_iterations),
                0.9,
            ));

            // Call LLM with tools
            let response = llm_client
                .generate_response_with_tools(messages.clone(), Some(tools.clone()))
                .await?;

            // Check if LLM wants to call tools
            if let Some(tool_calls) = &response.tool_calls {
                // Log which tools are being called
                let tool_names: Vec<String> = tool_calls.iter()
                    .map(|tc| tc.function.name.clone())
                    .collect();
                thoughts.push(OrchestratorThought::new(
                    "tool_calls_requested",
                    format!("LLM requested {} tool calls: {}", tool_calls.len(), tool_names.join(", ")),
                    0.85,
                ));

                // Add assistant message with tool calls to conversation
                messages.push(ChatMessageWithTools {
                    role: "assistant".to_string(),
                    content: response.content.clone(),
                    tool_calls: Some(tool_calls.clone()),
                    tool_call_id: None,
                });

                // Execute tools
                let results = tool_executor
                    .execute_tools_parallel(tool_calls, mcp_client)
                    .await;

                // Log tool execution results with details
                for (i, (tool_call_id, result)) in results.iter().enumerate() {
                    let tool_name = &tool_calls[i].function.name;
                    let status = if result.is_ok() { "success" } else { "error" };
                    let detail = match result {
                        Ok(val) => {
                            let preview = serde_json::to_string(val)
                                .unwrap_or_default()
                                .chars()
                                .take(100)
                                .collect::<String>();
                            format!("{}: {}", status, preview)
                        }
                        Err(e) => format!("{}: {}", status, e),
                    };
                    thoughts.push(OrchestratorThought::new(
                        "tool_executed",
                        format!("Tool '{}' ({}): {}", tool_name, tool_call_id, detail),
                        if result.is_ok() { 0.9 } else { 0.5 },
                    ));
                }

                // Add tool results to conversation
                let tool_messages = format_tool_results_as_messages(results);
                messages.extend(tool_messages);

                // Continue loop to get next LLM response
            } else {
                // No tool calls - this is the final response
                final_response = response.content;
                thoughts.push(OrchestratorThought::new(
                    "decision_made",
                    "LLM provided final decision without requesting more tools",
                    0.95,
                ));
                break;
            }
        }

        // Check if we hit the iteration limit
        if final_response.is_empty() {
            thoughts.push(OrchestratorThought::new(
                "max_iterations_reached",
                format!("Reached maximum iterations ({}). Using last response.", max_iterations),
                0.6,
            ));
            // Try to extract the last assistant message as the final response
            for msg in messages.iter().rev() {
                if msg.role == "assistant" && !msg.content.is_empty() {
                    final_response = msg.content.clone();
                    break;
                }
            }
        }

        let execution_time_ms = start_time.elapsed().as_millis() as u64;

        Ok(AgentOutput {
            content: final_response,
            tokens_used: 0, // TODO: aggregate from all LLM calls
            execution_time_ms,
            metadata: serde_json::Map::new(),
            cost_usd: None,
            thoughts,
        })
    }

}

#[async_trait::async_trait]
impl StrandsAgent for OrchestratorAgent {
    async fn execute(&self, context: &AgentExecutionContext) -> Result<AgentOutput> {
        let start_time = std::time::Instant::now();
        let mut thoughts = Vec::new();

        // Phase 1: Analyze input
        let input_preview: String = context.user_input.chars().take(100).collect();
        thoughts.push(OrchestratorThought::new(
            "analyzing_input",
            format!("Analyzing request: '{}'", input_preview),
            0.9,
        ));

        let heuristics_flag = {
            let u = context.user_input.to_lowercase();
            let indicators = ["how", "which", "search", "latest", "docs", "explain", "compare", "best"];
            indicators.iter().any(|w| u.contains(w))
        };

        if heuristics_flag {
            thoughts.push(OrchestratorThought::new(
                "research_detection",
                "Detected research indicators - may need additional context",
                0.85,
            ));
        }

        // Phase 2: Fetch documentation if needed
        thoughts.push(OrchestratorThought::new(
            "checking_documentation",
            "Checking if Godot-specific documentation is needed",
            0.8,
        ));

        let additional_docs = self.fetch_documentation_if_needed(&context.user_input, &mut thoughts).await;

        // Phase 3: Prepare system prompt
        thoughts.push(OrchestratorThought::new(
            "preparing_context",
            "Preparing orchestration context and available tools",
            0.9,
        ));

        let system_prompt = format!(r#"You are the Orchestrator Agent for a Godot assistant.

Decide whether additional RESEARCH is needed and whether the task is SIMPLE ENOUGH to implement directly.
Return STRICT JSON with fields:
{{
  "research_needed": boolean,
  "research_queries": string[],
  "simple_enough": boolean,
  "initial_plan": {{
    "reasoning": string,
    "steps": [{{"step_number": number, "description": string, "commands_needed": [string]}}],
    "estimated_complexity": "low" | "medium" | "high"
  }} | null,
  "direct_commands": [object],
  "reasoning": string
}}
Rules:
- Only output JSON, no prose.
- If simple_enough is true: ALWAYS return a concrete non-empty "direct_commands" array of executable Godoty command objects and you may set "initial_plan" to null.
- If simple_enough is false: provide an "initial_plan" and set "direct_commands" to [].
- Commands must adhere to the Godoty command schema provided in context (e.g., create_node, open_scene, modify_node, attach_script, select_nodes, focus_node, play, capture_game_screenshot).
- For filesystem/code edits, use desktop_commander tool with shape {{"action":"desktop_commander","tool": "read_file"|"write_file"|"edit_block"|"list_directory"|"start_search"|"read_multiple_files"|etc., "args": object}}.
- For running scripts/commands, use desktop_commander process tools: {{"action":"desktop_commander","tool": "start_process"|"interact_with_process"|"read_process"|"list_processes"|"kill_process", "args": object}}.
- When debugging or analyzing running game behavior, use capture_game_screenshot to capture the game's visual state for context in subsequent steps.
- Visual context (screenshots) can be used to understand the current state and make informed decisions about next steps.
{}
"#, if let Some(ref docs) = additional_docs {
    format!("\n# Additional Godot Documentation\n{}", docs.chars().take(2000).collect::<String>())
} else {
    String::new()
});
        let user_msg = format!(
            "User Input: {}\nProject Context (truncated): {}",
            context.user_input,
            context.project_context.chars().take(600).collect::<String>()
        );

        // Phase 4: Generate plan and commands
        thoughts.push(OrchestratorThought::new(
            "generating_plan",
            "Invoking LLM to generate execution plan and commands",
            0.85,
        ));

        let (content, cost_usd) = if let Some(factory) = &self.llm_factory {
            let client = factory.create_client_for_agent(AgentType::Orchestrator)?;
            let sys_prev = system_prompt.chars().take(200).collect::<String>();
            let user_prev = user_msg.chars().take(200).collect::<String>();
            tracing::debug!(
                agent = "OrchestratorAgent",
                model = %client.model_identifier(),
                endpoint = %client.endpoint(),
                system_prompt_preview = %sys_prev,
                user_input_preview = %user_prev,
                "Agent LLM invocation"
            );
            let response = client.generate_response_with_usage(&system_prompt, &user_msg).await?;
            let cost = response.usage.as_ref().and_then(|u| u.cost);

            thoughts.push(OrchestratorThought::new(
                "llm_response_received",
                format!("Received LLM response ({} chars)", response.content.len()),
                0.9,
            ));

            (response.content, cost)
        } else {
            // Fallback: heuristic JSON with optional initial plan for simple intents
            thoughts.push(OrchestratorThought::new(
                "heuristic_fallback",
                "Using heuristic-based decision making (no LLM factory configured)",
                0.7,
            ));
            let queries = vec![context.user_input.clone()];
            let u = context.user_input.to_lowercase();
            let simple_enough = [
                "create", "open", "rename", "focus", "select", "play", "duplicate", "reparent", "attach script"
            ].iter().any(|k| u.contains(k));

            let (commands_needed, estimated_complexity) = if simple_enough {
                let mut cmds: Vec<&str> = Vec::new();
                if u.contains("attach") && u.contains("script") { cmds.push("attach_script"); }
                if u.contains("open") && u.contains("scene") { cmds.push("open_scene"); }
                if u.contains("create") && u.contains("scene") { cmds.push("create_scene"); }
                if u.contains("create") && !u.contains("scene") { cmds.push("create_node"); }
                if u.contains("rename") { cmds.push("rename_node"); }
                if u.contains("reparent") { cmds.push("reparent_node"); }
                if u.contains("duplicate") { cmds.push("duplicate_node"); }
                if u.contains("select") { cmds.push("select_nodes"); }
                if u.contains("focus") { cmds.push("focus_node"); }
                if u.contains("play") { cmds.push("play"); }
                (cmds.into_iter().map(|s| s.to_string()).collect::<Vec<String>>(), "low")
            } else { (Vec::new(), "medium") };

            // Minimal direct commands we can safely infer without deep parsing
            let mut direct_commands: Vec<serde_json::Value> = Vec::new();
            if u.contains("play") {
                direct_commands.push(serde_json::json!({"action": "play", "mode": "current"}));
            }

            let initial_plan = if simple_enough {
                Some(serde_json::json!({
                    "reasoning": "Heuristic minimal plan for simple UI/file operation",
                    "steps": [{
                        "step_number": 1,
                        "description": "Perform the simple action using Godoty plugin commands",
                        "commands_needed": commands_needed
                    }],
                    "estimated_complexity": estimated_complexity
                }))
            } else { None };

            let content = serde_json::json!({
                "research_needed": heuristics_flag,
                "research_queries": queries,
                "simple_enough": simple_enough,
                "initial_plan": initial_plan,
                "direct_commands": direct_commands,
                "reasoning": "Heuristic: based on user phrasing, action keywords, and KB hits"
            }).to_string();

            thoughts.push(OrchestratorThought::new(
                "heuristic_decision",
                format!("Simple enough: {}, Research needed: {}", simple_enough, heuristics_flag),
                0.75,
            ));

            (content, None)
        };

        // Phase 5: Finalize and return
        thoughts.push(OrchestratorThought::new(
            "orchestration_complete",
            format!("Orchestration complete in {}ms", start_time.elapsed().as_millis()),
            0.95,
        ));

        let exec_ms = start_time.elapsed().as_millis() as u64;
        Ok(AgentOutput {
            content,
            tokens_used: 0,
            execution_time_ms: exec_ms,
            metadata: serde_json::Map::new(),
            cost_usd,
            thoughts,
        })
    }

}

/// Research Agent - aggregates KB findings and optional web search
pub struct ResearchAgent {
    #[allow(dead_code)]
    api_key: String,
    #[allow(dead_code)]
    client: Client,
    #[allow(dead_code)]
    model: String,
    llm_factory: Option<LlmFactory>,
}

impl ResearchAgent {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
            model: "deepseek/deepseek-v3.2-exp".to_string(),
            llm_factory: None,
        }
    }

    pub fn with_llm_factory(mut self, llm_factory: Option<LlmFactory>) -> Self {
        self.llm_factory = llm_factory;
        self
    }
}

#[async_trait::async_trait]
impl StrandsAgent for ResearchAgent {
    async fn execute(&self, context: &AgentExecutionContext) -> Result<AgentOutput> {
        let start_time = std::time::Instant::now();
        let mut thoughts = Vec::new();

        thoughts.push(OrchestratorThought::new(
            "research_start",
            "Starting research phase",
            0.9,
        ));

        // Derive queries
        let mut queries: Vec<String> = Vec::new();
        if let Some(prev) = &context.previous_output {
            if let Ok(v) = serde_json::from_str::<serde_json::Value>(prev) {
                if let Some(arr) = v.get("research_queries").and_then(|x| x.as_array()) {
                    for q in arr {
                        if let Some(s) = q.as_str() { queries.push(s.to_string()); }
                    }
                }
            }
        }
        if queries.is_empty() { queries.push(context.user_input.clone()); }

        thoughts.push(OrchestratorThought::new(
            "research_queries",
            format!("Identified {} research queries", queries.len()),
            0.85,
        ));

        // Knowledge base searches removed - using Context7 via ContextEngine instead
        let kb_notes = String::new();
        let kb_hits_total = 0usize;

        // Web search removed
        let web_section = String::new();
        let web_count = 0usize;

        // Build a planning prompt that turns research into an ExecutionPlan JSON
        let system_prompt = r#"You are the Research Planning Agent for a Godot assistant.
Using the evidence below (Project Index context, Plugin KB, Official Godot Docs, and optional Web results), produce an EXECUTION PLAN as STRICT JSON ONLY with this exact shape:
{
  "reasoning": string,
  "steps": [{"step_number": number, "description": string, "commands_needed": [string]}],
  "estimated_complexity": "low" | "medium" | "high"
}
Guidelines:
- Cross-check findings against Official Godot Docs and the Project Index. Prefer official docs when conflicts arise.
- Steps should reference actions achievable via the Godoty plugin command set (e.g., create_node, open_scene, modify_node, attach_script, rename_node, reparent_node, select_nodes, focus_node, play, duplicate_node).
- Keep the plan minimal but complete. If the request appears trivial and requires no change, return an empty steps array and estimated_complexity = "low" with an explanatory reasoning.
- Output ONLY the JSON object, no prose.
"#;
        let user_msg = format!(
            "User Input: {}\nProject Context: {}\n\nKB Evidence:\n{}\n\nWeb Evidence:\n{}",
            context.user_input,
            context.project_context.chars().take(1600).collect::<String>(),
            kb_notes,
            web_section
        );

        let (content, cost_usd) = if let Some(factory) = &self.llm_factory {
            let client = factory.create_client_for_agent(AgentType::Researcher)?;
            let sys_prev = system_prompt.chars().take(200).collect::<String>();
            let user_prev = user_msg.chars().take(200).collect::<String>();
            tracing::debug!(
                agent = "ResearchAgent",
                model = %client.model_identifier(),
                endpoint = %client.endpoint(),
                system_prompt_preview = %sys_prev,
                user_input_preview = %user_prev,
                "Agent LLM invocation"
            );
            let response = client.generate_response_with_usage(system_prompt, &user_msg).await?;
            let cost = response.usage.as_ref().and_then(|u| u.cost);

            thoughts.push(OrchestratorThought::new(
                "research_plan_generated",
                format!("Generated research plan ({} chars)", response.content.len()),
                0.9,
            ));

            (response.content, cost)
        } else {
            thoughts.push(OrchestratorThought::new(
                "research_heuristic",
                "Using heuristic research planning",
                0.7,
            ));

            // Fallback: build a minimal heuristic plan from evidence
            let reasoning = if kb_hits_total > 0 {
                "Heuristic plan derived from KB evidence"
            } else if web_count > 0 {
                "Heuristic plan derived from web evidence"
            } else {
                "Heuristic plan with limited evidence"
            };
            let step_desc = if kb_notes.is_empty() {
                "Review relevant project files and apply the requested change, consulting official docs if needed"
            } else {
                "Apply the requested change using patterns found in the knowledge base and verify against official docs"
            };
            let content = serde_json::json!({
                "reasoning": reasoning,
                "steps": [{
                    "step_number": 1,
                    "description": step_desc,
                    "commands_needed": []
                }],
                "estimated_complexity": if kb_hits_total > 0 || web_count > 0 { "low" } else { "medium" }
            }).to_string();
            (content, None)
        };

        thoughts.push(OrchestratorThought::new(
            "research_complete",
            format!("Research complete in {}ms", start_time.elapsed().as_millis()),
            0.95,
        ));

        let mut metadata = serde_json::Map::new();
        metadata.insert("queries".into(), serde_json::json!(queries));
        metadata.insert("web_results_count".into(), serde_json::json!(web_count));
        metadata.insert("kb_hits".into(), serde_json::json!(kb_hits_total));

        let exec_ms = start_time.elapsed().as_millis() as u64;
        Ok(AgentOutput {
            content,
            tokens_used: 0,
            execution_time_ms: exec_ms,
            metadata,
            cost_usd,
            thoughts,
        })
    }

}

