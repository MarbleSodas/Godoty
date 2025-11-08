use serde_json::{json, Value};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use tauri::Emitter;
use tauri::{Manager, State};

mod agent;
mod ai;
mod chat_session;
mod context_engine;
mod guardrails;
mod knowledge_base;
mod knowledge_manager;
mod letta_backend;
mod llm_client;
mod llm_config;
mod metrics;
mod project_indexer;
mod storage;
mod strands_agent;
mod tscn_utils;
mod tutorial_processor;
mod web_search;
mod websocket;

use crate::llm_client::set_tool_event_context;
use agent::AgenticWorkflow;
use ai::AIProcessor;
use chat_session::{ChatMessage, ChatSessionManager, ContextSnapshot, MessageRole};
use context_engine::ContextEngine;
use knowledge_manager::KnowledgeManager;
use letta_backend::LettaBackend;
use llm_config::{AgentLlmConfig, ApiKeyStore, LlmProvider};
use metrics::MetricsStore;
use project_indexer::{IndexingStatus, ProjectIndex, ProjectIndexer};
use storage::Storage;
use websocket::WebSocketClient;

#[derive(Clone)]
struct AppState {
    ws_client: Arc<Mutex<Option<WebSocketClient>>>,
    ai_processor: Arc<Mutex<Option<AIProcessor>>>,
    context_engine: Arc<Mutex<Option<ContextEngine>>>,
    chat_session_manager: Arc<Mutex<ChatSessionManager>>,
    storage: Arc<Mutex<Storage>>,
    project_index: Arc<Mutex<Option<ProjectIndex>>>,
    godot_project_path: Arc<Mutex<Option<String>>>,
    indexing_status: Arc<Mutex<IndexingStatus>>,
    knowledge_manager: Arc<Mutex<Option<KnowledgeManager>>>,
    agentic_workflow: Arc<Mutex<Option<AgenticWorkflow>>>,
    metrics_store: Arc<Mutex<Option<MetricsStore>>>,
    agent_llm_config: Arc<Mutex<AgentLlmConfig>>,
    api_key_store: Arc<Mutex<ApiKeyStore>>,
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

        // Load agent LLM configuration (or use defaults)
        let agent_llm_config = storage
            .load_agent_llm_config()
            .unwrap_or_else(|_| AgentLlmConfig::default());

        // Load API keys (or use empty store)
        let api_key_store = storage
            .load_api_keys()
            .unwrap_or_else(|_| ApiKeyStore::new());

        Self {
            ws_client: Arc::new(Mutex::new(None)),
            ai_processor: Arc::new(Mutex::new(None)),
            context_engine: Arc::new(Mutex::new(None)),
            chat_session_manager: Arc::new(Mutex::new(session_manager)),
            storage: Arc::new(Mutex::new(storage)),
            project_index: Arc::new(Mutex::new(None)),
            knowledge_manager: Arc::new(Mutex::new(None)),
            agentic_workflow: Arc::new(Mutex::new(None)),
            godot_project_path: Arc::new(Mutex::new(project_path)),
            indexing_status: Arc::new(Mutex::new(IndexingStatus::NotStarted)),
            metrics_store: Arc::new(Mutex::new(None)),
            agent_llm_config: Arc::new(Mutex::new(agent_llm_config)),
            api_key_store: Arc::new(Mutex::new(api_key_store)),
        }
    }
}

// Helper: emit process-log events to frontend
fn now_millis() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

#[allow(clippy::too_many_arguments)]
fn emit_log(
    window: &tauri::Window,
    level: &str,
    category: &str,
    message: &str,
    agent: Option<&str>,
    task: Option<&str>,
    status: Option<&str>,
    session_id: Option<String>,
    data: Option<Value>,
) {
    let payload = json!({
        "id": format!("{}-{}", level, now_millis()),
        "timestamp": now_millis(),
        "level": level,
        "category": category,
        "message": message,
        "agent": agent,
        "task": task,
        "status": status,
        "sessionId": session_id,
        "data": data,
    });
    let _ = window.emit("process-log", payload);
}

#[tauri::command]
async fn save_web_search_settings(
    state: State<'_, AppState>,
    provider: Option<String>,
    api_key: Option<String>,
) -> Result<String, String> {
    let mut storage = state.storage.lock().unwrap();
    storage
        .save_web_search_settings(provider.as_deref(), api_key.as_deref())
        .map_err(|e| e.to_string())?;
    Ok("ok".into())
}

#[tauri::command]
async fn get_web_search_settings(state: State<'_, AppState>) -> Result<Value, String> {
    let storage = state.storage.lock().unwrap();
    let (provider, key) = storage.get_web_search_settings();
    Ok(
        json!({"provider": provider, "api_key_set": key.as_ref().map(|k| !k.is_empty()).unwrap_or(false)}),
    )
}

#[tauri::command]
async fn tool_web_search(
    window: tauri::Window,
    state: State<'_, AppState>,
    query: String,
    max_results: Option<usize>,
    session_id: Option<String>,
) -> Result<Value, String> {
    emit_log(
        &window,
        "info",
        "tool_call",
        "Web search started",
        Some("WebSearch"),
        Some("web_search"),
        Some("started"),
        session_id.clone(),
        Some(json!({"query": query})),
    );

    let (_provider, key_opt) = {
        let storage = state.storage.lock().unwrap();
        storage.get_web_search_settings()
    };

    // Resolve API key
    let api_key = if let Some(k) = key_opt {
        k
    } else {
        std::env::var("TAVILY_API_KEY").unwrap_or_default()
    };
    if api_key.is_empty() {
        emit_log(
            &window,
            "error",
            "tool_call",
            "Web search failed: missing API key",
            Some("WebSearch"),
            Some("web_search"),
            Some("error"),
            session_id,
            None,
        );
        return Err("Missing Tavily API key. Set in settings or TAVILY_API_KEY env.".into());
    }

    // Only Tavily for now
    let client = web_search::TavilyClient::new(api_key);
    let start = std::time::Instant::now();
    let res = client.search(&query, max_results.unwrap_or(5)).await;

    match res {
        Ok(results) => {
            let took_ms = start.elapsed().as_millis();
            emit_log(
                &window,
                "info",
                "tool_call",
                "Web search completed",
                Some("WebSearch"),
                Some("web_search"),
                Some("completed"),
                session_id.clone(),
                Some(json!({"results_count": results.results.len(), "took_ms": took_ms })),
            );
            Ok(serde_json::to_value(results).unwrap_or(json!({})))
        }
        Err(e) => {
            emit_log(
                &window,
                "error",
                "tool_call",
                &format!("Web search error: {}", e),
                Some("WebSearch"),
                Some("web_search"),
                Some("error"),
                session_id,
                None,
            );
            Err(e.to_string())
        }
    }
}

#[tauri::command]
async fn connect_to_godot(
    window: tauri::Window,
    state: State<'_, AppState>,
) -> Result<String, String> {
    match WebSocketClient::connect("ws://127.0.0.1:9001").await {
        Ok(client) => {
            // Store the client
            {
                let mut ws_client = state.ws_client.lock().unwrap();
                *ws_client = Some(client.clone());
            }

            // Request project path from Godot
            let get_path_command = json!({
                "action": "get_project_path"
            });

            println!("Requesting project path from Godot...");
            match client.send_command(&get_path_command).await {
                Ok(response) => {
                    println!("Received response from Godot: {:?}", response);
                    if response["status"] == "success" {
                        if let Some(project_path) = response["data"]["project_path"].as_str() {
                            println!("Detected Godot project path: {}", project_path);

                            // Check if this is a different project than currently configured
                            let current_path = {
                                let path = state.godot_project_path.lock().unwrap();
                                path.clone()
                            };

                            println!("Current stored path: {:?}", current_path);
                            println!("New detected path: {}", project_path);

                            let needs_update = match current_path {
                                Some(ref current) => {
                                    // Normalize paths for comparison
                                    let current_normalized = std::path::Path::new(current)
                                        .canonicalize()
                                        .ok()
                                        .and_then(|p| p.to_str().map(|s| s.to_lowercase()));
                                    let new_normalized = std::path::Path::new(project_path)
                                        .canonicalize()
                                        .ok()
                                        .and_then(|p| p.to_str().map(|s| s.to_lowercase()));

                                    println!("Current normalized: {:?}", current_normalized);
                                    println!("New normalized: {:?}", new_normalized);
                                    println!(
                                        "Paths are different: {}",
                                        current_normalized != new_normalized
                                    );

                                    current_normalized != new_normalized
                                }
                                None => {
                                    println!("No current path stored, will update");
                                    true // No current path, so we need to set it
                                }
                            };

                            if needs_update {
                                println!(
                                    "Project path changed, updating and triggering indexing..."
                                );

                                // Update the stored project path
                                {
                                    let mut path = state.godot_project_path.lock().unwrap();
                                    *path = Some(project_path.to_string());
                                }

                                // Save to storage
                                {
                                    let mut storage = state.storage.lock().unwrap();
                                    let _ = storage.save_project_path(project_path);
                                }

                                // Set status to Indexing and emit event
                                {
                                    let mut status = state.indexing_status.lock().unwrap();
                                    *status = IndexingStatus::Indexing;
                                    let _ = window.emit(
                                        "indexing-status-changed",
                                        json!({
                                            "projectPath": Some(project_path),
                                            "status": IndexingStatus::Indexing
                                        }),
                                    );
                                }

                                // Trigger background indexing
                                let state_clone = state.inner().clone();
                                let path_clone = project_path.to_string();
                                let window_clone = window.clone();

                                tokio::spawn(async move {
                                    perform_background_indexing(
                                        window_clone,
                                        path_clone,
                                        state_clone,
                                    )
                                    .await;
                                });

                                Ok(format!(
                                    "Connected to Godot and updated project path to: {}",
                                    project_path
                                ))
                            } else {
                                Ok("Connected to Godot (same project)".to_string())
                            }
                        } else {
                            Ok("Connected to Godot (no project path in response)".to_string())
                        }
                    } else {
                        // Failed to get project path, but connection is still valid
                        Ok("Connected to Godot (failed to get project path)".to_string())
                    }
                }
                Err(e) => {
                    // Failed to get project path, but connection is still valid
                    println!("Warning: Failed to get project path: {}", e);
                    Ok("Connected to Godot (failed to query project path)".to_string())
                }
            }
        }
        Err(e) => Err(format!("Failed to connect: {}", e)),
    }
}

