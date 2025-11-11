use crate::knowledge_base::KnowledgeBase;
use anyhow::Result;
use std::collections::HashMap;
use std::path::PathBuf;

/// Manages the two knowledge bases: Plugin Tools & API, and Official Documentation
pub struct KnowledgeManager {
    plugin_kb: KnowledgeBase,
    docs_kb: KnowledgeBase,
    storage_dir: PathBuf,
}

impl KnowledgeManager {
    /// Create a new knowledge manager
    pub fn new(storage_dir: PathBuf) -> Result<Self> {
        Ok(Self {
            plugin_kb: KnowledgeBase::new("plugin_tools")?,
            docs_kb: KnowledgeBase::new("godot_docs")?,
            storage_dir,
        })
    }

    /// Initialize knowledge bases (load from disk or populate if empty)
    pub async fn initialize(&self) -> Result<()> {
        // Try to load from disk first
        let _ = self.plugin_kb.load_from_disk(&self.storage_dir).await;
        let _ = self.docs_kb.load_from_disk(&self.storage_dir).await;

        // If plugin KB is empty, populate it
        if self.plugin_kb.count().await == 0 {
            self.populate_plugin_kb().await?;
            self.plugin_kb.save_to_disk(&self.storage_dir).await?;
        }

        // If docs KB is empty, populate it
        if self.docs_kb.count().await == 0 {
            self.populate_docs_kb().await?;
            self.docs_kb.save_to_disk(&self.storage_dir).await?;
        }

        Ok(())
    }

    /// Get the plugin knowledge base
    pub fn get_plugin_kb(&self) -> KnowledgeBase {
        self.plugin_kb.clone()
    }

    /// Get the documentation knowledge base
    pub fn get_docs_kb(&self) -> KnowledgeBase {
        self.docs_kb.clone()
    }

    /// Rebuild the documentation knowledge base
    pub async fn rebuild_docs_kb(&self) -> Result<()> {
        // Clear existing documents
        self.docs_kb.clear().await?;

        // Repopulate
        self.populate_docs_kb().await?;

        // Save to disk
        self.docs_kb.save_to_disk(&self.storage_dir).await?;

        Ok(())
    }

    /// Rebuild the plugin knowledge base
    pub async fn rebuild_plugin_kb(&self) -> Result<()> {
        // Clear existing documents
        self.plugin_kb.clear().await?;

        // Repopulate
        self.populate_plugin_kb().await?;

        // Save to disk
        self.plugin_kb.save_to_disk(&self.storage_dir).await?;

        Ok(())
    }

    /// Populate the plugin tools & API knowledge base
    async fn populate_plugin_kb(&self) -> Result<()> {
        // Add command documentation
        let commands = vec![
            (
                "create_scene",
                r#"Create a new scene in Godot.
Command: {"action": "create_scene", "name": "SceneName", "root_type": "NodeType", "save_path": "res://path.tscn"}
Parameters:
- name: Name of the scene (required)
- root_type: Type of root node (e.g., "Node2D", "Control", "Node3D") (required)
- save_path: Path where scene will be saved (required)
Example: {"action": "create_scene", "name": "MainMenu", "root_type": "Control", "save_path": "res://MainMenu.tscn"}
Use case: Starting a new scene, creating UI menus, creating game levels"#,
            ),
            (
                "create_node",
                r#"Create a node in the current scene.
Command: {"action": "create_node", "type": "NodeType", "name": "NodeName", "parent": "ParentPath", "properties": {}}
Parameters:
- type: Godot node type (e.g., "Sprite2D", "Label", "CharacterBody2D") (required)
- name: Name for the node (required)
- parent: Path to parent node or null for root (required)
- properties: Dictionary of properties to set (optional)
Example: {"action": "create_node", "type": "Sprite2D", "name": "PlayerSprite", "parent": "Player", "properties": {}}
Use case: Adding nodes to scene hierarchy, building game objects"#,
            ),
            (
                "modify_node",
                r#"Modify properties of an existing node.
Command: {"action": "modify_node", "path": "NodePath", "properties": {"property": "value"}}
Parameters:
- path: Path to the node (required)
- properties: Dictionary of properties to modify (required)
Example: {"action": "modify_node", "path": "Player/Sprite", "properties": {"position": {"x": 100, "y": 200}}}
Use case: Changing node properties, positioning, scaling, configuring"#,
            ),
            (
                "attach_script",
                r#"Attach a GDScript to a node.
Command: {"action": "attach_script", "path": "NodePath", "script_content": "extends Node\n...", "script_path": "res://script.gd"}
Parameters:
- path: Path to the node (required)
- script_content: GDScript code content (required)
- script_path: Path where script will be saved (optional)
Example: {"action": "attach_script", "path": "Player", "script_content": "extends CharacterBody2D\n\nfunc _ready():\n\tpass", "script_path": "res://player.gd"}
Use case: Adding behavior to nodes, implementing game logic"#,
            ),
            (
                "get_scene_info",
                r#"Get information about the current scene.
Command: {"action": "get_scene_info"}
Returns: Scene tree structure with node names, types, and paths
Use case: Understanding current scene structure, debugging, planning modifications"#,
            ),
            (
                "search_nodes_by_type",
                r#"Search for nodes by their type.
Command: {"action": "search_nodes_by_type", "type": "NodeType", "select_results": false, "focus_first": false}
Parameters:
- type: Node type to search for (required)
- select_results: Whether to select found nodes (optional, default: false)
- focus_first: Whether to focus on first result (optional, default: false)
Example: {"action": "search_nodes_by_type", "type": "Sprite2D", "select_results": true}
Use case: Finding all nodes of a specific type, batch operations"#,
            ),
            (
                "play",
                r#"Run the game in Godot editor.
Command: {"action": "play", "mode": "current|main|custom", "path": "res://scene.tscn"}
Parameters:
- mode: Play mode - "current" (current scene), "main" (main scene), or "custom" (specific scene) (required)
- path: Path to scene (required only for "custom" mode)
Example: {"action": "play", "mode": "current"}
Use case: Testing the game, running scenes"#,
            ),
        ];

        for (id, content) in commands {
            let mut metadata = HashMap::new();
            metadata.insert("type".to_string(), "command".to_string());
            metadata.insert("category".to_string(), "plugin_api".to_string());

            self.plugin_kb
                .add_document(id.to_string(), content.to_string(), metadata)
                .await?;
        }

        Ok(())
    }

