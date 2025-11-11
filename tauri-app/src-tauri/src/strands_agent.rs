use crate::agent::ExecutionPlan;
use crate::llm_client::LlmFactory;
use crate::llm_config::AgentType;
use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value;

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
            model: "minimax/minimax-m2:free".to_string(),
            llm_factory: None,
        }
    }

    pub fn with_llm_factory(mut self, llm_factory: Option<LlmFactory>) -> Self {
        self.llm_factory = llm_factory;
        self
    }
    /// Generate executable commands for a given execution plan using the Orchestrator model
    pub async fn generate_actions_for_plan(
        &self,
        plan: &ExecutionPlan,
        user_input: &str,
        plugin_examples: &str,
        allowed_actions_list: &str,
    ) -> Result<String> {
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
            client.generate_response(&system_prompt, user_input).await
        } else {
            // Fallback to OpenRouter call
            call_llm(&self.client, &self.api_key, &self.model, &system_prompt, user_input).await
        }
    }

}

#[async_trait::async_trait]
impl StrandsAgent for OrchestratorAgent {
    async fn execute(&self, context: &AgentExecutionContext) -> Result<AgentOutput> {
        let start_time = std::time::Instant::now();

        let heuristics_flag = {
            let u = context.user_input.to_lowercase();
            let indicators = ["how", "which", "search", "latest", "docs", "explain", "compare", "best"];
            indicators.iter().any(|w| u.contains(w))
        };

        let system_prompt = r#"You are the Orchestrator Agent for a Godot assistant.
Decide whether additional RESEARCH is needed and whether the task is SIMPLE ENOUGH to implement directly.
Return STRICT JSON with fields:
{
  "research_needed": boolean,
  "research_queries": string[],
  "simple_enough": boolean,
  "initial_plan": {
    "reasoning": string,
    "steps": [{"step_number": number, "description": string, "commands_needed": [string]}],
    "estimated_complexity": "low" | "medium" | "high"
  } | null,
  "direct_commands": [object],
  "reasoning": string
}
Rules:
- Only output JSON, no prose.
- If simple_enough is true: ALWAYS return a concrete non-empty "direct_commands" array of executable Godoty command objects and you may set "initial_plan" to null.
- If simple_enough is false: provide an "initial_plan" and set "direct_commands" to [].
- Commands must adhere to the Godoty command schema provided in context (e.g., create_node, open_scene, modify_node, attach_script, select_nodes, focus_node, play).
- For filesystem/code edits, emit Desktop Commander MCP commands with shape {"action":"desktop_commander","tool": one of ["read_file","write_file","edit_block","create_directory","list_directory","move_file","start_search","get_more_search_results","stop_search","get_file_info"], "args": object}. Prefer "edit_block" for surgical changes; "write_file" for new files; use directory and search tools as needed. Keep ALL paths within the project root.
"#;
        let user_msg = format!(
            "User Input: {}\nProject Context (truncated): {}",
            context.user_input,
            context.project_context.chars().take(600).collect::<String>()
        );

        let content = if let Some(factory) = &self.llm_factory {
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
            client.generate_response(system_prompt, &user_msg).await?
        } else {
            // Fallback: heuristic JSON with optional initial plan for simple intents
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

            serde_json::json!({
                "research_needed": heuristics_flag,
                "research_queries": queries,
                "simple_enough": simple_enough,
                "initial_plan": initial_plan,
                "direct_commands": direct_commands,
                "reasoning": "Heuristic: based on user phrasing, action keywords, and KB hits"
            }).to_string()
        };

        let exec_ms = start_time.elapsed().as_millis() as u64;
        Ok(AgentOutput {
            content,
            tokens_used: 0,
            execution_time_ms: exec_ms,
            metadata: serde_json::Map::new(),
            cost_usd: None,
        })
    }

}

/// Research Agent - aggregates KB findings and optional web search
pub struct ResearchAgent {
    api_key: String,
    client: Client,
    model: String,
    llm_factory: Option<LlmFactory>,
}

impl ResearchAgent {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
            model: "qwen/qwen3-235b-a22b:free".to_string(),
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

        let content = if let Some(factory) = &self.llm_factory {
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
            client.generate_response(system_prompt, &user_msg).await?
        } else {
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
            serde_json::json!({
                "reasoning": reasoning,
                "steps": [{
                    "step_number": 1,
                    "description": step_desc,
                    "commands_needed": []
                }],
                "estimated_complexity": if kb_hits_total > 0 || web_count > 0 { "low" } else { "medium" }
            }).to_string()
        };

        let mut metadata = serde_json::Map::new();
        metadata.insert("queries".into(), serde_json::json!(queries));
        metadata.insert("web_results_count".into(), serde_json::json!(web_count));
        metadata.insert("kb_hits".into(), serde_json::json!(kb_hits_total));

        let exec_ms = start_time.elapsed().as_millis() as u64;
        Ok(AgentOutput { content, tokens_used: 0, execution_time_ms: exec_ms, metadata, cost_usd: None })
    }

}