/// Perform background indexing for a given project path
/// This function is shared between set_godot_project_path and startup indexing
async fn perform_background_indexing<R: tauri::Runtime, W: Emitter<R> + Clone + Send + 'static>(
    window: W,
    path: String,
    state: AppState,
) {
    // Get stored Godot executable path if available
    let godot_executable_path = {
        let storage = state.storage.lock().unwrap();
        storage.get_godot_executable_path(&path)
    };

    // Use automatic indexing: load from cache if valid, otherwise index
    let project_index_result = {
        let storage = state.storage.lock().unwrap();
        ProjectIndexer::index_or_load(&path, godot_executable_path, &storage)
    };

    match project_index_result {
        Ok(project_index) => {
            // Cache in memory
            {
                let mut cached_index = state.project_index.lock().unwrap();
                *cached_index = Some(project_index.clone());
            }

            println!(
                "Project index ready: {} scenes, {} scripts, {} resources",
                project_index.scenes.len(),
                project_index.scripts.len(),
                project_index.resources.len()
            );

            // Set status to Complete and emit event
            {
                let mut status = state.indexing_status.lock().unwrap();
                *status = IndexingStatus::Complete;
                let _ = window.emit(
                    "indexing-status-changed",
                    json!({
                        "projectPath": Some(path.clone()),
                        "status": IndexingStatus::Complete
                    }),
                );
            }

            // Proactively prefetch Godot docs and cache them
            let api_key_opt = {
                let storage = state.storage.lock().unwrap();
                storage.get_api_key()
            };
            if let Some(api_key) = api_key_opt {
                let engine = ContextEngine::new(&api_key);
                // Load any cached docs first
                let cached_docs = {
                    let storage = state.storage.lock().unwrap();
                    if storage.is_godot_docs_valid(7 * 24 * 60 * 60) {
                        storage.load_godot_docs().ok()
                    } else {
                        None
                    }
                };
                let _ = engine.load_cached_docs(cached_docs).await;
                let _ = engine.prefetch_common_godot_docs().await;
                if let Some(docs) = engine.get_cached_docs().await {
                    let storage = state.storage.lock().unwrap();
                    let _ = storage.save_godot_docs(&docs);
                }
                // Make engine available in state if none exists yet
                {
                    let mut eng_state = state.context_engine.lock().unwrap();
                    if eng_state.is_none() {
                        *eng_state = Some(engine);
                    }
                }
            }
        }
        Err(e) => {
            // Set status to Failed and emit event
            let error_msg = format!("Failed to index project: {}", e);
            println!("{}", error_msg);

            let mut status = state.indexing_status.lock().unwrap();
            *status = IndexingStatus::Failed(error_msg.clone());
            let _ = window.emit(
                "indexing-status-changed",
                json!({
                    "projectPath": Some(path.clone()),
                    "status": IndexingStatus::Failed(error_msg)
                }),
            );
        }
    }
}

#[tauri::command]
async fn set_godot_project_path(
    window: tauri::Window,
    path: String,
    state: State<'_, AppState>,
) -> Result<(), String> {
    // Save the project path to persistent storage
    {
        let mut storage = state.storage.lock().unwrap();
        storage
            .save_project_path(&path)
            .map_err(|e| format!("Failed to save project path: {}", e))?;
    }

    // Set the project path in memory
    {
        let mut project_path = state.godot_project_path.lock().unwrap();
        *project_path = Some(path.clone());
    }

    // Set status to Indexing and emit event
    {
        let mut status = state.indexing_status.lock().unwrap();
        *status = IndexingStatus::Indexing;
        let _ = window.emit(
            "indexing-status-changed",
            json!({
                "projectPath": Some(path.clone()),
                "status": IndexingStatus::Indexing
            }),
        );
    }

    // Trigger background indexing using the shared function
    let state_clone = state.inner().clone();
    let path_clone = path.clone();

    tokio::spawn(async move {
        perform_background_indexing(window, path_clone, state_clone).await;
    });

    Ok(())
}

#[tauri::command]
fn get_godot_project_path(state: State<'_, AppState>) -> Result<String, String> {
    let project_path = state.godot_project_path.lock().unwrap();
    project_path
        .clone()
        .ok_or("Godot project path not set".to_string())
}

#[tauri::command]
fn get_indexing_status(state: State<'_, AppState>) -> Result<Value, String> {
    let project_path = state.godot_project_path.lock().unwrap();
    let status = state.indexing_status.lock().unwrap();

    Ok(json!({
        "projectPath": project_path.clone(),
        "status": *status
    }))
}

#[tauri::command]
async fn set_godot_executable_path(
    project_path: String,
    executable_path: String,
    state: State<'_, AppState>,
) -> Result<(), String> {
    let mut storage = state.storage.lock().unwrap();
    storage
        .save_godot_executable_path(&project_path, &executable_path)
        .map_err(|e| format!("Failed to save Godot executable path: {}", e))
}

#[tauri::command]
fn get_godot_executable_path(
    project_path: String,
    state: State<'_, AppState>,
) -> Result<String, String> {
    let storage = state.storage.lock().unwrap();
    storage
        .get_godot_executable_path(&project_path)
        .ok_or("Godot executable path not set for this project".to_string())
}

#[tauri::command]
fn get_godot_executable_for_current_project(state: State<'_, AppState>) -> Result<String, String> {
    // Get the current project path
    let project_path = {
        let path = state.godot_project_path.lock().unwrap();
        path.clone()
            .ok_or("Godot project path not set".to_string())?
    };

    // Try to get the stored executable path
    let storage = state.storage.lock().unwrap();
    if let Some(exec_path) = storage.get_godot_executable_path(&project_path) {
        return Ok(exec_path);
    }

    // If not stored, try to auto-detect
    let indexer = ProjectIndexer::new(&project_path);
    if let Some(detected_path) = indexer.detect_godot_executable() {
        return Ok(detected_path);
    }

    Err("Godot executable not found. Please set it manually.".to_string())
}

#[tauri::command]
fn remove_godot_executable_path(
    project_path: String,
    state: State<'_, AppState>,
) -> Result<(), String> {
    let mut storage = state.storage.lock().unwrap();
    storage
        .remove_godot_executable_path(&project_path)
        .map_err(|e| format!("Failed to remove Godot executable path: {}", e))
}

