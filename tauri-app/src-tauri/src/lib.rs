use std::sync::{Arc, Mutex};
use tauri::State;
use serde_json::Value;

mod websocket;
mod ai;
mod storage;
mod project_indexer;
mod chat_session;
mod context_engine;
mod tscn_utils;

use websocket::WebSocketClient;
use ai::AIProcessor;
use storage::Storage;
use project_indexer::{ProjectIndexer, ProjectIndex};
use chat_session::{ChatSessionManager, ChatMessage, ContextSnapshot};
use context_engine::ContextEngine;

#[derive(Clone)]
struct AppState {
    ws_client: Arc<Mutex<Option<WebSocketClient>>>,
    ai_processor: Arc<Mutex<Option<AIProcessor>>>,
    context_engine: Arc<Mutex<Option<ContextEngine>>>,
    chat_session_manager: Arc<Mutex<ChatSessionManager>>,
    storage: Arc<Mutex<Storage>>,
    project_index: Arc<Mutex<Option<ProjectIndex>>>,
    godot_project_path: Arc<Mutex<Option<String>>>,
}

impl Default for AppState {
    fn default() -> Self {
        let storage = Storage::default();
        let project_path = storage.get_project_path();

        // Load chat sessions from storage
        let mut session_manager = ChatSessionManager::new();
        if let Ok(sessions) = storage.load_chat_sessions() {
            session_manager.load_sessions(sessions);
        }

        Self {
            ws_client: Arc::new(Mutex::new(None)),
            ai_processor: Arc::new(Mutex::new(None)),
            context_engine: Arc::new(Mutex::new(None)),
            chat_session_manager: Arc::new(Mutex::new(session_manager)),
            storage: Arc::new(Mutex::new(storage)),
            project_index: Arc::new(Mutex::new(None)),
            godot_project_path: Arc::new(Mutex::new(project_path)),
        }
    }
}

#[tauri::command]
async fn connect_to_godot(state: State<'_, AppState>) -> Result<String, String> {
    match WebSocketClient::connect("ws://127.0.0.1:9001").await {
        Ok(client) => {
            let mut ws_client = state.ws_client.lock().unwrap();
            *ws_client = Some(client);
            Ok("Connected to Godot".to_string())
        }
        Err(e) => Err(format!("Failed to connect: {}", e))
    }
}

#[tauri::command]
async fn set_godot_project_path(path: String, state: State<'_, AppState>) -> Result<(), String> {
    // Save the project path to persistent storage
    {
        let mut storage = state.storage.lock().unwrap();
        storage.save_project_path(&path)
            .map_err(|e| format!("Failed to save project path: {}", e))?;
    }

    // Set the project path in memory
    {
        let mut project_path = state.godot_project_path.lock().unwrap();
        *project_path = Some(path.clone());
    }

    // Trigger background indexing
    let state_clone = state.inner().clone();
    let path_clone = path.clone();

    tokio::spawn(async move {
        // Index the project in the background
        let indexer = ProjectIndexer::new(&path_clone);
        if let Ok(project_index) = indexer.index_project() {
            // Cache in memory
            {
                let mut cached_index = state_clone.project_index.lock().unwrap();
                *cached_index = Some(project_index.clone());
            }

            // Save to persistent storage
            {
                let storage = state_clone.storage.lock().unwrap();
                let _ = storage.save_project_index(&project_index, &path_clone);
            }

            println!("Background indexing completed: {} scenes, {} scripts, {} resources",
                project_index.scenes.len(),
                project_index.scripts.len(),
                project_index.resources.len()
            );

            // Proactively prefetch Godot docs and cache them
            let api_key_opt = {
                let storage = state_clone.storage.lock().unwrap();
                storage.get_api_key()
            };
            if let Some(api_key) = api_key_opt {
                let engine = ContextEngine::new(&api_key);
                // Load any cached docs first
                let cached_docs = {
                    let storage = state_clone.storage.lock().unwrap();
                    if storage.is_godot_docs_valid(7 * 24 * 60 * 60) {
                        storage.load_godot_docs().ok()
                    } else { None }
                };
                let _ = engine.load_cached_docs(cached_docs).await;
                let _ = engine.prefetch_common_godot_docs().await;
                if let Some(docs) = engine.get_cached_docs().await {
                    let storage = state_clone.storage.lock().unwrap();
                    let _ = storage.save_godot_docs(&docs);
                }
                // Make engine available in state if none exists yet
                {
                    let mut eng_state = state_clone.context_engine.lock().unwrap();
                    if eng_state.is_none() {
                        *eng_state = Some(engine);
                    }
                }
            }

        }
    });

    Ok(())
}

