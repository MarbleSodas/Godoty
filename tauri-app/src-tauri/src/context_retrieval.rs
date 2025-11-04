use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use crate::project_indexer::ProjectIndex;

#[derive(Serialize, Deserialize)]
struct ChatMessage {
    role: String,
    content: String,
}

#[derive(Serialize)]
struct ChatRequest {
    model: String,
    messages: Vec<ChatMessage>,
    temperature: f32,
    max_tokens: i32,
}

#[derive(Deserialize)]
struct ChatResponse {
    choices: Vec<Choice>,
}

#[derive(Deserialize)]
struct Choice {
    message: ChatMessage,
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

#[derive(Clone)]
pub struct ContextRetriever {
    api_key: String,
    client: Client,
    godot_docs_cache: std::sync::Arc<tokio::sync::Mutex<Option<String>>>,
}

impl ContextRetriever {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
            godot_docs_cache: std::sync::Arc::new(tokio::sync::Mutex::new(None)),
        }
    }

    /// Load Godot docs from persistent storage if available
    pub async fn load_cached_docs(&self, cached_docs: Option<String>) -> Result<()> {
        if let Some(docs) = cached_docs {
            let mut cache = self.godot_docs_cache.lock().await;
            *cache = Some(docs);
        }
        Ok(())
    }

    /// Get cached docs for saving to persistent storage
    pub async fn get_cached_docs(&self) -> Option<String> {
        let cache = self.godot_docs_cache.lock().await;
        cache.clone()
    }

    /// Retrieve relevant context from Godot documentation and project index
    pub async fn retrieve_context(
        &self,
        user_input: &str,
        project_index: &ProjectIndex,
    ) -> Result<String> {
        // Use a free model to analyze the user input and determine what context is needed
        let context_query = self.analyze_input_for_context(user_input).await?;

        // Fetch relevant Godot documentation
        let godot_docs = self.fetch_godot_docs(&context_query).await?;

        // Search project index for relevant information
        let project_context = self.search_project_index(&context_query, project_index);

        // Combine all context
        let combined_context = format!(
            "# Godot Documentation Context\n{}\n\n# Current Project Context\n{}",
            godot_docs, project_context
        );

        Ok(combined_context)
    }

    /// Use a free model to analyze user input and determine what context to retrieve
    async fn analyze_input_for_context(&self, user_input: &str) -> Result<String> {
        let system_prompt = r#"You are a context analyzer for a Godot game development assistant.
Analyze the user's request and extract key topics, node types, and concepts that would be relevant.
Return a concise list of keywords and topics to search for in documentation and project files.

Example:
User: "Create a 2D player character with movement"
Output: CharacterBody2D, Sprite2D, Input, movement, velocity, 2D physics

User: "Add a health system to my player"
Output: health, variables, signals, UI, ProgressBar, damage system"#;

        let request = ChatRequest {
            model: "z-ai/glm-4.5-air:free".to_string(), // Free model for context analysis
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

        // Check if the response is successful
        if !response.status().is_success() {
            let status = response.status();
            let error_text = response.text().await.unwrap_or_else(|_| "Unknown error".to_string());

            // Try to parse as error response
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

        // Try to parse as successful response
        match serde_json::from_str::<ChatResponse>(&response_text) {
            Ok(chat_response) => {
                if let Some(choice) = chat_response.choices.first() {
                    Ok(choice.message.content.clone())
                } else {
                    Ok(user_input.to_string())
                }
            }
            Err(e) => {
                // If parsing as ChatResponse fails, try to parse as error
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

    /// Fetch relevant Godot documentation (with caching)
    async fn fetch_godot_docs(&self, query: &str) -> Result<String> {
        // Check in-memory cache first
        {
            let cache = self.godot_docs_cache.lock().await;
            if let Some(docs) = cache.as_ref() {
                return Ok(docs.clone());
            }
        }

        // If not in memory, fetch and cache
        let docs = self.fetch_godot_docs_from_context7(query).await?;

        // Cache in memory
        let mut cache = self.godot_docs_cache.lock().await;
        *cache = Some(docs.clone());

        Ok(docs)
    }

    /// Fetch Godot documentation from Context7 or similar service
    async fn fetch_godot_docs_from_context7(&self, query: &str) -> Result<String> {
        // This is a placeholder - in production, you would integrate with Context7 API
        // For now, we'll return a comprehensive template with common Godot concepts

        let basic_docs = format!(
            r#"# Godot Engine Documentation (Relevant to: {})

## UI/Control Nodes (for menus, HUD, UI)
- Control: Base class for all UI nodes. Use as root for UI scenes.
  * Properties: anchor_left, anchor_top, anchor_right, anchor_bottom, custom_minimum_size
  * Common children: Panel, VBoxContainer, HBoxContainer, Label, Button

- Panel: Stylized background panel for UI
  * Typical use: Background for menus, dialog boxes
  * Common children: VBoxContainer, HBoxContainer for layout

- VBoxContainer: Arranges children vertically
  * Properties: alignment (0=begin, 1=center, 2=end)
  * Common children: Label, Button, HBoxContainer

- HBoxContainer: Arranges children horizontally
  * Properties: alignment (0=begin, 1=center, 2=end)
  * Common children: Label, Button, TextureRect

- Label: Displays text
  * Properties: text (string), horizontal_alignment, vertical_alignment

- Button: Clickable button
  * Properties: text (string)
  * Signals: pressed()

- HSlider/VSlider: Slider controls
  * Properties: min_value, max_value, value, step
  * Signals: value_changed(value)

- ProgressBar: Progress indicator
  * Properties: min_value, max_value, value

- MarginContainer: Adds margins around children
  * Properties: theme_override_constants/margin_left, margin_top, margin_right, margin_bottom

## 2D Gameplay Nodes
- Node2D: Base class for 2D nodes. Use as root for 2D game scenes.
  * Properties: position (Vector2), rotation (float), scale (Vector2)

- CharacterBody2D: Character controller with built-in movement
  * Properties: velocity (Vector2), motion_mode, up_direction
  * Methods: move_and_slide(), is_on_floor(), is_on_wall()
  * Typical children: Sprite2D, CollisionShape2D, Camera2D
  * Common use: Player, enemies, NPCs

- Sprite2D: Displays a 2D texture
  * Properties: texture (Texture2D), centered (bool), offset (Vector2)
  * Common use: Character sprites, objects, backgrounds

- AnimatedSprite2D: Displays animated sprites
  * Properties: sprite_frames (SpriteFrames), animation (string), frame (int)
  * Methods: play(animation), stop()

- CollisionShape2D: Defines collision shape for physics
  * Properties: shape (Shape2D) - RectangleShape2D, CircleShape2D, CapsuleShape2D
  * Must be child of physics body (CharacterBody2D, Area2D, RigidBody2D)

- Area2D: Detects overlapping bodies and areas
  * Signals: body_entered(body), body_exited(body), area_entered(area)
  * Common use: Triggers, pickups, damage zones, detection areas
  * Typical children: CollisionShape2D, Sprite2D

- RigidBody2D: Physics-based body with gravity
  * Properties: mass, gravity_scale, linear_velocity
  * Methods: apply_force(force), apply_impulse(impulse)

- StaticBody2D: Non-moving physics body
  * Common use: Walls, platforms, obstacles
  * Typical children: CollisionShape2D, Sprite2D

- Camera2D: 2D camera for viewport control
  * Properties: zoom (Vector2), offset (Vector2), enabled (bool)
  * Common use: Follow player, cutscenes

- TileMap: Grid-based tile system
  * Properties: tile_set (TileSet)
  * Common use: Levels, backgrounds, terrain

## 3D Gameplay Nodes
- Node3D: Base class for 3D nodes. Use as root for 3D game scenes.
  * Properties: position (Vector3), rotation (Vector3), scale (Vector3)

- CharacterBody3D: 3D character controller
  * Properties: velocity (Vector3), motion_mode, up_direction
  * Methods: move_and_slide(), is_on_floor(), is_on_wall()
  * Typical children: MeshInstance3D, CollisionShape3D, Camera3D

- MeshInstance3D: Displays 3D meshes
  * Properties: mesh (Mesh), material_override (Material)

- CollisionShape3D: 3D collision shapes
  * Properties: shape (Shape3D) - BoxShape3D, SphereShape3D, CapsuleShape3D

- Camera3D: 3D camera
  * Properties: fov, near, far, current (bool)

- DirectionalLight3D: Directional lighting (sun)
  * Properties: light_energy, light_color

- OmniLight3D: Point light source
  * Properties: omni_range, light_energy

## Node Hierarchy Best Practices
1. UI Scenes: Control (root) > Panel/MarginContainer > VBoxContainer/HBoxContainer > Widgets
2. 2D Player: CharacterBody2D (root) > Sprite2D + CollisionShape2D + Camera2D
3. 2D Enemy: CharacterBody2D (root) > AnimatedSprite2D + CollisionShape2D + Area2D (detection)
4. Pickup Item: Area2D (root) > Sprite2D + CollisionShape2D
5. 3D Player: CharacterBody3D (root) > MeshInstance3D + CollisionShape3D + Camera3D

## Input Handling
- Input.is_action_pressed(action: String) -> bool
- Input.is_action_just_pressed(action: String) -> bool
- Input.get_vector(negative_x, positive_x, negative_y, positive_y) -> Vector2
- Input.get_axis(negative, positive) -> float

## Physics & Movement
- move_and_slide() - For CharacterBody2D/3D movement (call in _physics_process)
- velocity: Vector2/Vector3 - Movement velocity
- apply_force(force: Vector2/Vector3) - Apply force to RigidBody
- is_on_floor() -> bool - Check if character is on ground
- is_on_wall() -> bool - Check if character is touching wall

## Signals
- Define: signal signal_name(param1, param2)
- Emit: signal_name.emit(value1, value2)
- Connect: node.signal_name.connect(callable)
- Common signals: pressed(), body_entered(body), value_changed(value)

## GDScript Basics
- extends Node - Inherit from node type
- @export var name: Type - Exported variable (visible in inspector)
- func _ready() - Called when node enters scene tree (initialization)
- func _process(delta) - Called every frame (visual updates)
- func _physics_process(delta) - Called every physics frame (movement, physics)
- get_node("NodePath") or $NodePath - Get reference to node
- queue_free() - Delete node

## Common Patterns
### Player Movement (2D):
```gdscript
extends CharacterBody2D

@export var speed = 300.0
@export var jump_velocity = -400.0

func _physics_process(delta):
    if not is_on_floor():
        velocity.y += gravity * delta

    if Input.is_action_just_pressed("jump") and is_on_floor():
        velocity.y = jump_velocity

    var direction = Input.get_axis("move_left", "move_right")
    velocity.x = direction * speed

    move_and_slide()
```

### Health System:
```gdscript
extends Node

signal health_changed(new_health)
signal died()

@export var max_health = 100
var current_health = max_health

func take_damage(amount):
    current_health -= amount
    health_changed.emit(current_health)
    if current_health <= 0:
        died.emit()

func heal(amount):
    current_health = min(current_health + amount, max_health)
    health_changed.emit(current_health)
```
"#,
            query
        );

        Ok(basic_docs)
    }

    /// Search project index for relevant information
    fn search_project_index(&self, query: &str, index: &ProjectIndex) -> String {
        let query_lower = query.to_lowercase();
        let mut context = String::new();

        // Categorize scenes by type
        let mut ui_scenes = Vec::new();
        let mut gameplay_scenes = Vec::new();
        let mut other_scenes = Vec::new();

        for scene in &index.scenes {
            if let Some(root_type) = &scene.root_type {
                if root_type.contains("Control") || root_type.contains("Panel") || root_type.contains("Container") {
                    ui_scenes.push(scene);
                } else if root_type.contains("Node2D") || root_type.contains("Node3D") || root_type.contains("CharacterBody") {
                    gameplay_scenes.push(scene);
                } else {
                    other_scenes.push(scene);
                }
            } else {
                other_scenes.push(scene);
            }
        }

        // Provide detailed scene hierarchies for relevant scenes
        context.push_str("## Existing Scene Structures\n\n");

        // Show UI scene examples
        if !ui_scenes.is_empty() {
            context.push_str("### UI Scenes (use these as reference for UI elements)\n");
            for scene in ui_scenes.iter().take(3) {
                context.push_str(&format!("**{}** (Root: {})\n",
                    scene.name,
                    scene.root_type.as_ref().unwrap_or(&"Unknown".to_string())
                ));
                context.push_str("Node Hierarchy:\n");
                for node in &scene.nodes {
                    let indent = node.path.matches('/').count();
                    context.push_str(&format!("{}├─ {} ({})\n",
                        "  ".repeat(indent),
                        node.name,
                        node.node_type
                    ));
                }
                context.push_str("\n");
            }
        }

        // Show gameplay scene examples
        if !gameplay_scenes.is_empty() {
            context.push_str("### Gameplay Scenes (use these as reference for game objects)\n");
            for scene in gameplay_scenes.iter().take(3) {
                context.push_str(&format!("**{}** (Root: {})\n",
                    scene.name,
                    scene.root_type.as_ref().unwrap_or(&"Unknown".to_string())
                ));
                context.push_str("Node Hierarchy:\n");
                for node in &scene.nodes {
                    let indent = node.path.matches('/').count();
                    context.push_str(&format!("{}├─ {} ({})\n",
                        "  ".repeat(indent),
                        node.name,
                        node.node_type
                    ));
                }
                context.push_str("\n");
            }
        }

        // Search for relevant scenes based on query
        context.push_str("### Scenes Matching Your Query\n");
        let mut found_relevant = false;
        for scene in &index.scenes {
            if scene.name.to_lowercase().contains(&query_lower)
                || scene
                    .root_type
                    .as_ref()
                    .map(|t| t.to_lowercase().contains(&query_lower))
                    .unwrap_or(false)
                || scene.nodes.iter().any(|n|
                    n.name.to_lowercase().contains(&query_lower) ||
                    n.node_type.to_lowercase().contains(&query_lower)
                )
            {
                found_relevant = true;
                context.push_str(&format!("**{}** (Root: {})\n",
                    scene.name,
                    scene.root_type.as_ref().unwrap_or(&"Unknown".to_string())
                ));
                context.push_str("Node Hierarchy:\n");
                for node in &scene.nodes {
                    let indent = node.path.matches('/').count();
                    context.push_str(&format!("{}├─ {} ({})\n",
                        "  ".repeat(indent),
                        node.name,
                        node.node_type
                    ));
                }
                context.push_str("\n");
            }
        }
        if !found_relevant {
            context.push_str("No existing scenes match your query.\n\n");
        }

        // Search scripts
        context.push_str("## Existing Scripts\n");
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
                if !script.functions.is_empty() {
                    context.push_str(&format!("  Functions: {}\n", script.functions.join(", ")));
                }
            }
        }

        // Search resources
        context.push_str("\n## Existing Resources\n");
        for resource in &index.resources {
            if resource.name.to_lowercase().contains(&query_lower)
                || resource.resource_type.to_lowercase().contains(&query_lower)
            {
                context.push_str(&format!(
                    "- {} ({})\n",
                    resource.name, resource.resource_type
                ));
            }
        }

        // Add project summary
        context.push_str(&format!(
            "\n## Project Summary\n- Total Scenes: {}\n- Total Scripts: {}\n- Total Resources: {}\n",
            index.scenes.len(),
            index.scripts.len(),
            index.resources.len()
        ));

        context
    }
}