#[tauri::command]
async fn process_command(
    window: tauri::Window,
    input: String,
    state: State<'_, AppState>,
) -> Result<String, String> {
    let processing_start = std::time::Instant::now();
    // Get API key
    let api_key = {
        let storage = state.storage.lock().unwrap();
        storage.get_api_key().ok_or("API key not configured")?
    };

    // Get Godot project path
    let project_path = {
        let path = state.godot_project_path.lock().unwrap();
        path.clone()
            .ok_or("Godot project path not set. Please set it in settings.")?
    };

    // Ensure we have an active chat session
    let session_exists = {
        let manager = state.chat_session_manager.lock().unwrap();
        manager.get_active_session().is_some()
    };

    if !session_exists {
        let mut manager = state.chat_session_manager.lock().unwrap();
        manager.create_session(Some("New Chat".to_string()), Some(project_path.clone()));
    }

    // Add user message to session and auto-generate title if this is the first message
    let should_generate_title = {
        let mut manager = state.chat_session_manager.lock().unwrap();
        if let Some(session) = manager.get_active_session_mut() {
            let is_first_message = session.messages.is_empty();
            session.add_message(ChatMessage::user(input.clone()));

            // Auto-generate title from first message if session has default title
            if is_first_message
                && (session.title == "New Chat" || session.title.starts_with("Session "))
            {
                let new_title = generate_session_title_from_message(&input);
                session.update_title(new_title);
                true
            } else {
                false
            }
        } else {
            false
        }
    };

    // Save session if title was updated
    if should_generate_title {
        let manager = state.chat_session_manager.lock().unwrap();
        if let Some(session) = manager.get_active_session() {
            let storage = state.storage.lock().unwrap();
            let _ = storage.save_chat_session(session);
        }
    }

    // Emit start log for this session
    let session_id_for_logs = {
        let manager = state.chat_session_manager.lock().unwrap();
        manager.get_active_session().map(|s| s.id.clone())
    };
    emit_log(
        &window,
        "info",
        "agent_activity",
        "AI processing started",
        Some("Assistant"),
        None,
        Some("processing"),
        session_id_for_logs.clone(),
        Some(json!({ "input_preview": input.chars().take(200).collect::<String>() })),
    );

    // Step 1: Try to load cached project index, otherwise index the project
    let project_index = {
        let cached_index = state.project_index.lock().unwrap();
        if let Some(index) = cached_index.as_ref() {
            // Use cached index if available
            index.clone()
        } else {
            drop(cached_index); // Release lock before indexing

            // Get Godot executable path if available
            let godot_executable_path = {
                let storage = state.storage.lock().unwrap();
                storage.get_godot_executable_path(&project_path)
            };

            // Use automatic indexing: load from cache if valid, otherwise index
            let index = {
                let storage = state.storage.lock().unwrap();
                ProjectIndexer::index_or_load(&project_path, godot_executable_path, &storage)
                    .map_err(|e| format!("Failed to get project index: {}", e))?
            };

            // Cache in memory
            let mut cached_index = state.project_index.lock().unwrap();
            *cached_index = Some(index.clone());

            index
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
    let mut context = context_engine.format_context_for_ai(&comprehensive);
    let visual_analysis_used = false;
    let mut tutorial_research_used = false;
    let mut snapshot_b64_to_attach: Option<String> = None;
    let mut snapshot_meta_to_attach: Option<serde_json::Value> = None;

    // Integrate Visual Snapshot Analysis (Godot Inspector)
    {
        // Clone WebSocket client if connected (do not hold lock across await)
        let client_for_capture = {
            let ws_client = state.ws_client.lock().unwrap();
            ws_client.as_ref().cloned()
        };
        if let Some(client_for_capture) = client_for_capture {
            // Get latest snapshot captured by the inspector plugin (if any)
            if let Ok(snapshot) = client_for_capture
                .send_command(&serde_json::json!({"action":"get_visual_snapshot"}))
                .await
            {
                if snapshot.get("status").and_then(|s| s.as_str()) == Some("success") {
                    if let Some(data) = snapshot.get("data") {
                        let image_b64 =
                            data.get("image_b64").and_then(|v| v.as_str()).unwrap_or("");
                        let meta = data
                            .get("meta")
                            .cloned()
                            .unwrap_or_else(|| serde_json::json!({}));
                        if !image_b64.is_empty() {
                            // Attach snapshot to the message later
                            snapshot_b64_to_attach = Some(image_b64.to_string());
                            snapshot_meta_to_attach = Some(meta.clone());
                        }
                    }
                }
            }
        }
    }

    // Integrate Tutorial Research (lower precedence than official docs)
    {
        let version_key = project_index.godot_version.as_deref();
        let should_research = comprehensive.context_query.trim().len() >= 3;
        if should_research {
            // 3-day cache
            let cached_ok = {
                let storage = state.storage.lock().unwrap();
                storage.is_tutorials_valid(version_key, 3 * 24 * 60 * 60)
            };

            let tutorials_text = if cached_ok {
                let storage = state.storage.lock().unwrap();
                storage.load_tutorials(version_key).unwrap_or_default()
            } else {
                let tp = crate::tutorial_processor::TutorialProcessor::new();
                let fetched = tp
                    .fetch_godot_tutorials(&comprehensive.context_query, version_key)
                    .await
                    .unwrap_or_default();
                if !fetched.is_empty() {
                    let storage = state.storage.lock().unwrap();
                    let _ = storage.save_tutorials(&fetched, version_key);
                }
                fetched
            };

            if !tutorials_text.trim().is_empty() {
                context.push_str("# Tutorial Context (Lower Precedence)\n");
                context.push_str("Note: Official Godot documentation takes precedence over tutorials. Conflicts will be resolved in favor of docs.\n\n");
                context.push_str(&tutorials_text);
                context.push_str("\n\n");
                tutorial_research_used = true;
            }
        }
    }
    println!(
        "[ContextEngine] built: total_chars={}, docs_len={}, proj_len={}, chat_len={}, recent_msgs={}, query='{}'",
        context.len(),
        comprehensive.godot_docs.len(),
        comprehensive.project_context.len(),
        comprehensive.chat_history.len(),
        comprehensive.recent_messages.len(),
        comprehensive.context_query
    );

    // Emit context built log
    emit_log(
        &window,
        "info",
        "information_flow",
        "Context built",
        Some("ContextEngine"),
        None,
        Some("processing"),
        session_id_for_logs.clone(),
        Some(json!({
            "context_chars": context.len(),
            "docs_len": comprehensive.godot_docs.len(),
            "project_len": comprehensive.project_context.len(),
            "chat_len": comprehensive.chat_history.len(),
            "recent_messages": comprehensive.recent_messages.len()
        })),
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
    let commands = processor
        .process_input(&input, &context, &project_index)
        .await
        .map_err(|e| format!("AI processing failed: {}", e))?;

    // Emit AI command generation log
    emit_log(
        &window,
        "info",
        "agent_activity",
        &format!("AI generated {} command(s)", commands.len()),
        Some("Assistant"),
        Some("Plan commands"),
        Some("processing"),
        session_id_for_logs.clone(),
        Some(json!({ "count": commands.len() })),
    );

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
        // Inline activity log: about to execute command
        let action_name = cmd
            .get("action")
            .and_then(|a| a.as_str())
            .unwrap_or("unknown");
        emit_log(
            &window,
            "info",
            "action",
            &format!("Executing command {}: {}", idx + 1, action_name),
            Some("GodotBridge"),
            Some("Execute"),
            Some("processing"),
            session_id_for_logs.clone(),
            Some(json!({ "index": idx + 1, "action": action_name, "command": cmd })),
        );

        println!(
            "Executing command {}: {}",
            idx + 1,
            serde_json::to_string(cmd).unwrap_or_default()
        );

        let result = client
            .send_command(cmd)
            .await
            .map_err(|e| format!("Failed to send command: {}", e))?;

        println!(
            "Command {} result: {}",
            idx + 1,
            serde_json::to_string(&result).unwrap_or_default()
        );

        // Check if the command failed
        if let Some(status) = result.get("status").and_then(|s| s.as_str()) {
            if status == "error" {
                let error_msg = result
                    .get("message")
                    .and_then(|m| m.as_str())
                    .unwrap_or("Unknown error");
                let action = cmd
                    .get("action")
                    .and_then(|a| a.as_str())
                    .unwrap_or("unknown");

                // Attempt immediate recovery for this specific error
                let error_context =
                    format!("Command {}: {} - Error: {}", idx + 1, action, error_msg);

                println!("ERROR DETECTED: {}", error_context);
                emit_log(
                    &window,
                    "error",
                    "action",
                    &error_context,
                    Some("GodotBridge"),
                    Some("Execute"),
                    Some("error"),
                    session_id_for_logs.clone(),
                    Some(json!({ "index": idx + 1, "action": action, "result": result })),
                );

                println!("Attempting recovery...");

                match attempt_single_command_recovery(
                    &processor,
                    &input,
                    &context,
                    &project_index,
                    &error_context,
                    cmd,
                    &client,
                    0, // Start at recovery depth 0
                )
                .await
                {
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
                        final_errors.push(format!(
                            "{}\nRecovery failed: {}",
                            error_context, recovery_err
                        ));
                        // Continue to next command instead of breaking
                        continue;
                    }
                }
            }
        }

        // Command succeeded
        println!("Command {} succeeded", idx + 1);
        emit_log(
            &window,
            "info",
            "action",
            &format!("Command {} succeeded", idx + 1),
            Some("GodotBridge"),
            Some("Execute"),
            Some("completed"),
            session_id_for_logs.clone(),
            None,
        );

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
            successful_commands, total_recoveries
        ))
    } else {
        Ok(format!(
            "Successfully executed {} commands",
            successful_commands
        ))
    };

    // Emit final completion log
    match &result_message {
        Ok(msg) => emit_log(
            &window,
            "info",
            "agent_activity",
            "AI processing complete",
            Some("Assistant"),
            None,
            Some("completed"),
            session_id_for_logs.clone(),
            Some(json!({ "summary": msg })),
        ),
        Err(msg) => emit_log(
            &window,
            "error",
            "agent_activity",
            "AI processing failed",
            Some("Assistant"),
            None,
            Some("error"),
            session_id_for_logs.clone(),
            Some(json!({ "summary": msg })),
        ),
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
                visual_analysis_used,
                tutorial_research_used,
            };

            let mut msg = ChatMessage::assistant(
                response_content,
                None, // Thought process will be added in future enhancement
                Some(context_snapshot),
                snapshot_b64_to_attach,
                snapshot_meta_to_attach,
            );
            // Attach basic metrics (latency only for now)
            msg.metrics = Some(chat_session::MessageMetrics {
                input_tokens: 0,
                output_tokens: 0,
                total_tokens: 0,
                latency_ms: processing_start.elapsed().as_millis() as u64,
                tool_call_times: Vec::new(),
                cost_estimate_usd: None,
            });
            session.add_message(msg);

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