#[tauri::command]
fn get_godot_project_path(state: State<'_, AppState>) -> Result<String, String> {
    let project_path = state.godot_project_path.lock().unwrap();
    project_path.clone().ok_or("Godot project path not set".to_string())
}

#[tauri::command]
async fn process_command(
    input: String,
    state: State<'_, AppState>,
) -> Result<String, String> {
    // Get API key
    let api_key = {
        let storage = state.storage.lock().unwrap();
        storage.get_api_key().ok_or("API key not configured")?
    };

    // Get Godot project path
    let project_path = {
        let path = state.godot_project_path.lock().unwrap();
        path.clone().ok_or("Godot project path not set. Please set it in settings.")?
    };

    // Ensure we have an active chat session
    let session_exists = {
        let manager = state.chat_session_manager.lock().unwrap();
        manager.get_active_session().is_some()
    };

    if !session_exists {
        let mut manager = state.chat_session_manager.lock().unwrap();
        manager.create_session(Some("New Session".to_string()), Some(project_path.clone()));
    }

    // Add user message to session
    {
        let mut manager = state.chat_session_manager.lock().unwrap();
        if let Some(session) = manager.get_active_session_mut() {
            session.add_message(ChatMessage::user(input.clone()));
        }
    }

    // Step 1: Try to load cached project index, otherwise index the project
    let project_index = {
        let cached_index = state.project_index.lock().unwrap();
        if let Some(index) = cached_index.as_ref() {
            // Use cached index if available
            index.clone()
        } else {
            drop(cached_index); // Release lock before indexing

            // Try to load from persistent storage first
            let storage = state.storage.lock().unwrap();
            if storage.is_project_index_valid(&project_path, 24 * 60 * 60) { // 24 hours
                if let Ok(index) = storage.load_project_index(&project_path) {
                    // Cache in memory
                    let mut cached_index = state.project_index.lock().unwrap();
                    *cached_index = Some(index.clone());
                    drop(cached_index);
                    drop(storage);
                    index
                } else {
                    drop(storage);
                    // Index the project
                    let indexer = ProjectIndexer::new(&project_path);
                    let index = indexer.index_project()
                        .map_err(|e| format!("Failed to index project: {}", e))?;

                    // Cache in memory and persistent storage
                    let mut cached_index = state.project_index.lock().unwrap();
                    *cached_index = Some(index.clone());
                    drop(cached_index);

                    let storage = state.storage.lock().unwrap();
                    let _ = storage.save_project_index(&index, &project_path);
                    drop(storage);

                    index
                }
            } else {
                drop(storage);
                // Index the project
                let indexer = ProjectIndexer::new(&project_path);
                let index = indexer.index_project()
                    .map_err(|e| format!("Failed to index project: {}", e))?;

                // Cache in memory and persistent storage
                let mut cached_index = state.project_index.lock().unwrap();
                *cached_index = Some(index.clone());
                drop(cached_index);

                let storage = state.storage.lock().unwrap();
                let _ = storage.save_project_index(&index, &project_path);
                drop(storage);

                index
            }
        }
    };

    // Step 2: Initialize context engine if needed
    let context_engine = {
        let needs_init = {
            let engine = state.context_engine.lock().unwrap();
            engine.is_none()
        };

        if needs_init {
            let new_engine = ContextEngine::new(&api_key);

            // Try to load cached Godot docs
            let cached_docs = {
                let storage = state.storage.lock().unwrap();
                if storage.is_godot_docs_valid(7 * 24 * 60 * 60) {
                    storage.load_godot_docs().ok()
                } else {
                    None
                }
            };

            let _ = new_engine.load_cached_docs(cached_docs).await;

            let mut engine = state.context_engine.lock().unwrap();
            *engine = Some(new_engine);
        }

        let engine = state.context_engine.lock().unwrap();
        engine.as_ref().unwrap().clone()
    };

    // Step 3: Build comprehensive context (with chat history) and format for AI
    let chat_session_opt = {
        let manager = state.chat_session_manager.lock().unwrap();
        manager.get_active_session().cloned()
    };

    let comprehensive = context_engine
        .build_comprehensive_context(&input, &project_index, chat_session_opt.as_ref(), 10)
        .await
        .map_err(|e| format!("Failed to build context: {}", e))?;
    let context = context_engine.format_context_for_ai(&comprehensive);
    println!(
        "[ContextEngine] built: total_chars={}, docs_len={}, proj_len={}, chat_len={}, recent_msgs={}, query='{}'",
        context.len(),
        comprehensive.godot_docs.len(),
        comprehensive.project_context.len(),
        comprehensive.chat_history.len(),
        comprehensive.recent_messages.len(),
        comprehensive.context_query
    );

    // Save Godot docs to persistent storage
    if let Some(docs) = context_engine.get_cached_docs().await {
        let storage = state.storage.lock().unwrap();
        let _ = storage.save_godot_docs(&docs);
    }

    // Step 4: Initialize AI processor if needed
    let processor = {
        let mut ai_processor = state.ai_processor.lock().unwrap();
        if ai_processor.is_none() {
            *ai_processor = Some(AIProcessor::new(&api_key));
        }
        ai_processor.as_ref().unwrap().clone()
    };

    // Step 5: Process command with AI using context and project index
    let commands = processor.process_input(&input, &context, &project_index).await
        .map_err(|e| format!("AI processing failed: {}", e))?;

    // Step 6: Send commands to Godot and handle errors with immediate recovery
    let client = {
        let ws_client = state.ws_client.lock().unwrap();
        ws_client.as_ref().ok_or("Not connected to Godot")?.clone()
    };

    let mut successful_commands = 0;
    let mut total_recoveries = 0;
    let mut final_errors = Vec::new();

    for (idx, cmd) in commands.iter().enumerate() {
        // Try to execute the command
        println!("Executing command {}: {}", idx + 1, serde_json::to_string(cmd).unwrap_or_default());

        let result = client.send_command(cmd).await
            .map_err(|e| format!("Failed to send command: {}", e))?;

        println!("Command {} result: {}", idx + 1, serde_json::to_string(&result).unwrap_or_default());

        // Check if the command failed
        if let Some(status) = result.get("status").and_then(|s| s.as_str()) {
            if status == "error" {
                let error_msg = result.get("message")
                    .and_then(|m| m.as_str())
                    .unwrap_or("Unknown error");
                let action = cmd.get("action").and_then(|a| a.as_str()).unwrap_or("unknown");

                // Attempt immediate recovery for this specific error
                let error_context = format!("Command {}: {} - Error: {}", idx + 1, action, error_msg);

                println!("ERROR DETECTED: {}", error_context);
                println!("Attempting recovery...");

                match attempt_single_command_recovery(
                    &processor,
                    &input,
                    &context,
                    &project_index,
                    &error_context,
                    cmd,
                    &client,
                    0  // Start at recovery depth 0
                ).await {
                    Ok(recovery_msg) => {
                        println!("Recovery succeeded: {}", recovery_msg);
                        total_recoveries += 1;
                        successful_commands += 1;
                        // Recovery succeeded, continue to next command
                        continue;
                    }
                    Err(recovery_err) => {
                        println!("Recovery failed: {}", recovery_err);
                        // Recovery failed, record the error but CONTINUE with remaining tasks
                        final_errors.push(format!("{}\nRecovery failed: {}", error_context, recovery_err));
                        // Continue to next command instead of breaking
                        continue;
                    }
                }
            }
        }

        // Command succeeded
        println!("Command {} succeeded", idx + 1);
        successful_commands += 1;
    }

    // Report results
    let result_message: Result<String, String> = if !final_errors.is_empty() {
        // Some commands failed even after recovery attempts, but we continued with remaining tasks
        let failed_count = final_errors.len();
        Ok(format!(
            "Completed {} of {} commands successfully. {} recoveries attempted.\n{} command(s) failed after recovery attempts but processing continued:\n{}",
            successful_commands,
            commands.len(),
            total_recoveries,
            failed_count,
            final_errors.join("\n")
        ))
    } else if total_recoveries > 0 {
        Ok(format!(
            "Successfully executed {} commands ({} with automatic recovery)",
            successful_commands,
            total_recoveries
        ))
    } else {
        Ok(format!("Successfully executed {} commands", successful_commands))
    };

    // Add assistant response to chat session
    {
        let mut manager = state.chat_session_manager.lock().unwrap();
        if let Some(session) = manager.get_active_session_mut() {

            let response_content = match &result_message {
                Ok(msg) => msg.clone(),
                Err(msg) => msg.clone(),
            };

            // Create context snapshot
            let context_snapshot = ContextSnapshot {
                godot_docs_used: true,
                project_files_referenced: Vec::new(), // Could be enhanced to track actual files
                previous_messages_count: session.get_messages().len(),
                total_context_size: context.len(),
            };

            session.add_message(ChatMessage::assistant(
                response_content,
                None, // Thought process will be added in future enhancement
                Some(context_snapshot),
            ));

            // Update metadata
            session.update_metadata(result_message.is_ok(), 0); // Token count could be tracked

            // Save session to storage
            let storage = state.storage.lock().unwrap();
            let _ = storage.save_chat_session(session);
        }
    }

    result_message
}

