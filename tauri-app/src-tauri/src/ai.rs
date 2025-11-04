use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use reqwest::Client;
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
    max_tokens: Option<i32>,
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
pub struct AIProcessor {
    api_key: String,
    client: Client,
}

impl AIProcessor {
    pub fn new(api_key: &str) -> Self {
        Self {
            api_key: api_key.to_string(),
            client: Client::new(),
        }
    }

    pub async fn process_input(&self, input: &str, context: &str, project_index: &ProjectIndex) -> Result<Vec<Value>> {
        let system_prompt = format!(r#"You are an AI assistant that helps users create game elements in Godot.
Your task is to convert natural language descriptions into a series of JSON commands that can be executed by the Godot editor.

You have access to the following context:
{}

Current Project Information:
- Total Scenes: {}
- Total Scripts: {}
- Total Resources: {}

Available commands:
1. create_node: Creates a new node (requires a scene to be open)
   {{"action": "create_node", "type": "NodeType", "name": "NodeName", "parent": "ParentPath or null", "properties": {{}}}}

2. modify_node: Modifies an existing node (requires a scene to be open)
   {{"action": "modify_node", "path": "NodePath", "properties": {{}}}}

3. attach_script: Attaches a script to a node (requires a scene to be open)
   {{"action": "attach_script", "path": "NodePath", "script_content": "GDScript code", "script_path": "optional/path.gd"}}

4. create_scene: Creates a new scene and opens it in the editor
   {{"action": "create_scene", "name": "SceneName", "root_type": "NodeType", "save_path": "res://path.tscn"}}

5. get_scene_info: Gets information about the currently open scene
   {{"action": "get_scene_info"}}

CRITICAL WORKFLOW RULES:
1. ALWAYS create parent nodes BEFORE child nodes
2. Parent paths use forward slashes: "Parent/Child/GrandChild"
3. When creating a new scene, FIRST use create_scene, THEN create_node for children
4. The root node name from create_scene is used as the parent for first-level children
5. For nested nodes, build the path incrementally: create "A", then "A/B", then "A/B/C"

COMMON NODE PATTERNS:

UI Scenes (use Control as root):
- Main Menu: Control > Panel (background) > VBoxContainer > Buttons
- Settings Menu: Control > Panel > VBoxContainer > (Label + HSlider) pairs
- HUD: Control > MarginContainer > VBoxContainer > Labels/ProgressBars
- Pause Menu: Control > ColorRect (overlay) > Panel > VBoxContainer > Buttons

Gameplay Scenes (use Node2D/Node3D as root):
- Player: CharacterBody2D > Sprite2D + CollisionShape2D + Camera2D
- Enemy: CharacterBody2D > AnimatedSprite2D + CollisionShape2D + Area2D (detection)
- Projectile: Area2D > Sprite2D + CollisionShape2D
- Level: Node2D > TileMap + StaticBody2D (walls) + Area2D (triggers)

3D Gameplay:
- Player: CharacterBody3D > MeshInstance3D + CollisionShape3D + Camera3D
- Enemy: CharacterBody3D > MeshInstance3D + CollisionShape3D + NavigationAgent3D

PARENT PATH SYNTAX:
- Root node: parent is the scene name (e.g., "MainMenu")
- First child: parent is scene name (e.g., "MainMenu")
- Nested child: parent is full path (e.g., "MainMenu/Container")
- Deep nesting: "MainMenu/Container/SubContainer/Button"

COMMON PROPERTIES:
- Label: {{"text": "Hello World"}}
- Button: {{"text": "Click Me"}}
- Sprite2D: {{"texture": "res://icon.png"}} (if texture exists)
- Panel: {{"custom_minimum_size": {{"x": 200, "y": 300}}}}
- VBoxContainer: {{"alignment": 1}} (center)
- Control: {{"anchor_right": 1.0, "anchor_bottom": 1.0}} (fill parent)

Respond ONLY with a JSON array of commands. No explanations, just the JSON array.

EXAMPLE 1 - Main Menu Scene:
Input: "Create a main menu scene"
Output: [
  {{"action": "create_scene", "name": "MainMenu", "root_type": "Control", "save_path": "res://MainMenu.tscn"}},
  {{"action": "create_node", "type": "Panel", "name": "Background", "parent": "MainMenu", "properties": {{}}}},
  {{"action": "create_node", "type": "VBoxContainer", "name": "MenuContainer", "parent": "MainMenu", "properties": {{"alignment": 1}}}},
  {{"action": "create_node", "type": "Label", "name": "Title", "parent": "MainMenu/MenuContainer", "properties": {{"text": "My Game"}}}},
  {{"action": "create_node", "type": "Button", "name": "PlayButton", "parent": "MainMenu/MenuContainer", "properties": {{"text": "Play"}}}},
  {{"action": "create_node", "type": "Button", "name": "SettingsButton", "parent": "MainMenu/MenuContainer", "properties": {{"text": "Settings"}}}},
  {{"action": "create_node", "type": "Button", "name": "QuitButton", "parent": "MainMenu/MenuContainer", "properties": {{"text": "Quit"}}}}
]

EXAMPLE 2 - Player Character:
Input: "Create a 2D player character"
Output: [
  {{"action": "create_scene", "name": "Player", "root_type": "CharacterBody2D", "save_path": "res://Player.tscn"}},
  {{"action": "create_node", "type": "Sprite2D", "name": "Sprite", "parent": "Player", "properties": {{}}}},
  {{"action": "create_node", "type": "CollisionShape2D", "name": "CollisionShape", "parent": "Player", "properties": {{}}}},
  {{"action": "create_node", "type": "Camera2D", "name": "Camera", "parent": "Player", "properties": {{}}}}
]

EXAMPLE 3 - Error Recovery (missing scene):
Input: "The previous attempt failed with: Command 1: create_node - Error: No scene is currently open"
Output: [
  {{"action": "create_scene", "name": "NewScene", "root_type": "Node2D", "save_path": "res://NewScene.tscn"}},
  {{"action": "create_node", "type": "Sprite2D", "name": "Sprite", "parent": "NewScene", "properties": {{}}}}
]

EXAMPLE 4 - Error Recovery (missing parent):
Input: "The previous attempt failed with: Command 2: create_node - Error: Parent node not found: MainMenu/MenuContainer"
Output: [
  {{"action": "create_node", "type": "VBoxContainer", "name": "MenuContainer", "parent": "MainMenu", "properties": {{}}}},
  {{"action": "create_node", "type": "Label", "name": "TitleLabel", "parent": "MainMenu/MenuContainer", "properties": {{"text": "Game Title"}}}}
]

EXAMPLE 5 - Complex Nested Structure:
Input: "Create a settings menu with volume sliders"
Output: [
  {{"action": "create_scene", "name": "SettingsMenu", "root_type": "Control", "save_path": "res://SettingsMenu.tscn"}},
  {{"action": "create_node", "type": "Panel", "name": "Background", "parent": "SettingsMenu", "properties": {{}}}},
  {{"action": "create_node", "type": "VBoxContainer", "name": "SettingsContainer", "parent": "SettingsMenu", "properties": {{"alignment": 1}}}},
  {{"action": "create_node", "type": "Label", "name": "Title", "parent": "SettingsMenu/SettingsContainer", "properties": {{"text": "Settings"}}}},
  {{"action": "create_node", "type": "HBoxContainer", "name": "MasterVolumeRow", "parent": "SettingsMenu/SettingsContainer", "properties": {{}}}},
  {{"action": "create_node", "type": "Label", "name": "MasterLabel", "parent": "SettingsMenu/SettingsContainer/MasterVolumeRow", "properties": {{"text": "Master Volume"}}}},
  {{"action": "create_node", "type": "HSlider", "name": "MasterSlider", "parent": "SettingsMenu/SettingsContainer/MasterVolumeRow", "properties": {{"min_value": 0, "max_value": 100, "value": 100}}}},
  {{"action": "create_node", "type": "HBoxContainer", "name": "MusicVolumeRow", "parent": "SettingsMenu/SettingsContainer", "properties": {{}}}},
  {{"action": "create_node", "type": "Label", "name": "MusicLabel", "parent": "SettingsMenu/SettingsContainer/MusicVolumeRow", "properties": {{"text": "Music Volume"}}}},
  {{"action": "create_node", "type": "HSlider", "name": "MusicSlider", "parent": "SettingsMenu/SettingsContainer/MusicVolumeRow", "properties": {{"min_value": 0, "max_value": 100, "value": 80}}}},
  {{"action": "create_node", "type": "Button", "name": "BackButton", "parent": "SettingsMenu/SettingsContainer", "properties": {{"text": "Back"}}}}
]

Remember: Look at the existing scene structures in the context to match the project's style and patterns!"#,
            context,
            project_index.scenes.len(),
            project_index.scripts.len(),
            project_index.resources.len()
        );

        let request = ChatRequest {
            model: "minimax/minimax-m2:free".to_string(),
            messages: vec![
                ChatMessage {
                    role: "system".to_string(),
                    content: system_prompt,
                },
                ChatMessage {
                    role: "user".to_string(),
                    content: input.to_string(),
                },
            ],
            temperature: 0.7,
            max_tokens: Some(4096),
        };

        let response = self.client
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
                    let content = &choice.message.content;

                    // Extract JSON from the response (handle markdown code blocks)
                    let json_content = Self::extract_json(content)
                        .map_err(|e| anyhow::anyhow!("Failed to extract JSON from AI response: {}", e))?;

                    // Parse the JSON array from the response
                    let commands: Vec<Value> = serde_json::from_str(&json_content)
                        .map_err(|e| anyhow::anyhow!(
                            "Failed to parse JSON commands: {}. Content: {}",
                            e,
                            &json_content[..json_content.len().min(200)]
                        ))?;

                    Ok(commands)
                } else {
                    Err(anyhow::anyhow!("No response from AI"))
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

    /// Extract JSON from AI response, handling markdown code blocks and extra text
    fn extract_json(content: &str) -> Result<String> {
        let trimmed = content.trim();

        // Check if content is wrapped in markdown code blocks
        if let Some(start) = trimmed.find("```json") {
            let json_start = start + 7; // Length of "```json"
            // Find the closing ``` after the opening ```json
            if let Some(end_offset) = trimmed[json_start..].find("```") {
                let json_end = json_start + end_offset;
                return Ok(trimmed[json_start..json_end].trim().to_string());
            }
        }

        // Check for generic code blocks
        if let Some(start) = trimmed.find("```") {
            let first_block_start = start + 3;
            if let Some(end) = trimmed[first_block_start..].find("```") {
                let json_end = first_block_start + end;
                return Ok(trimmed[first_block_start..json_end].trim().to_string());
            }
        }

        // Try to find JSON array or object boundaries
        if let Some(array_start) = trimmed.find('[') {
            if let Some(array_end) = trimmed.rfind(']') {
                if array_end > array_start {
                    return Ok(trimmed[array_start..=array_end].to_string());
                }
            }
        }

        // If no special formatting found, return as-is
        Ok(trimmed.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_json_from_markdown_json_block() {
        let content = r#"Here are the commands:
```json
[{"action": "create_node"}]
```"#;
        let result = AIProcessor::extract_json(content).unwrap();
        assert_eq!(result, r#"[{"action": "create_node"}]"#);
    }

    #[test]
    fn test_extract_json_from_generic_code_block() {
        let content = r#"```
[{"action": "create_node"}]
```"#;
        let result = AIProcessor::extract_json(content).unwrap();
        assert_eq!(result, r#"[{"action": "create_node"}]"#);
    }

    #[test]
    fn test_extract_json_from_plain_array() {
        let content = r#"Some text before [{"action": "create_node"}] some text after"#;
        let result = AIProcessor::extract_json(content).unwrap();
        assert_eq!(result, r#"[{"action": "create_node"}]"#);
    }

    #[test]
    fn test_extract_json_from_plain_json() {
        let content = r#"[{"action": "create_node"}]"#;
        let result = AIProcessor::extract_json(content).unwrap();
        assert_eq!(result, r#"[{"action": "create_node"}]"#);
    }

    #[test]
    fn test_extract_json_with_whitespace() {
        let content = r#"

        [{"action": "create_node"}]

        "#;
        let result = AIProcessor::extract_json(content).unwrap();
        assert_eq!(result, r#"[{"action": "create_node"}]"#);
    }
}