#[allow(clippy::too_many_arguments)]
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
    println!(
        "=== RECOVERY ATTEMPT STARTED (Depth: {}) ===",
        recovery_depth
    );
    println!("Error context: {}", error_context);
    println!(
        "Failed command: {}",
        serde_json::to_string_pretty(failed_command).unwrap_or_default()
    );

    // First, get the current scene info to understand the state
    let scene_info_cmd = serde_json::json!({
        "action": "get_scene_info"
    });

    println!("Querying scene info...");
    let scene_info_result = client
        .send_command(&scene_info_cmd)
        .await
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

    let recovery_commands = processor
        .process_input(&recovery_input, context, project_index)
        .await
        .map_err(|e| {
            println!("AI failed to generate recovery commands: {}", e);
            format!("Failed to generate recovery commands: {}", e)
        })?;

    if recovery_commands.is_empty() {
        println!("AI generated no recovery commands!");
        return Err("AI generated no recovery commands".to_string());
    }

    // Log recovery commands for debugging
    println!(
        "Recovery commands generated ({} commands): {}",
        recovery_commands.len(),
        serde_json::to_string_pretty(&recovery_commands).unwrap_or_default()
    );

    // Execute recovery commands with recursive recovery support
    println!("Executing {} recovery commands...", recovery_commands.len());
    for (idx, cmd) in recovery_commands.iter().enumerate() {
        println!(
            "Recovery command {} (depth {}): {}",
            idx + 1,
            recovery_depth,
            serde_json::to_string(cmd).unwrap_or_default()
        );

        let result = client.send_command(cmd).await.map_err(|e| {
            println!("Failed to send recovery command {}: {}", idx + 1, e);
            format!("Failed to send recovery command {}: {}", idx + 1, e)
        })?;

        println!(
            "Recovery command {} result: {}",
            idx + 1,
            serde_json::to_string(&result).unwrap_or_default()
        );

        if let Some(status) = result.get("status").and_then(|s| s.as_str()) {
            if status == "error" {
                let error_msg = result
                    .get("message")
                    .and_then(|m| m.as_str())
                    .unwrap_or("Unknown error");
                let action = cmd
                    .get("action")
                    .and_then(|a| a.as_str())
                    .unwrap_or("unknown");

                println!("Recovery command {} FAILED: {}", idx + 1, error_msg);

                // Fallback: if parent not found on create_node, try direct .tscn patch as last resort
                if action == "create_node" && error_msg.contains("Parent node not found") {
                    if let Some(scene_path) = scene_info_result
                        .get("data")
                        .and_then(|d| d.get("scene_path"))
                        .and_then(|s| s.as_str())
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
                        if data
                            .get("scene_open")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(false)
                        {
                            if let Some(root_name) = data.get("root_name").and_then(|v| v.as_str())
                            {
                                out.push_str(&format!("- Open scene root: {}\n", root_name));
                            }
                            if let Some(scene_path) =
                                data.get("scene_path").and_then(|v| v.as_str())
                            {
                                out.push_str(&format!("- Open scene path: {}\n", scene_path));
                            }
                        } else {
                            out.push_str("- No scene is currently open in the editor.\n");
                        }
                    }

                    let parent_path = failed_command
                        .get("parent")
                        .and_then(|v| v.as_str())
                        .unwrap_or("");
                    if !parent_path.is_empty() {
                        let root_hint = parent_path.split('/').next().unwrap_or(parent_path);
                        out.push_str(&format!(
                            "- Failed parent path: '{}' (root hint: '{}')\n",
                            parent_path, root_hint
                        ));
                    }

                    if let Some(node_type) = failed_command.get("type").and_then(|v| v.as_str()) {
                        out.push_str(&format!("- Target node type: {}\n", node_type));
                    }

                    // Show a couple of scenes that might be relevant
                    let mut ui_suggestions: Vec<&crate::project_indexer::SceneInfo> = Vec::new();
                    let mut game_suggestions: Vec<&crate::project_indexer::SceneInfo> = Vec::new();
                    for scene in &project_index.scenes {
                        if let Some(rt) = &scene.root_type {
                            if rt.contains("Control")
                                || rt.contains("Panel")
                                || rt.contains("Container")
                            {
                                ui_suggestions.push(scene);
                            } else if rt.contains("Node2D")
                                || rt.contains("Node3D")
                                || rt.contains("CharacterBody")
                            {
                                game_suggestions.push(scene);
                            }
                        }
                    }

                    if !ui_suggestions.is_empty() {
                        out.push_str("- Example UI scenes (root Control-like): ");
                        for s in ui_suggestions.iter().take(3) {
                            out.push_str(&format!(
                                "{} (root: {}), ",
                                s.name,
                                s.root_type.clone().unwrap_or_default()
                            ));
                        }
                        out.push('\n');
                    }
                    if !game_suggestions.is_empty() {
                        out.push_str("- Example gameplay scenes (root Node2D/3D-like): ");
                        for s in game_suggestions.iter().take(3) {
                            out.push_str(&format!(
                                "{} (root: {}), ",
                                s.name,
                                s.root_type.clone().unwrap_or_default()
                            ));
                        }
                        out.push('\n');
                    }

                    out.push_str("Hints:\n- If parent is missing, create intermediate parents in order (X before X/Y).\n- If editor has no open scene, create or open a scene, then retry.\n- For editor persistence, ensure 'owner' is set to the edited scene root.\n");
                    out.push_str(&format!("Original error: {}\n", error_msg));

                    out
                }

                // Check if we can attempt nested recovery; enhance context to avoid repeating same strategy
                if recovery_depth < MAX_RECOVERY_DEPTH {
                    println!(
                        "Attempting nested recovery (depth {} -> {})...",
                        recovery_depth,
                        recovery_depth + 1
                    );

                    let nested_error_context = format!(
                        "Recovery command {} (depth {}): {} - Error: {}",
                        idx + 1,
                        recovery_depth,
                        action,
                        error_msg
                    );

                    let research_snippet =
                        build_recovery_research(project_index, &scene_info_result, error_msg, cmd);
                    let enhanced_context =
                        format!("{}\n\n# Additional Research\n{}", context, research_snippet);

                    // Attempt recursive recovery (boxed to avoid infinite size)
                    match Box::pin(attempt_single_command_recovery(
                        processor,
                        original_input,
                        &enhanced_context,
                        project_index,
                        &nested_error_context,
                        cmd,
                        client,
                        recovery_depth + 1, // Increment depth
                    ))
                    .await
                    {
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
                    println!(
                        "Max recovery depth ({}) reached, cannot attempt further recovery",
                        MAX_RECOVERY_DEPTH
                    );
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

    println!(
        "=== RECOVERY COMPLETED SUCCESSFULLY (Depth: {}) ===",
        recovery_depth
    );
    Ok(format!(
        "Successfully executed {} recovery commands at depth {}",
        recovery_commands.len(),
        recovery_depth
    ))
}

#[tauri::command]
fn get_api_key(state: State<'_, AppState>) -> Result<String, String> {
    let storage = state.storage.lock().unwrap();
    storage
        .get_api_key()
        .ok_or("API key not configured".to_string())
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
        path.clone()
            .ok_or("Godot project path not set. Please set it in settings.")?
    };

    // Get stored Godot executable path if available
    let godot_executable_path = {
        let storage = state.storage.lock().unwrap();
        storage.get_godot_executable_path(&project_path)
    };

    // Index the project with the Godot executable path
    let indexer = ProjectIndexer::with_godot_executable(&project_path, godot_executable_path);
    let project_index = indexer
        .index_project()
        .map_err(|e| format!("Failed to index project: {}", e))?;

    // Cache in memory
    {
        let mut cached_index = state.project_index.lock().unwrap();
        *cached_index = Some(project_index.clone());
    }

    // Save to persistent storage
    {
        let storage = state.storage.lock().unwrap();
        storage
            .save_project_index(&project_index, &project_path)
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
        storage
            .clear_cache()
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
        if project_index_valid {
            "Valid"
        } else {
            "Invalid/Missing"
        },
        if in_memory_index {
            "Cached"
        } else {
            "Not Cached"
        },
        if godot_docs_valid {
            "Valid"
        } else {
            "Invalid/Missing"
        },
        if in_memory_docs {
            "Cached"
        } else {
            "Not Cached"
        }
    ))
}

/// Helper function to generate a session title from the first message
fn generate_session_title_from_message(message: &str) -> String {
    // Take first 50 characters or up to first newline, whichever comes first
    let title = message
        .lines()
        .next()
        .unwrap_or(message)
        .chars()
        .take(50)
        .collect::<String>();

    // If we truncated and it's not due to a newline, add ellipsis
    if title.len() < message.len() && !message.contains('\n') {
        format!("{}...", title)
    } else {
        title
    }
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
        storage
            .save_chat_session(session)
            .map_err(|e| format!("Failed to save session: {}", e))?;
    }

    Ok(session_id)
}