// Maximum depth for recursive recovery attempts
const MAX_RECOVERY_DEPTH: usize = 3;

async fn attempt_single_command_recovery(
    processor: &AIProcessor,
    original_input: &str,
    context: &str,
    project_index: &ProjectIndex,
    error_context: &str,
    failed_command: &Value,
    client: &WebSocketClient,
    recovery_depth: usize,
) -> Result<String, String> {
    println!("=== RECOVERY ATTEMPT STARTED (Depth: {}) ===", recovery_depth);
    println!("Error context: {}", error_context);
    println!("Failed command: {}", serde_json::to_string_pretty(failed_command).unwrap_or_default());

    // First, get the current scene info to understand the state
    let scene_info_cmd = serde_json::json!({
        "action": "get_scene_info"
    });

    println!("Querying scene info...");
    let scene_info_result = client.send_command(&scene_info_cmd).await
        .map_err(|e| format!("Failed to get scene info: {}", e))?;

    let scene_info_str = serde_json::to_string_pretty(&scene_info_result)
        .unwrap_or_else(|_| "Unable to serialize scene info".to_string());

    println!("Scene info: {}", scene_info_str);

    // Extract specific error details for better recovery
    let error_msg = if error_context.contains("Parent node not found:") {
        // Extract the missing parent path
        let parts: Vec<&str> = error_context.split("Parent node not found:").collect();
        if parts.len() > 1 {
            let parent_path = parts[1].trim();
            format!("Parent node not found: {}", parent_path)
        } else {
            error_context.to_string()
        }
    } else {
        error_context.to_string()
    };

    // Create a more specific recovery prompt with clear instructions
    let recovery_input = format!(
        r#"ERROR RECOVERY REQUEST:

Current Scene State:
{}

Failed Command:
{}

Error Message: {}

Original User Request: '{}'

INSTRUCTIONS:
1. First, examine the Current Scene State to understand what exists
2. Analyze the error and determine what prerequisite commands are needed
3. If the error is "Parent node not found: X", check if X exists in the scene:
   - If X is the root node and doesn't exist, the scene might not be open - create it first
   - If X is a child node, create it with the correct parent
4. If the error is "Parent node not found: X/Y":
   - Check if X exists (it should be in the scene state)
   - Create node Y as a child of X
   - Then retry the original failed command
5. If the error is "No scene is currently open":
   - Create a scene with create_scene
   - Then retry the original failed command
6. Generate ALL necessary commands including the retry of the failed command
7. Return ONLY the JSON array of commands needed to fix and retry

Example for "Parent node not found: MainMenu" when MainMenu is the root:
[
  {{"action": "create_scene", "name": "MainMenu", "root_type": "Control", "save_path": "res://MainMenu.tscn"}},
  {{"action": "create_node", "type": "Panel", "name": "Background", "parent": "MainMenu", "properties": {{}}}}
]

Example for "Parent node not found: MainMenu/Container" when MainMenu exists:
[
  {{"action": "create_node", "type": "VBoxContainer", "name": "Container", "parent": "MainMenu", "properties": {{}}}},
  {{"action": "create_node", "type": "Label", "name": "Title", "parent": "MainMenu/Container", "properties": {{"text": "Title"}}}}
]"#,
        scene_info_str,
        serde_json::to_string_pretty(failed_command).unwrap_or_default(),
        error_msg,
        original_input
    );

    // Get recovery commands from AI
    println!("Sending recovery request to AI...");
    println!("Recovery prompt:\n{}", recovery_input);

    let recovery_commands = processor.process_input(&recovery_input, context, project_index).await
        .map_err(|e| {
            println!("AI failed to generate recovery commands: {}", e);
            format!("Failed to generate recovery commands: {}", e)
        })?;

    if recovery_commands.is_empty() {
        println!("AI generated no recovery commands!");
        return Err("AI generated no recovery commands".to_string());
    }

    // Log recovery commands for debugging
    println!("Recovery commands generated ({} commands): {}",
        recovery_commands.len(),
        serde_json::to_string_pretty(&recovery_commands).unwrap_or_default());

    // Execute recovery commands with recursive recovery support
    println!("Executing {} recovery commands...", recovery_commands.len());
    for (idx, cmd) in recovery_commands.iter().enumerate() {
        println!("Recovery command {} (depth {}): {}", idx + 1, recovery_depth, serde_json::to_string(cmd).unwrap_or_default());

        let result = client.send_command(cmd).await
            .map_err(|e| {
                println!("Failed to send recovery command {}: {}", idx + 1, e);
                format!("Failed to send recovery command {}: {}", idx + 1, e)
            })?;

        println!("Recovery command {} result: {}", idx + 1, serde_json::to_string(&result).unwrap_or_default());

        if let Some(status) = result.get("status").and_then(|s| s.as_str()) {
            if status == "error" {
                let error_msg = result.get("message")
                    .and_then(|m| m.as_str())
                    .unwrap_or("Unknown error");
                let action = cmd.get("action").and_then(|a| a.as_str()).unwrap_or("unknown");

                println!("Recovery command {} FAILED: {}", idx + 1, error_msg);

                // Fallback: if parent not found on create_node, try direct .tscn patch as last resort
                if action == "create_node" && error_msg.contains("Parent node not found") {
                    if let Some(scene_path) = scene_info_result
                        .get("data").and_then(|d| d.get("scene_path")).and_then(|s| s.as_str())
                    {
                        let node_name = cmd.get("name").and_then(|v| v.as_str());
                        let node_type = cmd.get("type").and_then(|v| v.as_str());
                        let parent_path = cmd.get("parent").and_then(|v| v.as_str());
                        if let (Some(n), Some(t), Some(p)) = (node_name, node_type, parent_path) {
                            match crate::tscn_utils::add_node_to_tscn(scene_path, n, t, p) {
                                Ok(_) => {
                                    println!(
                                        "Fallback applied: wrote node '{}' of type '{}' under '{}' into scene file {}",
                                        n, t, p, scene_path
                                    );
                                }
                                Err(e) => {
                                    println!("Fallback TSCN edit failed: {}", e);
                                }
                            }
                        }
                    }
                }

/// Build a small research snippet from the current project index and scene info
fn build_recovery_research(
    project_index: &ProjectIndex,
    scene_info: &serde_json::Value,
    error_msg: &str,
    failed_command: &serde_json::Value,
) -> String {
    let mut out = String::new();
    out.push_str("Project/Scene context relevant to recovery:\n");

    if let Some(data) = scene_info.get("data") {
        if data.get("scene_open").and_then(|v| v.as_bool()).unwrap_or(false) {
            if let Some(root_name) = data.get("root_name").and_then(|v| v.as_str()) {
                out.push_str(&format!("- Open scene root: {}\n", root_name));
            }
            if let Some(scene_path) = data.get("scene_path").and_then(|v| v.as_str()) {
                out.push_str(&format!("- Open scene path: {}\n", scene_path));
            }
        } else {
            out.push_str("- No scene is currently open in the editor.\n");
        }
    }

    let parent_path = failed_command.get("parent").and_then(|v| v.as_str()).unwrap_or("");
    if !parent_path.is_empty() {
        let root_hint = parent_path.split('/').next().unwrap_or(parent_path);
        out.push_str(&format!("- Failed parent path: '{}' (root hint: '{}')\n", parent_path, root_hint));
    }

    if let Some(node_type) = failed_command.get("type").and_then(|v| v.as_str()) {
        out.push_str(&format!("- Target node type: {}\n", node_type));
    }

    // Show a couple of scenes that might be relevant
    let mut ui_suggestions: Vec<&crate::project_indexer::SceneInfo> = Vec::new();
    let mut game_suggestions: Vec<&crate::project_indexer::SceneInfo> = Vec::new();
    for scene in &project_index.scenes {
        if let Some(rt) = &scene.root_type {
            if rt.contains("Control") || rt.contains("Panel") || rt.contains("Container") {
                ui_suggestions.push(scene);
            } else if rt.contains("Node2D") || rt.contains("Node3D") || rt.contains("CharacterBody") {
                game_suggestions.push(scene);
            }
        }
    }

    if !ui_suggestions.is_empty() {
        out.push_str("- Example UI scenes (root Control-like): ");
        for s in ui_suggestions.iter().take(3) {
            out.push_str(&format!("{} (root: {}), ", s.name, s.root_type.clone().unwrap_or_default()));
        }
        out.push('\n');
    }
    if !game_suggestions.is_empty() {
        out.push_str("- Example gameplay scenes (root Node2D/3D-like): ");
        for s in game_suggestions.iter().take(3) {
            out.push_str(&format!("{} (root: {}), ", s.name, s.root_type.clone().unwrap_or_default()));
        }
        out.push('\n');
    }

    out.push_str("Hints:\n- If parent is missing, create intermediate parents in order (X before X/Y).\n- If editor has no open scene, create or open a scene, then retry.\n- For editor persistence, ensure 'owner' is set to the edited scene root.\n");
    out.push_str(&format!("Original error: {}\n", error_msg));

    out
}

                // Check if we can attempt nested recovery; enhance context to avoid repeating same strategy
                if recovery_depth < MAX_RECOVERY_DEPTH {
                    println!("Attempting nested recovery (depth {} -> {})...", recovery_depth, recovery_depth + 1);

                    let nested_error_context = format!(
                        "Recovery command {} (depth {}): {} - Error: {}",
                        idx + 1,
                        recovery_depth,
                        action,
                        error_msg
                    );

                    let research_snippet = build_recovery_research(project_index, &scene_info_result, error_msg, cmd);
                    let enhanced_context = format!("{}\n\n# Additional Research\n{}", context, research_snippet);

                    // Attempt recursive recovery (boxed to avoid infinite size)
                    match Box::pin(attempt_single_command_recovery(
                        processor,
                        original_input,
                        &enhanced_context,
                        project_index,
                        &nested_error_context,
                        cmd,
                        client,
                        recovery_depth + 1  // Increment depth
                    )).await {
                        Ok(nested_recovery_msg) => {
                            println!("Nested recovery succeeded: {}", nested_recovery_msg);
                            // Continue with next recovery command
                            continue;
                        }
                        Err(nested_recovery_err) => {
                            println!("Nested recovery failed: {}", nested_recovery_err);
                            // Nested recovery failed, return error
                            let cmd_str = serde_json::to_string(cmd).unwrap_or_default();
                            return Err(format!(
                                "Recovery command {} failed: {}\nCommand was: {}\nNested recovery also failed: {}",
                                idx + 1,
                                error_msg,
                                cmd_str,
                                nested_recovery_err
                            ));
                        }
                    }
                } else {
                    // Max recovery depth reached
                    let cmd_str = serde_json::to_string(cmd).unwrap_or_default();
                    println!("Max recovery depth ({}) reached, cannot attempt further recovery", MAX_RECOVERY_DEPTH);
                    return Err(format!(
                        "Recovery command {} failed: {}\nCommand was: {}\nMax recovery depth ({}) reached",
                        idx + 1,
                        error_msg,
                        cmd_str,
                        MAX_RECOVERY_DEPTH
                    ));
                }
            }
        }
        println!("Recovery command {} succeeded", idx + 1);
    }

    println!("=== RECOVERY COMPLETED SUCCESSFULLY (Depth: {}) ===", recovery_depth);
    Ok(format!("Successfully executed {} recovery commands at depth {}", recovery_commands.len(), recovery_depth))
}

