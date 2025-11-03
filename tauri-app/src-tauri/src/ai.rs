use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use reqwest::Client;

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
}

#[derive(Deserialize)]
struct ChatResponse {
    choices: Vec<Choice>,
}

#[derive(Deserialize)]
struct Choice {
    message: ChatMessage,
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
    
    pub async fn process_input(&self, input: &str) -> Result<Vec<Value>> {
        let system_prompt = r#"You are an AI assistant that helps users create game elements in Godot.
Your task is to convert natural language descriptions into a series of JSON commands that can be executed by the Godot editor.

Available commands:
1. create_node: Creates a new node
   {"action": "create_node", "type": "NodeType", "name": "NodeName", "parent": "ParentPath or null", "properties": {}}

2. modify_node: Modifies an existing node
   {"action": "modify_node", "path": "NodePath", "properties": {}}

3. attach_script: Attaches a script to a node
   {"action": "attach_script", "path": "NodePath", "script_content": "GDScript code", "script_path": "optional/path.gd"}

4. create_scene: Creates a new scene
   {"action": "create_scene", "name": "SceneName", "root_type": "NodeType", "save_path": "optional/path.tscn"}

Common Godot node types:
- Node, Node2D, Node3D
- CharacterBody2D, CharacterBody3D
- Sprite2D, Sprite3D
- CollisionShape2D, CollisionShape3D
- Area2D, Area3D
- Camera2D, Camera3D
- Control, Label, Button

Respond ONLY with a JSON array of commands. No explanations, just the JSON array.

Example input: "Add a 2D player character with a sprite and collision shape"
Example output: [
  {"action": "create_node", "type": "CharacterBody2D", "name": "Player", "parent": null, "properties": {}},
  {"action": "create_node", "type": "Sprite2D", "name": "Sprite", "parent": "Player", "properties": {}},
  {"action": "create_node", "type": "CollisionShape2D", "name": "CollisionShape", "parent": "Player", "properties": {}}
]"#;

        let request = ChatRequest {
            model: "openai/gpt-4".to_string(),
            messages: vec![
                ChatMessage {
                    role: "system".to_string(),
                    content: system_prompt.to_string(),
                },
                ChatMessage {
                    role: "user".to_string(),
                    content: input.to_string(),
                },
            ],
            temperature: 0.7,
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
        
        let chat_response: ChatResponse = response.json().await?;
        
        if let Some(choice) = chat_response.choices.first() {
            let content = &choice.message.content;
            
            // Parse the JSON array from the response
            let commands: Vec<Value> = serde_json::from_str(content.trim())?;
            
            Ok(commands)
        } else {
            Err(anyhow::anyhow!("No response from AI"))
        }
    }
}