#[tauri::command]
async fn get_active_session(state: State<'_, AppState>) -> Result<Value, String> {
    let manager = state.chat_session_manager.lock().unwrap();

    if let Some(session) = manager.get_active_session() {
        serde_json::to_value(session).map_err(|e| format!("Failed to serialize session: {}", e))
    } else {
        Err("No active session".to_string())
    }
}

#[tauri::command]
async fn get_all_sessions(state: State<'_, AppState>) -> Result<Value, String> {
    let manager = state.chat_session_manager.lock().unwrap();
    let sessions = manager.get_all_sessions();

    serde_json::to_value(sessions).map_err(|e| format!("Failed to serialize sessions: {}", e))
}

#[tauri::command]
async fn set_active_session(
    state: State<'_, AppState>,
    session_id: String,
) -> Result<String, String> {
    let mut manager = state.chat_session_manager.lock().unwrap();
    manager
        .set_active_session(&session_id)
        .map_err(|e| format!("Failed to set active session: {}", e))?;

    Ok("Session activated".to_string())
}

#[tauri::command]
async fn delete_session(state: State<'_, AppState>, session_id: String) -> Result<String, String> {
    {
        let mut manager = state.chat_session_manager.lock().unwrap();
        manager
            .delete_session(&session_id)
            .map_err(|e| format!("Failed to delete session: {}", e))?;
    }

    // Delete from storage
    let storage = state.storage.lock().unwrap();
    storage
        .delete_chat_session(&session_id)
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
    storage
        .clear_chat_sessions()
        .map_err(|e| format!("Failed to clear sessions: {}", e))?;

    Ok("All sessions cleared".to_string())
}

#[tauri::command]
async fn update_session_title(
    state: State<'_, AppState>,
    session_id: String,
    new_title: String,
) -> Result<String, String> {
    {
        let mut manager = state.chat_session_manager.lock().unwrap();
        manager
            .update_session_title(&session_id, new_title)
            .map_err(|e| format!("Failed to update session title: {}", e))?;
    }

    // Save to storage
    let manager = state.chat_session_manager.lock().unwrap();
    if let Some(session) = manager
        .get_all_sessions()
        .iter()
        .find(|s| s.id == session_id)
    {
        let storage = state.storage.lock().unwrap();
        storage
            .save_chat_session(session)
            .map_err(|e| format!("Failed to save session: {}", e))?;
    }

    Ok("Session title updated".to_string())
}

// Append a system message to a specific session and persist it.
#[tauri::command]
fn append_system_message(
    state: State<'_, AppState>,
    session_id: String,
    id: String,
    content: String,
    timestamp: Option<u64>,
) -> Result<String, String> {
    let mut manager = state.chat_session_manager.lock().unwrap();

    // Find the target session without switching the active session
    let session = manager
        .get_session_mut(&session_id)
        .ok_or_else(|| format!("Session not found: {}", session_id))?;

    // De-dup: if a message with the same id already exists, do nothing
    if session.messages.iter().any(|m| m.id == id) {
        return Ok("duplicate_ignored".to_string());
    }

    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);

    let msg = ChatMessage {
        id,
        role: MessageRole::System,
        content,
        timestamp: timestamp.unwrap_or(now),
        thought_process: None,
        context_used: None,
        visual_snapshot_b64: None,
        visual_snapshot_meta: None,
        metrics: None,
    };

    session.add_message(msg);

    // Persist the updated session
    let storage = state.storage.lock().unwrap();
    storage
        .save_chat_session(session)
        .map_err(|e| format!("Failed to save session: {}", e))?;

    Ok("ok".to_string())
}

/// Initialize knowledge bases
#[tauri::command]
async fn initialize_knowledge_bases(state: State<'_, AppState>) -> Result<String, String> {
    // Pick embeddings key: prefer provider-specific OpenRouter key, else fall back to legacy key
    let embed_api_key = {
        let store = state.api_key_store.lock().unwrap();
        store.get_key(&LlmProvider::OpenRouter).cloned()
    }
    .or_else(|| {
        let storage = state.storage.lock().unwrap();
        storage.get_api_key()
    })
    .ok_or("API key not configured. Please set an OpenRouter key in Settings.")?;

    // Get storage directory
    let storage_dir = storage::Storage::get_config_dir()
        .map_err(|e| format!("Failed to get config dir: {}", e))?;

    // Initialize knowledge manager
    let km = KnowledgeManager::new(&embed_api_key, storage_dir.clone());
    km.initialize()
        .await
        .map_err(|e| format!("Failed to initialize knowledge bases: {}", e))?;

    // Store in state
    {
        let mut knowledge_manager = state.knowledge_manager.lock().unwrap();
        *knowledge_manager = Some(km);
    }

    // Initialize metrics store
    let metrics_store = MetricsStore::new(storage_dir.clone());
    {
        let mut store = state.metrics_store.lock().unwrap();
        *store = Some(metrics_store.clone());
    }

    // Initialize agentic workflow with metrics and LLM factory
    {
        let agent_llm_config = state.agent_llm_config.lock().unwrap().clone();
        let llm_factory = llm_client::LlmFactory::new(agent_llm_config);

        let mut agentic_workflow = state.agentic_workflow.lock().unwrap();
        *agentic_workflow = Some(
            AgenticWorkflow::new(&embed_api_key)
                .with_metrics_store(metrics_store)
                .with_llm_factory(llm_factory),
        );
    }

    Ok("Knowledge bases initialized successfully".to_string())
}