#[tauri::command]
fn get_api_key(state: State<'_, AppState>) -> Result<String, String> {
    let storage = state.storage.lock().unwrap();
    storage.get_api_key().ok_or("API key not configured".to_string())
}

#[tauri::command]
fn save_api_key(key: String, state: State<'_, AppState>) -> Result<(), String> {
    let mut storage = state.storage.lock().unwrap();
    storage.save_api_key(&key).map_err(|e| e.to_string())
}

#[tauri::command]
async fn refresh_project_index(state: State<'_, AppState>) -> Result<String, String> {
    // Get Godot project path
    let project_path = {
        let path = state.godot_project_path.lock().unwrap();
        path.clone().ok_or("Godot project path not set. Please set it in settings.")?
    };

    // Index the project
    let indexer = ProjectIndexer::new(&project_path);
    let project_index = indexer.index_project()
        .map_err(|e| format!("Failed to index project: {}", e))?;

    // Cache in memory
    {
        let mut cached_index = state.project_index.lock().unwrap();
        *cached_index = Some(project_index.clone());
    }

    // Save to persistent storage
    {
        let storage = state.storage.lock().unwrap();
        storage.save_project_index(&project_index, &project_path)
            .map_err(|e| format!("Failed to save project index: {}", e))?;
    }

    Ok(format!(
        "Project indexed: {} scenes, {} scripts, {} resources",
        project_index.scenes.len(),
        project_index.scripts.len(),
        project_index.resources.len()
    ))
}

