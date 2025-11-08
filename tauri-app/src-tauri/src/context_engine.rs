use crate::chat_session::ChatSession;
use crate::project_indexer::ProjectIndex;
use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};

// Bundled, high-signal Godot docs used as a fast offline cache
const BUNDLED_GODOT_DOCS: &str = include_str!("../assets/godot_docs_bundled.md");

// Compact reference of Godoty command executor tools for AI prompting
const GODOTY_TOOL_REFERENCE: &str = r#"
- create_scene: {"action":"create_scene","name":"Name","root_type":"NodeType","save_path":"res://Scene.tscn"}
- open_scene: {"action":"open_scene","path":"res://Scene.tscn"}
- get_scene_info: {"action":"get_scene_info"}
- get_current_scene_detailed: {"action":"get_current_scene_detailed"}
- inspect_scene_file: {"action":"inspect_scene_file","path":"res://Scene.tscn"}
- create_node: {"action":"create_node","type":"Type","name":"Name","parent":"Parent or null","properties":{}}
- modify_node: {"action":"modify_node","path":"NodePath","properties":{}}
- delete_node: {"action":"delete_node","path":"NodePath"}
- attach_script: {"action":"attach_script","path":"NodePath","script_content":"...","script_path":"res://opt.gd"}
- select_nodes: {"action":"select_nodes","paths":["Root/A","Root/B"]}
- focus_node: {"action":"focus_node","path":"Root/Node","select":true}
- play: {"action":"play","mode":"current|main|custom","path":"res://opt.tscn"}
- add_command_palette_command: {"action":"add_command_palette_command","display_name":"...","key":"...","action_to_execute":"...","payload":{}}
- search_nodes_by_type: {"action":"search_nodes_by_type","type":"Sprite2D","select_results":false,"focus_first":false}
- search_nodes_by_name: {"action":"search_nodes_by_name","name":"Enemy","exact":false,"case_sensitive":false}
- search_nodes_by_group: {"action":"search_nodes_by_group","group":"enemies"}
- search_nodes_by_script: {"action":"search_nodes_by_script","script_path":null}
- duplicate_node: {"action":"duplicate_node","path":"Root/A","parent":"Root/B","name":"Copy"}
- reparent_node: {"action":"reparent_node","path":"Root/A","new_parent":"Root/B","index":-1,"keep_global_transform":true}
- rename_node: {"action":"rename_node","path":"Root/A","new_name":"NewName"}
- add_to_group: {"action":"add_to_group","path":"Root/A","group":"grp","persistent":true}
- remove_from_group: {"action":"remove_from_group","path":"Root/A","group":"grp"}
- start_debug_capture: {"action":"start_debug_capture"}
- stop_debug_capture: {"action":"stop_debug_capture"}
- get_debug_output: {"action":"get_debug_output","limit":200}
- clear_debug_output: {"action":"clear_debug_output"}
- capture_visual_context: {"action":"capture_visual_context","metadata":{}}
- get_visual_snapshot: {"action":"get_visual_snapshot"}
- enable_auto_visual_capture: {"action":"enable_auto_visual_capture"}
- disable_auto_visual_capture: {"action":"disable_auto_visual_capture"}
"#;

#[derive(Serialize, Deserialize)]
struct ChatRequest {
    model: String,
    messages: Vec<ApiChatMessage>,
    temperature: f32,
    max_tokens: i32,
}

#[derive(Serialize, Deserialize)]
struct ApiChatMessage {
    role: String,
    content: String,
}

#[derive(Deserialize)]
struct ChatResponse {
    choices: Vec<Choice>,
}

#[derive(Deserialize)]
struct Choice {
    message: ApiChatMessage,
}

/// Comprehensive context engine that manages all context sources
#[derive(Clone)]
pub struct ContextEngine {
    api_key: String,
    client: Client,
    godot_docs_cache: std::sync::Arc<tokio::sync::Mutex<Option<String>>>,
    context7_enabled: bool,
}