/// Process command using agentic workflow
#[tauri::command]
#[tracing::instrument(skip(window, state, input))]
async fn process_command_agentic(
    window: tauri::Window,
    input: String,
    state: State<'_, AppState>,
) -> Result<String, String> {
    let processing_start = std::time::Instant::now();
    let mut web_search_time_ms: Option<u64> = None;
    // Get API key for LLM calls: prefer provider-specific OpenRouter key, else fall back to legacy key
    let api_key = {
        let store = state.api_key_store.lock().unwrap();
        if let Some(k) = store.get_key(&LlmProvider::OpenRouter) {
            k.clone()
        } else {
            let storage = state.storage.lock().unwrap();
            storage.get_api_key().ok_or("API key not configured")?
        }
    };

    // Get Godot project path
    let project_path = {
        let path = state.godot_project_path.lock().unwrap();
        path.clone()
            .ok_or("Godot project path not set. Please set it in settings.")?
    };

    // Ensure knowledge bases are initialized
    let km_exists = {
        let km = state.knowledge_manager.lock().unwrap();
        km.is_some()
    };

    if !km_exists {
        // Log knowledge base initialization if not present
        emit_log(
            &window,
            "debug",
            "agent_activity",
            "Initializing knowledge bases",
            Some("System"),
            Some("Bootstrap"),
            Some("processing"),
            None,
            None,
        );

        // Initialize knowledge bases
        let storage_dir = storage::Storage::get_config_dir()
            .map_err(|e| format!("Failed to get config dir: {}", e))?;
        let embed_api_key = {
            let store = state.api_key_store.lock().unwrap();
            store.get_key(&LlmProvider::OpenRouter).cloned()
        }
        .unwrap_or_else(|| api_key.clone());
        let km = KnowledgeManager::new(&embed_api_key, storage_dir);
        km.initialize()
            .await
            .map_err(|e| format!("Failed to initialize knowledge bases: {}", e))?;

        let mut knowledge_manager = state.knowledge_manager.lock().unwrap();
        *knowledge_manager = Some(km);

        emit_log(
            &window,
            "info",
            "agent_activity",
            "Knowledge bases initialized",
            Some("System"),
            Some("Bootstrap"),
            Some("completed"),
            None,
            None,
        );
    }

    // Ensure metrics store is initialized
    let metrics_exists = {
        let store = state.metrics_store.lock().unwrap();
        store.is_some()
    };

    if !metrics_exists {
        let storage_dir = storage::Storage::get_config_dir()
            .map_err(|e| format!("Failed to get config dir: {}", e))?;
        emit_log(
            &window,
            "debug",
            "agent_activity",
            "Initializing metrics store",
            Some("System"),
            Some("Bootstrap"),
            Some("processing"),
            None,
            None,
        );
        let metrics_store = MetricsStore::new(storage_dir);
        let mut store = state.metrics_store.lock().unwrap();
        *store = Some(metrics_store);
        emit_log(
            &window,
            "info",
            "agent_activity",
            "Metrics store ready",
            Some("System"),
            Some("Bootstrap"),
            Some("completed"),
            None,
            None,
        );
    }

    // Ensure agentic workflow is initialized
    let workflow_exists = {
        let workflow = state.agentic_workflow.lock().unwrap();
        workflow.is_some()
    };

    if !workflow_exists {
        emit_log(
            &window,
            "debug",
            "agent_activity",
            "Initializing agentic workflow",
            Some("System"),
            Some("Bootstrap"),
            Some("processing"),
            None,
            None,
        );
        let metrics_store = {
            let store = state.metrics_store.lock().unwrap();
            store.clone().ok_or("Metrics store not initialized")?
        };

        let agent_llm_config = state.agent_llm_config.lock().unwrap().clone();
        let llm_factory = llm_client::LlmFactory::new(agent_llm_config);

        let mut agentic_workflow = state.agentic_workflow.lock().unwrap();
        *agentic_workflow = Some(
            AgenticWorkflow::new(&api_key)
                .with_metrics_store(metrics_store)
                .with_llm_factory(llm_factory),
        );
        emit_log(
            &window,
            "info",
            "agent_activity",
            "Agentic workflow ready",
            Some("System"),
            Some("Bootstrap"),
            Some("completed"),
            None,
            None,
        );
    }

    // Ensure we have an active chat session
    let session_exists = {
        let manager = state.chat_session_manager.lock().unwrap();
        manager.get_active_session().is_some()
    };

    if !session_exists {
        let mut manager = state.chat_session_manager.lock().unwrap();
        manager.create_session(Some("New Chat".to_string()), Some(project_path.clone()));
    }

    // Add user message to session and auto-generate title if this is the first message
    let should_generate_title = {
        let mut manager = state.chat_session_manager.lock().unwrap();
        if let Some(session) = manager.get_active_session_mut() {
            let is_first_message = session.messages.is_empty();
            session.add_message(ChatMessage::user(input.clone()));

            // Auto-generate title from first message if session has default title
            if is_first_message
                && (session.title == "New Chat" || session.title.starts_with("Session "))
            {
                let new_title = generate_session_title_from_message(&input);
                session.update_title(new_title);
                true
            } else {
                false
            }
        } else {
            false
        }
    };

    // Persist session immediately after adding user message (improves reliability on early errors)
    {
        let manager = state.chat_session_manager.lock().unwrap();
        if let Some(session) = manager.get_active_session() {
            let storage = state.storage.lock().unwrap();
            let _ = storage.save_chat_session(session);
        }
    }

    // Save session if title was updated
    if should_generate_title {
        let manager = state.chat_session_manager.lock().unwrap();
        if let Some(session) = manager.get_active_session() {
            let storage = state.storage.lock().unwrap();
            let _ = storage.save_chat_session(session);
        }
    }

    // Emit start log for agentic workflow
    let session_id_for_logs = {
        let manager = state.chat_session_manager.lock().unwrap();
        manager.get_active_session().map(|s| s.id.clone())
    };
    emit_log(
        &window,
        "info",
        "agent_activity",
        "Agentic processing started",
        Some("Assistant"),
        Some("AgenticWorkflow"),
        Some("processing"),
        session_id_for_logs.clone(),
        Some(json!({ "input_preview": input.chars().take(200).collect::<String>() })),
    );

    // Provide LLM tool streaming context (window + session) for tool-call-delta events
    set_tool_event_context(Some(window.clone()), session_id_for_logs.clone());

    // Get project index
    let project_index = {
        let cached_index = state.project_index.lock().unwrap();
        if let Some(index) = cached_index.as_ref() {
            index.clone()
        } else {
            drop(cached_index);

            // Get Godot executable path if available
            let godot_executable_path = {
                let storage = state.storage.lock().unwrap();
                storage.get_godot_executable_path(&project_path)
            };

            // Use automatic indexing: load from cache if valid, otherwise index
            let index = {
                let storage = state.storage.lock().unwrap();
                ProjectIndexer::index_or_load(&project_path, godot_executable_path, &storage)
                    .map_err(|e| format!("Failed to get project index: {}", e))?
            };

            let mut cached_index = state.project_index.lock().unwrap();
            *cached_index = Some(index.clone());
            index
        }
    };

    // Get chat history
    let chat_history = {
        let manager = state.chat_session_manager.lock().unwrap();
        if let Some(session) = manager.get_active_session() {
            session.build_accumulated_context()
        } else {
            String::new()
        }
    };

    // Get knowledge bases
    let (plugin_kb, docs_kb) = {
        let km = state.knowledge_manager.lock().unwrap();
        let km_ref = km.as_ref().ok_or("Knowledge manager not initialized")?;
        (km_ref.get_plugin_kb(), km_ref.get_docs_kb())
    };

    // Optional: perform a lightweight web search to provide fresh context
    let _web_results_md = {
        let (_prov, key_opt) = {
            let storage = state.storage.lock().unwrap();
            storage.get_web_search_settings()
        };
        let api_key = key_opt.or_else(|| std::env::var("TAVILY_API_KEY").ok());
        if let Some(api_key) = api_key {
            if !api_key.is_empty() {
                emit_log(
                    &window,
                    "info",
                    "tool_call",
                    "Web search started",
                    Some("WebSearch"),
                    Some("web_search"),
                    Some("started"),
                    session_id_for_logs.clone(),
                    Some(json!({"query": input})),
                );
                let client = web_search::TavilyClient::new(api_key);
                match client.search(&input, 3).await {
                    Ok(results) => {
                        web_search_time_ms = Some(results.took_ms as u64);
                        emit_log(
                            &window,
                            "info",
                            "tool_call",
                            "Web search completed",
                            Some("WebSearch"),
                            Some("web_search"),
                            Some("completed"),
                            session_id_for_logs.clone(),
                            Some(
                                json!({"results_count": results.results.len(), "took_ms": results.took_ms}),
                            ),
                        );

                        // Add a system message with results
                        let mut md = String::from("# Web Search Results\n");
                        for (i, item) in results.results.iter().enumerate() {
                            md.push_str(&format!(
                                "{}. {}\n{}\n{}\n\n",
                                i + 1,
                                item.title,
                                item.url,
                                item.snippet
                            ));
                        }
                        {
                            let mut manager = state.chat_session_manager.lock().unwrap();
                            if let Some(session) = manager.get_active_session_mut() {
                                session.add_message(ChatMessage {
                                    id: uuid::Uuid::new_v4().to_string(),
                                    role: chat_session::MessageRole::System,
                                    content: md.clone(),
                                    timestamp: now_millis() as u64 / 1000,
                                    thought_process: None,
                                    context_used: None,
                                    visual_snapshot_b64: None,
                                    visual_snapshot_meta: None,
                                    metrics: None,
                                });
                                let storage = state.storage.lock().unwrap();
                                let _ = storage.save_chat_session(session);
                            }
                        }
                        Some(())
                    }
                    Err(e) => {
                        emit_log(
                            &window,
                            "error",
                            "tool_call",
                            &format!("Web search error: {}", e),
                            Some("WebSearch"),
                            Some("web_search"),
                            Some("error"),
                            session_id_for_logs.clone(),
                            None,
                        );
                        None
                    }
                }
            } else {
                None
            }
        } else {
            None
        }
    };

    // Gather visual context if this is a UI-related task
    let visual_context = {
        let is_ui_task = agent::AgenticWorkflow::is_ui_task(&input);

        if is_ui_task {
            emit_log(
                &window,
                "info",
                "agent_activity",
                "Detected UI task - capturing visual context",
                Some("Assistant"),
                Some("VisualContext"),
                Some("processing"),
                session_id_for_logs.clone(),
                None,
            );

            // Try to capture screenshot from Godot editor
            let (screenshot_b64, screenshot_meta, visual_analysis): (
                Option<String>,
                Option<Value>,
                Option<String>,
            ) = {
                // Clone the client to avoid holding the lock across await
                let client_clone = {
                    let client_opt = state.ws_client.lock().unwrap();
                    client_opt.clone()
                };

                if let Some(client) = client_clone {
                    // Request visual snapshot from Godot
                    match client
                        .send_command(&serde_json::json!({"action": "get_visual_snapshot"}))
                        .await
                    {
                        Ok(snapshot)
                            if snapshot.get("status").and_then(|s| s.as_str())
                                == Some("success") =>
                        {
                            if let Some(data) = snapshot.get("data") {
                                let image_b64: Option<String> = data
                                    .get("image_b64")
                                    .and_then(|v| v.as_str())
                                    .map(|s| s.to_string());
                                let meta: Option<Value> = data.get("meta").cloned();

                                // Visual analysis handled by Vision agent; no inline call here
                                let analysis: Option<String> = None;

                                (image_b64, meta, analysis)
                            } else {
                                (None, None, None)
                            }
                        }
                        _ => (None, None, None),
                    }
                } else {
                    (None, None, None)
                }
            };

            agent::VisualContext {
                _screenshot_base64: screenshot_b64,
                _screenshot_metadata: screenshot_meta,
                visual_analysis,
                is_ui_task: true,
            }
        } else {
            agent::VisualContext::default()
        }
    };

    // Create agent context
    let agent_context = agent::AgentContext {
        user_input: input.clone(),
        project_index,
        chat_history,
        plugin_kb,
        docs_kb,
        visual_context,
    };

    // Execute agentic workflow
    let workflow = {
        let workflow_guard = state.agentic_workflow.lock().unwrap();
        match workflow_guard.as_ref() {
            Some(w) => w.clone(),
            None => return Err("Agentic workflow not initialized".to_string()),
        }
    };

    // Choose backend: Letta (stateful agents) or Strands (legacy)
    let backend = std::env::var("AGENT_BACKEND")
        .unwrap_or_else(|_| "strands".to_string())
        .to_lowercase();

    let agent_response = {
        if backend == "letta" {
            let backend_client = match LettaBackend::new_from_env() {
                Ok(b) => b,
                Err(e) => {
                    emit_log(
                        &window,
                        "error",
                        "agent_activity",
                        &format!("Letta config error: {}", e),
                        Some("LettaBackend"),
                        Some("Init"),
                        Some("error"),
                        session_id_for_logs.clone(),
                        None,
                    );
                    {
                        let mut manager = state.chat_session_manager.lock().unwrap();
                        if let Some(session) = manager.get_active_session_mut() {
                            let mut msg = ChatMessage::assistant(
                                format!("Letta not configured: {}", e),
                                None,
                                None,
                                None,
                                None,
                            );
                            msg.metrics = Some(chat_session::MessageMetrics {
                                input_tokens: 0,
                                output_tokens: 0,
                                total_tokens: 0,
                                latency_ms: processing_start.elapsed().as_millis() as u64,
                                tool_call_times: {
                                    let mut v = Vec::new();
                                    if let Some(ms) = web_search_time_ms {
                                        v.push(chat_session::ToolCallMetric {
                                            name: "web_search".into(),
                                            duration_ms: ms,
                                        });
                                    }
                                    v
                                },
                                cost_estimate_usd: None,
                            });
                            session.add_message(msg);
                            let storage = state.storage.lock().unwrap();
                            let _ = storage.save_chat_session(session);
                        }
                    }
                    return Err(format!("Letta not configured: {}", e));
                }
            };
            let existing_letta_agent_id: Option<String> = {
                let manager = state.chat_session_manager.lock().unwrap();
                manager
                    .get_active_session()
                    .and_then(|s| s.letta_agent_id.clone())
            };
            match backend_client
                .execute(
                    &window,
                    session_id_for_logs.as_deref(),
                    &agent_context,
                    existing_letta_agent_id.as_deref(),
                )
                .await
            {
                Ok((r, used_agent_id)) => {
                    // Persist agent id for this session
                    if let Ok(mut manager) = state.chat_session_manager.lock() {
                        if let Some(session) = manager.get_active_session_mut() {
                            session.letta_agent_id = Some(used_agent_id.clone());
                            let storage = state.storage.lock().unwrap();
                            let _ = storage.save_chat_session(session);
                        }
                    }
                    r
                }
                Err(e) => {
                    emit_log(
                        &window,
                        "error",
                        "agent_activity",
                        &format!("Letta workflow failed: {}", e),
                        Some("LettaBackend"),
                        Some("Execute"),
                        Some("error"),
                        session_id_for_logs.clone(),
                        None,
                    );
                    {
                        let mut manager = state.chat_session_manager.lock().unwrap();
                        if let Some(session) = manager.get_active_session_mut() {
                            let mut msg = ChatMessage::assistant(
                                format!("Letta workflow failed: {}", e),
                                None,
                                None,
                                None,
                                None,
                            );
                            msg.metrics = Some(chat_session::MessageMetrics {
                                input_tokens: 0,
                                output_tokens: 0,
                                total_tokens: 0,
                                latency_ms: processing_start.elapsed().as_millis() as u64,
                                tool_call_times: {
                                    let mut v = Vec::new();
                                    if let Some(ms) = web_search_time_ms {
                                        v.push(chat_session::ToolCallMetric {
                                            name: "web_search".into(),
                                            duration_ms: ms,
                                        });
                                    }
                                    v
                                },
                                cost_estimate_usd: None,
                            });
                            session.add_message(msg);
                            let storage = state.storage.lock().unwrap();
                            let _ = storage.save_chat_session(session);
                        }
                    }
                    return Err(format!("Letta workflow failed: {}", e));
                }
            }
        } else {
            match workflow.execute(&agent_context).await {
                Ok(r) => r,
                Err(e) => {
                    emit_log(
                        &window,
                        "error",
                        "agent_activity",
                        &format!("Agentic workflow failed: {}", e),
                        Some("AgenticWorkflow"),
                        Some("Execute"),
                        Some("error"),
                        session_id_for_logs.clone(),
                        None,
                    );
                    {
                        let mut manager = state.chat_session_manager.lock().unwrap();
                        if let Some(session) = manager.get_active_session_mut() {
                            let mut msg = ChatMessage::assistant(
                                format!("Agentic workflow failed: {}", e),
                                None,
                                None,
                                None,
                                None,
                            );
                            msg.metrics = Some(chat_session::MessageMetrics {
                                input_tokens: 0,
                                output_tokens: 0,
                                total_tokens: 0,
                                latency_ms: processing_start.elapsed().as_millis() as u64,
                                tool_call_times: {
                                    let mut v = Vec::new();
                                    if let Some(ms) = web_search_time_ms {
                                        v.push(chat_session::ToolCallMetric {
                                            name: "web_search".into(),
                                            duration_ms: ms,
                                        });
                                    }
                                    v
                                },
                                cost_estimate_usd: None,
                            });
                            session.add_message(msg);
                            let storage = state.storage.lock().unwrap();
                            let _ = storage.save_chat_session(session);
                        }
                    }
                    return Err(format!("Agentic workflow failed: {}", e));
                }
            }
        }
    };

    // Emit metrics snapshot and warnings if any
    if let Some(m) = agent_response.metrics.as_ref() {
        emit_log(
            &window,
            "debug",
            "agent_activity",
            "Metrics snapshot",
            Some("Metrics"),
            Some("AgenticWorkflow"),
            Some("processing"),
            session_id_for_logs.clone(),
            Some(json!({
                "total_time_ms": m.total_time_ms,
                "total_tokens": m.total_tokens,
                "commands_generated": m.commands_generated,
                "commands_validated": m.commands_validated,
                "validation_warnings": m.validation_warnings,
                "validation_errors": m.validation_errors,
                "success": m.success
            })),
        );
        if m.validation_warnings > 0 {
            emit_log(
                &window,
                "warning",
                "agent_activity",
                &format!("Validation warnings detected: {}", m.validation_warnings),
                Some("Validation"),
                Some("AgenticWorkflow"),
                Some("warning"),
                session_id_for_logs.clone(),
                None,
            );
        }
    }

    // Emit agentic plan summary
    emit_log(
        &window,
        "info",
        "agent_activity",
        &format!(
            "Agentic plan ready: {} command(s)",
            agent_response.commands.len()
        ),
        Some("Assistant"),
        Some("AgenticWorkflow"),
        Some("processing"),
        session_id_for_logs.clone(),
        Some(json!({ "count": agent_response.commands.len() })),
    );

    // Execute commands
    let client = {
        let ws_client = state.ws_client.lock().unwrap();
        ws_client.as_ref().ok_or("Not connected to Godot")?.clone()
    };

    let mut results = Vec::new();
    for (idx, cmd) in agent_response.commands.iter().enumerate() {
        // Log agentic command execution
        let action_name = cmd
            .get("action")
            .and_then(|a| a.as_str())
            .unwrap_or("unknown");
        emit_log(
            &window,
            "info",
            "action",
            &format!("Executing command {}: {}", idx + 1, action_name),
            Some("GodotBridge"),
            Some("Execute"),
            Some("processing"),
            session_id_for_logs.clone(),
            Some(json!({ "index": idx + 1, "action": action_name, "command": cmd })),
        );

        println!(
            "Executing command {}: {}",
            idx + 1,
            serde_json::to_string(cmd).unwrap_or_default()
        );

        let result = client
            .send_command(cmd)
            .await
            .map_err(|e| format!("Failed to send command: {}", e))?;

        // Log command result
        let resp_preview = result.to_string().chars().take(300).collect::<String>();
        let level = if result.get("error").is_some() {
            "error"
        } else {
            "debug"
        };
        emit_log(
            &window,
            level,
            "action",
            &format!("Command {} response", idx + 1),
            Some("GodotBridge"),
            Some("Execute"),
            Some(if level == "error" {
                "failed"
            } else {
                "completed"
            }),
            session_id_for_logs.clone(),
            Some(json!({ "index": idx + 1, "response_preview": resp_preview })),
        );
        results.push(result);
    }

    // Emit agentic completion log
    emit_log(
        &window,
        "info",
        "agent_activity",
        &format!(
            "Agentic workflow completed: {} command(s) executed",
            results.len()
        ),
        Some("Assistant"),
        Some("AgenticWorkflow"),
        Some("completed"),
        session_id_for_logs.clone(),
        Some(json!({ "executed": results.len() })),
    );

    // Add assistant message to session with thoughts
    {
        let mut manager = state.chat_session_manager.lock().unwrap();
        if let Some(session) = manager.get_active_session_mut() {
            let response_text = format!(
                "Executed {} commands.\n\nPlan:\n{}\n\nThoughts:\n{}",
                agent_response.commands.len(),
                agent_response.plan.reasoning,
                agent_response
                    .thoughts
                    .iter()
                    .map(|t| format!("Step {}: {}", t.step, t.thought))
                    .collect::<Vec<_>>()
                    .join("\n")
            );

            let now = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs();

            let mut msg = ChatMessage::assistant(
                response_text,
                Some(
                    agent_response
                        .thoughts
                        .iter()
                        .map(|t| chat_session::ThoughtStep {
                            step_number: t.step,
                            description: t.thought.clone(),
                            reasoning: t.action.clone().unwrap_or_default(),
                            timestamp: now,
                        })
                        .collect(),
                ),
                None,
                None,
                None,
            );
            // Attach per-message metrics extracted from workflow + timings
            msg.metrics = Some(chat_session::MessageMetrics {
                input_tokens: agent_response
                    .metrics
                    .as_ref()
                    .map(|m| m.total_tokens)
                    .unwrap_or(0),
                output_tokens: 0,
                total_tokens: agent_response
                    .metrics
                    .as_ref()
                    .map(|m| m.total_tokens)
                    .unwrap_or(0),
                latency_ms: processing_start.elapsed().as_millis() as u64,
                tool_call_times: {
                    let mut v = Vec::new();
                    if let Some(ms) = web_search_time_ms {
                        v.push(chat_session::ToolCallMetric {
                            name: "web_search".into(),
                            duration_ms: ms,
                        });
                    }
                    v
                },
                cost_estimate_usd: None,
            });
            session.add_message(msg);
        }
    }

    // Save session
    {
        let manager = state.chat_session_manager.lock().unwrap();
        if let Some(session) = manager.get_active_session() {
            let storage = state.storage.lock().unwrap();
            let _ = storage.save_chat_session(session);
        }
    }

    Ok(format!(
        "Agentic workflow completed: {} commands executed",
        results.len()
    ))
}