#[tauri::command]
async fn clear_cache(state: State<'_, AppState>) -> Result<String, String> {
    // Clear in-memory cache
    {
        let mut cached_index = state.project_index.lock().unwrap();
        *cached_index = None;
    }

    {
        let mut engine = state.context_engine.lock().unwrap();
        *engine = None;
    }

    // Clear persistent cache
    {
        let storage = state.storage.lock().unwrap();
        storage.clear_cache()
            .map_err(|e| format!("Failed to clear cache: {}", e))?;
    }

    Ok("Cache cleared successfully".to_string())
}

#[tauri::command]
async fn get_cache_status(state: State<'_, AppState>) -> Result<String, String> {
    let project_path = {
        let path = state.godot_project_path.lock().unwrap();
        path.clone().ok_or("Godot project path not set")?
    };

    let storage = state.storage.lock().unwrap();

    let project_index_valid = storage.is_project_index_valid(&project_path, 24 * 60 * 60);
    let godot_docs_valid = storage.is_godot_docs_valid(7 * 24 * 60 * 60);

    let in_memory_index = {
        let cached_index = state.project_index.lock().unwrap();
        cached_index.is_some()
    };

    let in_memory_docs = {
        let engine = state.context_engine.lock().unwrap();
        engine.is_some()
    };

    Ok(format!(
        "Project Index - Persistent: {}, In-Memory: {}\nGodot Docs - Persistent: {}, In-Memory: {}",
        if project_index_valid { "Valid" } else { "Invalid/Missing" },
        if in_memory_index { "Cached" } else { "Not Cached" },
        if godot_docs_valid { "Valid" } else { "Invalid/Missing" },
        if in_memory_docs { "Cached" } else { "Not Cached" }
    ))
}

