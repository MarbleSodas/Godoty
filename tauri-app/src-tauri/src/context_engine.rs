use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use crate::project_indexer::ProjectIndex;
use crate::chat_session::{ChatSession, ChatMessage, ThoughtStep, ContextSnapshot};

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

#[derive(Deserialize)]
struct ErrorResponse {
    error: ErrorDetail,
}

#[derive(Deserialize)]
struct ErrorDetail {
    message: String,
    #[serde(rename = "type")]
    #[allow(dead_code)]
    error_type: Option<String>,
    #[allow(dead_code)]
    code: Option<String>,
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
            context7_enabled: false, // Will be enabled when Context7 API is integrated
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

        // Add chat history if available
        if !context.chat_history.is_empty() {
            formatted.push_str(&context.chat_history);
            formatted.push_str("\n\n");
        }

        formatted
    }

    /// Analyze user input to determine what context to retrieve
    async fn analyze_input_for_context(&self, user_input: &str) -> Result<String> {
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

        let response = self
            .client
            .post("https://openrouter.ai/api/v1/chat/completions")
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", "application/json")
            .header("HTTP-Referer", "https://github.com/godoty/godoty")
            .header("X-Title", "Godoty AI Assistant")
            .json(&request)
            .send()
            .await?;

        if !response.status().is_success() {
            let status = response.status();
            let error_text = response.text().await.unwrap_or_else(|_| "Unknown error".to_string());

            if let Ok(error_response) = serde_json::from_str::<ErrorResponse>(&error_text) {
                return Err(anyhow::anyhow!(
                    "OpenRouter API error ({}): {}",
                    status,
                    error_response.error.message
                ));
            }

            return Err(anyhow::anyhow!(
                "OpenRouter API request failed with status {}: {}",
                status,
                error_text
            ));
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
                if let Ok(error_response) = serde_json::from_str::<ErrorResponse>(&response_text) {
                    Err(anyhow::anyhow!(
                        "OpenRouter API error: {}",
                        error_response.error.message
                    ))
                } else {
                    Err(anyhow::anyhow!(
                        "Failed to parse API response: {}. Response: {}",
                        e,
                        &response_text[..response_text.len().min(500)]
                    ))
                }
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

    /// Fetch from Context7 API (placeholder for future implementation)
    async fn fetch_from_context7(&self, _query: &str) -> Result<String> {
        // TODO: Implement Context7 API integration
        // This would use the Context7 API to fetch relevant Godot documentation
        Err(anyhow::anyhow!("Context7 integration not yet implemented"))
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
}