/// Get all workflow metrics
#[tauri::command]
async fn get_workflow_metrics(
    state: State<'_, AppState>,
) -> Result<Vec<crate::metrics::WorkflowMetrics>, String> {
    let metrics_store = {
        let store = state.metrics_store.lock().unwrap();
        store.clone().ok_or("Metrics store not initialized")?
    };

    let all_metrics = metrics_store.get_all_metrics().await;
    Ok(all_metrics)
}

/// Get metrics summary
#[tauri::command]
async fn get_metrics_summary(
    state: State<'_, AppState>,
) -> Result<crate::metrics::MetricsSummary, String> {
    let metrics_store = {
        let store = state.metrics_store.lock().unwrap();
        store.clone().ok_or("Metrics store not initialized")?
    };

    let summary = metrics_store.get_summary().await;
    Ok(summary)
}

/// Clear all metrics
#[tauri::command]
async fn clear_metrics(state: State<'_, AppState>) -> Result<String, String> {
    // Clear by creating a new store
    let storage_dir = storage::Storage::get_config_dir()
        .map_err(|e| format!("Failed to get config dir: {}", e))?;
    let new_store = MetricsStore::new(storage_dir);

    let mut store = state.metrics_store.lock().unwrap();
    *store = Some(new_store);

    Ok("Metrics cleared".to_string())
}