    /// Populate the Godot documentation knowledge base
    async fn populate_docs_kb(&self) -> Result<()> {
        // Add core Godot documentation
        let docs = vec![
            (
                "node2d_overview",
                r#"Node2D is the base class for all 2D nodes in Godot.
It provides position, rotation, and scale properties for 2D transformations.
Common child classes: Sprite2D, AnimatedSprite2D, CollisionShape2D, Area2D, CharacterBody2D, RigidBody2D.
Properties: position (Vector2), rotation (float), scale (Vector2), z_index (int).
Use Node2D as the root for 2D game scenes."#,
            ),
            (
                "characterbody2d",
                r#"CharacterBody2D is used for player-controlled or AI-controlled characters in 2D games.
It provides built-in movement with collision detection via move_and_slide().
Properties: velocity (Vector2), motion_mode, up_direction.
Methods: move_and_slide() - moves the body and handles collisions.
Example usage: Player characters, enemies, NPCs with custom movement logic."#,
            ),
            (
                "control_nodes",
                r#"Control is the base class for all UI nodes in Godot.
Common Control nodes: Button, Label, Panel, Container nodes (VBoxContainer, HBoxContainer, MarginContainer).
Properties: anchor_left, anchor_right, anchor_top, anchor_bottom for positioning.
Use Control as root for UI scenes like menus, HUDs, dialogs.
Container nodes automatically arrange their children."#,
            ),
            (
                "sprite2d",
                r#"Sprite2D displays a 2D texture/image.
Properties: texture (Texture2D), centered (bool), offset (Vector2), flip_h, flip_v.
Use for displaying game graphics, character sprites, backgrounds.
Can be animated by changing the texture or using region_rect for sprite sheets."#,
            ),
            (
                "signals",
                r#"Signals are Godot's implementation of the observer pattern for event handling.
Define: signal signal_name(param1, param2)
Emit: signal_name.emit(value1, value2)
Connect: node.signal_name.connect(callable)
Example: signal health_changed(new_health)
Common built-in signals: pressed (Button), body_entered (Area2D), timeout (Timer)"#,
            ),
            (
                "gdscript_basics",
                r#"GDScript is Godot's built-in scripting language.
Key concepts:
- extends NodeType - inherit from a node class
- @export var name: Type - expose variable to editor
- func _ready() - called when node enters scene tree
- func _process(delta) - called every frame
- func _physics_process(delta) - called every physics frame (60 FPS)
Variables: var name = value or var name: Type = value
Functions: func function_name(param: Type) -> ReturnType:"#,
            ),
        ];

        for (id, content) in docs {
            let mut metadata = HashMap::new();
            metadata.insert("type".to_string(), "documentation".to_string());
            metadata.insert("source".to_string(), "godot_official".to_string());

            self.docs_kb
                .add_document(id.to_string(), content.to_string(), metadata)
                .await?;
        }

        Ok(())
    }

}