// Chat Session Management Commands

#[tauri::command]
async fn create_chat_session(
    state: State<'_, AppState>,
    title: Option<String>,
) -> Result<String, String> {
    let project_path = {
        let path = state.godot_project_path.lock().unwrap();
        path.clone()
    };

    let session_id = {
        let mut manager = state.chat_session_manager.lock().unwrap();
        manager.create_session(title, project_path)
    };

    // Save to storage
    let manager = state.chat_session_manager.lock().unwrap();
    if let Some(session) = manager.get_active_session() {
        let storage = state.storage.lock().unwrap();
        storage.save_chat_session(session)
            .map_err(|e| format!("Failed to save session: {}", e))?;
    }

    Ok(session_id)
}

#[tauri::command]
async fn get_active_session(state: State<'_, AppState>) -> Result<Value, String> {
    let manager = state.chat_session_manager.lock().unwrap();

    if let Some(session) = manager.get_active_session() {
        serde_json::to_value(session)
            .map_err(|e| format!("Failed to serialize session: {}", e))
    } else {
        Err("No active session".to_string())
    }
}

#[tauri::command]
async fn get_all_sessions(state: State<'_, AppState>) -> Result<Value, String> {
    let manager = state.chat_session_manager.lock().unwrap();
    let sessions = manager.get_all_sessions();

    serde_json::to_value(sessions)
        .map_err(|e| format!("Failed to serialize sessions: {}", e))
}