impl ContextEngine {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
            godot_docs_cache: std::sync::Arc::new(tokio::sync::Mutex::new(None)),
            context7_enabled: true, // Context7 integration enabled; will gracefully fall back to bundled docs
        }
    }

    /// Load cached Godot documentation
    pub async fn load_cached_docs(&self, cached_docs: Option<String>) -> Result<()> {
        if let Some(docs) = cached_docs {
            let mut cache = self.godot_docs_cache.lock().await;
            *cache = Some(docs);
        }
        Ok(())
    }

    /// Get cached documentation for persistence
    pub async fn get_cached_docs(&self) -> Option<String> {
        let cache = self.godot_docs_cache.lock().await;
        cache.clone()
    }
    /// Proactively fetch a broad slice of Godot docs and cache them for reuse
    pub async fn prefetch_common_godot_docs(&self) -> Result<()> {
        // If already present, skip
        if self.get_cached_docs().await.is_some() {
            return Ok(());
        }

        // Seed with bundled docs to ensure immediate availability
        {
            let mut cache = self.godot_docs_cache.lock().await;
            if cache.is_none() {
                *cache = Some(BUNDLED_GODOT_DOCS.to_string());
            }
        }

        // Optionally enrich/refresh from Context7 using a wide topic query
        let enrichment_query = "nodes scenes Control Node2D CharacterBody2D signals ownership PackedScene NodePath editor tool scripts common pitfalls";
        let enriched = self
            .fetch_from_context7(enrichment_query)
            .await
            .unwrap_or_else(|_| BUNDLED_GODOT_DOCS.to_string());
        let mut cache = self.godot_docs_cache.lock().await;
        *cache = Some(enriched);
        Ok(())
    }

    /// Build comprehensive context from all sources
    pub async fn build_comprehensive_context(
        &self,
        user_input: &str,
        project_index: &ProjectIndex,
        chat_session: Option<&ChatSession>,
        max_history_messages: usize,
    ) -> Result<ComprehensiveContext> {
        // 1. Analyze user input to determine what context is needed
        let context_query = self.analyze_input_for_context(user_input).await?;

        // 2. Fetch Godot documentation
        let godot_docs = self.fetch_godot_docs(&context_query).await?;

        // 3. Search project index
        let project_context = self.search_project_index(&context_query, project_index);

        // 4. Build chat history context
        let chat_history = if let Some(session) = chat_session {
            session.build_accumulated_context()
        } else {
            String::new()
        };

        // 5. Get recent messages for conversation continuity
        let recent_messages = if let Some(session) = chat_session {
            session.get_context_messages(max_history_messages)
        } else {
            Vec::new()
        };

        Ok(ComprehensiveContext {
            godot_docs,
            project_context,
            chat_history,
            recent_messages,
            context_query,
            visual_analysis: None,
            tutorial_context: None,
        })
    }

    /// Format context for AI consumption
    pub fn format_context_for_ai(&self, context: &ComprehensiveContext) -> String {
        let mut formatted = String::new();

        // Add Godot documentation
        formatted.push_str("# Godot Documentation\n");
        formatted.push_str(&context.godot_docs);
        formatted.push_str("\n\n");

        // Add project context
        formatted.push_str("# Current Project Context\n");
        formatted.push_str(&context.project_context);
        formatted.push_str("\n\n");

        // Add visual analysis if available
        if let Some(visual) = &context.visual_analysis {
            formatted.push_str("# Visual Analysis (Viewport/Inspector)\n");
            formatted.push_str(visual);
            formatted.push_str("\n\n");
        }

        // Add tutorial context if available, with precedence note
        if let Some(tuts) = &context.tutorial_context {
            formatted.push_str("# Tutorial Context (Lower Precedence)\n");
            formatted.push_str("Note: Official Godot documentation takes precedence over tutorials. Conflicts will be resolved in favor of docs.\n\n");
            formatted.push_str(tuts);
            formatted.push_str("\n\n");
        }

        // Add chat history if available
        if !context.chat_history.is_empty() {
            formatted.push_str(&context.chat_history);
            formatted.push_str("\n\n");
        }

        // Add Godoty command executor tool reference to help the AI plan and validate commands
        formatted.push_str("# Godoty Command Executor – Tool Reference\n");
        formatted.push_str(GODOTY_TOOL_REFERENCE);
        formatted.push_str("\n\n");

        formatted
    }

    /// Analyze user input to determine what context to retrieve
    async fn analyze_input_for_context(&self, user_input: &str) -> Result<String> {
        // Offline mode: skip network calls and use raw input as the query
        if std::env::var("GODOTY_OFFLINE").ok().as_deref() == Some("1") {
            return Ok(user_input.to_string());
        }

        let system_prompt = r#"You are a context analyzer for a Godot game development assistant.
Analyze the user's request and extract key topics, node types, and concepts that would be relevant.
Return a concise list of keywords and topics to search for in documentation and project files.

Example:
User: "Create a 2D player character with movement"
Output: CharacterBody2D, Sprite2D, Input, movement, velocity, 2D physics

User: "Add a health system to my player"
Output: health, variables, signals, UI, ProgressBar, damage system

User: "Fix the jumping mechanic"
Output: jump, physics, velocity, CharacterBody2D, Input, gravity"#;

        let request = ChatRequest {
            model: "z-ai/glm-4.5-air:free".to_string(),
            messages: vec![
                ApiChatMessage {
                    role: "system".to_string(),
                    content: system_prompt.to_string(),
                },
                ApiChatMessage {
                    role: "user".to_string(),
                    content: user_input.to_string(),
                },
            ],
            temperature: 0.3,
            max_tokens: 200,
        };

        let response = match self
            .client
            .post("https://openrouter.ai/api/v1/chat/completions")
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", "application/json")
            .header("HTTP-Referer", "https://github.com/godoty/godoty")
            .header("X-Title", "Godoty AI Assistant")
            .json(&request)
            .send()
            .await
        {
            Ok(resp) => resp,
            Err(e) => {
                eprintln!(
                    "OpenRouter API request error: {}. Falling back to raw input for context query",
                    e
                );
                return Ok(user_input.to_string());
            }
        };

        if !response.status().is_success() {
            // Fall back gracefully when the API is unavailable or rate-limited
            eprintln!(
                "OpenRouter API request failed (status {}), falling back to raw input for context query",
                response.status()
            );
            return Ok(user_input.to_string());
        }

        let response_text = response.text().await?;

        match serde_json::from_str::<ChatResponse>(&response_text) {
            Ok(chat_response) => {
                if let Some(choice) = chat_response.choices.first() {
                    Ok(choice.message.content.clone())
                } else {
                    Ok(user_input.to_string())
                }
            }
            Err(e) => {
                // Fall back to the original user input if parsing fails
                eprintln!(
                    "Failed to parse context-analyzer response: {}. Falling back to raw input. Partial: {}",
                    e,
                    &response_text[..response_text.len().min(200)]
                );
                Ok(user_input.to_string())
            }
        }
    }

    /// Fetch Godot documentation (with caching)
    async fn fetch_godot_docs(&self, query: &str) -> Result<String> {
        // Check in-memory cache first
        {
            let cache = self.godot_docs_cache.lock().await;
            if let Some(docs) = cache.as_ref() {
                return Ok(docs.clone());
            }
        }

        // Fetch documentation
        let docs = if self.context7_enabled {
            self.fetch_from_context7(query).await?
        } else {
            self.fetch_basic_godot_docs(query).await?
        };

        // Cache in memory
        let mut cache = self.godot_docs_cache.lock().await;
        *cache = Some(docs.clone());

        Ok(docs)
    }

    /// Fetch from Context7 API (via configurable gateway) and merge with bundled docs
    async fn fetch_from_context7(&self, query: &str) -> Result<String> {
        // Derive a focused topic from the query
        fn derive_topic(q: &str) -> String {
            let candidates: Vec<&str> = q
                .split(|c: char| !c.is_alphanumeric() && c != '_')
                .filter(|t| !t.is_empty())
                .collect();
            if let Some(tok) = candidates
                .iter()
                .find(|t| t.chars().any(|c| c.is_uppercase()))
            {
                return (*tok).to_string();
            }
            candidates
                .iter()
                .max_by_key(|t| t.len())
                .map(|s| s.to_string())
                .unwrap_or_else(|| "Godot".to_string())
        }

        let topic = derive_topic(query);

        // Context7 gateway URL must be provided by environment (keeps runtime flexible)
        let gateway = std::env::var("CONTEXT7_GATEWAY_URL").unwrap_or_else(|_| String::new());
        let mut context7_docs: Option<String> = None;

        if !gateway.is_empty() {
            let payload = serde_json::json!({
                "context7CompatibleLibraryID": "/godotengine/godot-docs",
                "topic": topic,
                "tokens": 4000
            });

            match self.client.post(gateway).json(&payload).send().await {
                Ok(resp) => {
                    if resp.status().is_success() {
                        if let Ok(body) = resp.text().await {
                            if let Ok(v) = serde_json::from_str::<serde_json::Value>(&body) {
                                let extracted = v
                                    .get("docs")
                                    .and_then(|x| x.as_str())
                                    .or_else(|| v.get("content").and_then(|x| x.as_str()))
                                    .or_else(|| {
                                        v.get("data")
                                            .and_then(|d| d.get("content"))
                                            .and_then(|x| x.as_str())
                                    })
                                    .map(|s| s.to_string());
                                context7_docs = extracted.or_else(|| Some(v.to_string()));
                            } else {
                                context7_docs = Some(body);
                            }
                        }
                    } else {
                        eprintln!(
                            "Context7 gateway returned non-success status: {}",
                            resp.status()
                        );
                    }
                }
                Err(err) => {
                    eprintln!("Context7 gateway request failed: {}", err);
                }
            }
        }

        let context7_part = context7_docs.unwrap_or_default();
        if context7_part.trim().is_empty() {
            // If no enrichment available, return bundled quick reference only
            return Ok(BUNDLED_GODOT_DOCS.to_string());
        }

        if BUNDLED_GODOT_DOCS.contains(context7_part.trim()) {
            return Ok(BUNDLED_GODOT_DOCS.to_string());
        }

        let merged = format!(
            "{}\n\n# Context7 Enrichment (Topic: {})\n{}",
            BUNDLED_GODOT_DOCS, topic, context7_part
        );

        Ok(merged)
    }

    /// Fetch basic Godot documentation (fallback)
    async fn fetch_basic_godot_docs(&self, query: &str) -> Result<String> {
        let basic_docs = format!(
            r#"# Godot Engine Documentation (Relevant to: {})

## Common Node Types
- Node2D: Base class for 2D nodes
- CharacterBody2D: Character controller for 2D games with built-in movement
- Sprite2D: Displays a 2D texture
- CollisionShape2D: Defines collision shapes for physics
- Area2D: Detects overlapping bodies and areas
- RigidBody2D: Physics-based body with gravity and forces
- StaticBody2D: Non-moving physics body
- AnimatedSprite2D: Displays animated sprites
- Camera2D: 2D camera for viewport control

## Node3D Types
- Node3D: Base class for 3D nodes
- CharacterBody3D: Character controller for 3D games
- MeshInstance3D: Displays 3D meshes
- CollisionShape3D: 3D collision shapes
- Camera3D: 3D camera
- DirectionalLight3D: Directional lighting

## Common Properties
- position: Vector2/Vector3 - Node position
- rotation: float - Node rotation in radians
- scale: Vector2/Vector3 - Node scale
- visible: bool - Visibility state

## Input Handling
- Input.is_action_pressed(action: String) -> bool
- Input.get_vector(negative_x, positive_x, negative_y, positive_y) -> Vector2
- Input.get_axis(negative, positive) -> float

## Physics
- move_and_slide() - For CharacterBody2D/3D movement
- velocity: Vector2/Vector3 - Movement velocity
- apply_force(force: Vector2/Vector3) - Apply force to RigidBody

## Signals
- Define: signal signal_name(param1, param2)
- Emit: signal_name.emit(value1, value2)
- Connect: node.signal_name.connect(callable)

## GDScript Basics
- extends Node - Inherit from node type
- @export var name: Type - Exported variable
- func _ready() - Called when node enters scene tree
- func _process(delta) - Called every frame
- func _physics_process(delta) - Called every physics frame
"#,
            query
        );

        Ok(basic_docs)
    }

    /// Search project index for relevant information
    fn search_project_index(&self, query: &str, index: &ProjectIndex) -> String {
        let query_lower = query.to_lowercase();
        let mut context = String::new();

        context.push_str("## Existing Scenes\n");
        for scene in &index.scenes {
            if scene.name.to_lowercase().contains(&query_lower)
                || scene
                    .root_type
                    .as_ref()
                    .map(|t| t.to_lowercase().contains(&query_lower))
                    .unwrap_or(false)
            {
                context.push_str(&format!(
                    "- {} ({}): {} nodes\n",
                    scene.name,
                    scene.root_type.as_ref().unwrap_or(&"Unknown".to_string()),
                    scene.nodes.len()
                ));
            }
        }

        context.push_str("\n## Existing Scripts\n");
        for script in &index.scripts {
            if script.name.to_lowercase().contains(&query_lower)
                || script
                    .classes
                    .iter()
                    .any(|c| c.to_lowercase().contains(&query_lower))
                || script
                    .functions
                    .iter()
                    .any(|f| f.to_lowercase().contains(&query_lower))
            {
                context.push_str(&format!(
                    "- {}: {} functions, {} classes\n",
                    script.name,
                    script.functions.len(),
                    script.classes.len()
                ));
            }
        }

        context.push_str(&format!(
            "\n## Project Summary\n- Total Scenes: {}\n- Total Scripts: {}\n- Total Resources: {}\n",
            index.scenes.len(),
            index.scripts.len(),
            index.resources.len()
        ));

        context
    }
}