// Agent LLM Configuration Commands

/// Get the current agent LLM configuration
#[tauri::command]
fn get_agent_llm_config(state: State<'_, AppState>) -> Result<AgentLlmConfig, String> {
    let config = state.agent_llm_config.lock().unwrap();
    Ok(config.clone())
}

/// Save agent LLM configuration
#[tauri::command]
fn save_agent_llm_config(config: AgentLlmConfig, state: State<'_, AppState>) -> Result<(), String> {
    // Update in-memory config
    {
        let mut current_config = state.agent_llm_config.lock().unwrap();
        *current_config = config.clone();
    }

    // Save to disk
    let storage = state.storage.lock().unwrap();
    storage
        .save_agent_llm_config(&config)
        .map_err(|e| format!("Failed to save agent LLM config: {}", e))
}

/// Get API keys (returns the store structure, but actual keys should be masked in production)
#[tauri::command]
fn get_api_keys(state: State<'_, AppState>) -> Result<ApiKeyStore, String> {
    let keys = state.api_key_store.lock().unwrap();
    Ok(keys.clone())
}

/// Save API keys
#[tauri::command]
fn save_api_keys(keys: ApiKeyStore, state: State<'_, AppState>) -> Result<(), String> {
    // Update in-memory store
    {
        let mut current_keys = state.api_key_store.lock().unwrap();
        *current_keys = keys.clone();
    }

    // Save to disk
    let storage = state.storage.lock().unwrap();
    storage
        .save_api_keys(&keys)
        .map_err(|e| format!("Failed to save API keys: {}", e))
}

/// Get available models for each provider
#[tauri::command]
fn get_available_models() -> Result<HashMap<llm_config::LlmProvider, Vec<String>>, String> {
    Ok(llm_config::get_available_models())
}

/// Trigger automatic indexing on application startup
/// This function checks if a project path is configured and if indexing hasn't started yet
fn trigger_automatic_indexing_on_startup(app: &tauri::App) {
    // Get the app state
    let state = app.state::<AppState>();

    // Check if a project path is already configured
    let project_path_opt = {
        let storage = state.storage.lock().unwrap();
        storage.get_project_path()
    };

    if let Some(project_path) = project_path_opt {
        // Check if indexing status is NotStarted
        let should_index = {
            let status = state.indexing_status.lock().unwrap();
            matches!(*status, IndexingStatus::NotStarted)
        };

        if should_index {
            println!(
                "Triggering automatic indexing on startup for project: {}",
                project_path
            );

            // Set the project path in memory
            {
                let mut path = state.godot_project_path.lock().unwrap();
                *path = Some(project_path.clone());
            }

            // Set status to Indexing
            {
                let mut status = state.indexing_status.lock().unwrap();
                *status = IndexingStatus::Indexing;
            }

            // Get the main window to emit events
            if let Some(window) = app.get_webview_window("main") {
                // Emit initial indexing status
                let _ = window.emit(
                    "indexing-status-changed",
                    json!({
                        "projectPath": Some(project_path.clone()),
                        "status": IndexingStatus::Indexing
                    }),
                );

                // Trigger background indexing using tauri's async runtime
                let state_clone = state.inner().clone();
                let path_clone = project_path.clone();

                tauri::async_runtime::spawn(async move {
                    perform_background_indexing(window, path_clone, state_clone).await;
                });
            } else {
                println!("Warning: Could not get main window for indexing events");
            }
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(AppState::default())
        .setup(|app| {
            // Trigger automatic indexing on startup
            trigger_automatic_indexing_on_startup(app);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            connect_to_godot,
            process_command,
            process_command_agentic,
            initialize_knowledge_bases,
            get_api_key,
            save_api_key,
            set_godot_project_path,
            get_godot_project_path,
            get_indexing_status,
            set_godot_executable_path,
            get_godot_executable_path,
            get_godot_executable_for_current_project,
            remove_godot_executable_path,
            refresh_project_index,
            clear_cache,
            get_cache_status,
            create_chat_session,
            get_active_session,
            get_all_sessions,
            set_active_session,
            delete_session,
            clear_all_sessions,
            update_session_title,
            append_system_message,
            get_workflow_metrics,
            get_metrics_summary,
            clear_metrics,
            get_agent_llm_config,
            save_agent_llm_config,
            get_api_keys,
            save_api_keys,
            get_available_models,
            get_web_search_settings,
            save_web_search_settings,
            tool_web_search
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