#[tauri::command]
async fn set_active_session(
    state: State<'_, AppState>,
    session_id: String,
) -> Result<String, String> {
    let mut manager = state.chat_session_manager.lock().unwrap();
    manager.set_active_session(&session_id)
        .map_err(|e| format!("Failed to set active session: {}", e))?;

    Ok("Session activated".to_string())
}

#[tauri::command]
async fn delete_session(
    state: State<'_, AppState>,
    session_id: String,
) -> Result<String, String> {
    {
        let mut manager = state.chat_session_manager.lock().unwrap();
        manager.delete_session(&session_id)
            .map_err(|e| format!("Failed to delete session: {}", e))?;
    }

    // Delete from storage
    let storage = state.storage.lock().unwrap();
    storage.delete_chat_session(&session_id)
        .map_err(|e| format!("Failed to delete from storage: {}", e))?;

    Ok("Session deleted".to_string())
}

#[tauri::command]
async fn clear_all_sessions(state: State<'_, AppState>) -> Result<String, String> {
    {
        let mut manager = state.chat_session_manager.lock().unwrap();
        *manager = ChatSessionManager::new();
    }

    let storage = state.storage.lock().unwrap();
    storage.clear_chat_sessions()
        .map_err(|e| format!("Failed to clear sessions: {}", e))?;

    Ok("All sessions cleared".to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            connect_to_godot,
            process_command,
            get_api_key,
            save_api_key,
            set_godot_project_path,
            get_godot_project_path,
            refresh_project_index,
            clear_cache,
            get_cache_status,
            create_chat_session,
            get_active_session,
            get_all_sessions,
            set_active_session,
            delete_session,
            clear_all_sessions
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