/// Comprehensive context structure
pub struct ComprehensiveContext {
    pub godot_docs: String,
    pub project_context: String,
    pub chat_history: String,
    pub recent_messages: Vec<(String, String)>,
    pub context_query: String,
    pub visual_analysis: Option<String>,
    pub tutorial_context: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dummy_index() -> ProjectIndex {
        ProjectIndex {
            scenes: vec![],
            scripts: vec![],
            resources: vec![],
            project_path: ".".into(),
            godot_version: None,
            godot_executable_path: None,
        }
    }

    #[tokio::test]
    async fn prefetch_caches_docs() {
        std::env::set_var("GODOTY_OFFLINE", "1");
        let engine = ContextEngine::new("test-key");
        engine.prefetch_common_godot_docs().await.unwrap();
        let docs = engine.get_cached_docs().await;
        assert!(docs.is_some());
        assert!(docs.unwrap().contains("Godot"));
    }

    #[tokio::test]
    async fn build_context_offline_uses_input_query() {
        std::env::set_var("GODOTY_OFFLINE", "1");
        let engine = ContextEngine::new("test-key");
        let ctx = engine
            .build_comprehensive_context("Create a player with movement", &dummy_index(), None, 5)
            .await
            .unwrap();
        assert!(ctx.godot_docs.len() > 10);
        assert!(ctx.project_context.contains("Total Scenes"));
        assert!(ctx.context_query.to_lowercase().contains("player"));

        let formatted = engine.format_context_for_ai(&ctx);
        assert!(formatted.contains("# Godot Documentation"));
        assert!(formatted.contains("# Current Project Context"));
    }
}
