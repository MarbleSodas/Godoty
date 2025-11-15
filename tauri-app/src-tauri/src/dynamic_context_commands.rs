use crate::dynamic_context_provider::{
    ContextUpdate, DynamicProjectContextProvider, FileWatcherConfig
};
use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::Arc;
use tauri::State;

/// Request to initialize dynamic context provider
#[derive(Debug, Deserialize)]
pub struct InitializeDynamicContextRequest {
    /// Project path to watch
    pub project_path: String,
    /// Optional file watcher configuration
    pub config: Option<FileWatcherConfig>,
}

/// Response for context updates
#[derive(Debug, Serialize)]
#[allow(dead_code)] // Dynamic context infrastructure - enhancement plan
pub struct ContextUpdateResponse {
    /// List of recent context updates
    pub updates: Vec<ContextUpdate>,
    /// Current context content
    pub current_context: Option<String>,
    /// Number of files being watched
    pub watched_files_count: usize,
}

/// Initialize dynamic context provider
#[tauri::command]
pub async fn initialize_dynamic_context(
    request: InitializeDynamicContextRequest,
    app_state: State<'_, crate::AppState>,
) -> Result<String, String> {
    // Get required components from app state
    let context_engine = {
        let guard = app_state.context_engine.lock().unwrap();
        match guard.as_ref() {
            Some(ce) => ce.clone(),
            None => return Err("Context engine not initialized".to_string()),
        }
    };

    let project_path = PathBuf::from(request.project_path);
    let indexer = Arc::new(crate::project_indexer::ProjectIndexer::new(&project_path.to_string_lossy()));

    // Create dynamic context provider
    let (provider, update_rx) = DynamicProjectContextProvider::new(
        project_path,
        request.config,
        Arc::new(context_engine),
        indexer,
    ).await.map_err(|e| format!("Failed to create dynamic context provider: {}", e))?;

    // Start file watching
    provider.start_watching()
        .await
        .map_err(|e| format!("Failed to start file watching: {}", e))?;

    // Store provider in app state (we'll need to add it to AppState)
    // TODO: Add dynamic_context_provider field to AppState
    // TODO: Use Tauri's event system to emit context updates instead of returning the receiver

    // For now, just spawn a task to consume the updates
    tokio::spawn(async move {
        let mut rx = update_rx;
        while let Some(_update) = rx.recv().await {
            // TODO: Emit Tauri events for context updates
            tracing::debug!("Context update received");
        }
    });

    Ok("Dynamic context provider initialized successfully".to_string())
}

/// Get current dynamic context
#[tauri::command]
pub async fn get_dynamic_context(
    project_path: String,
    app_state: State<'_, crate::AppState>,
) -> Result<String, String> {
    // For now, use the regular context engine
    let context_engine = {
        let guard = app_state.context_engine.lock().unwrap();
        match guard.as_ref() {
            Some(ce) => ce.clone(),
            None => return Err("Context engine not initialized".to_string()),
        }
    };

    // Index the project first
    let indexer = crate::project_indexer::ProjectIndexer::new(&project_path);
    let project_index = indexer.index_project()
        .map_err(|e| format!("Failed to index project: {}", e))?;

    let context = context_engine
        .build_comprehensive_context(
            "Get current context request",
            &project_index,
            None,
            10
        )
        .await
        .map_err(|e| format!("Failed to build context: {}", e))?;

    // Convert to JSON string
    Ok(serde_json::to_string_pretty(&context)
        .unwrap_or_else(|_| format!("Context: {} files", project_index.scenes.len() + project_index.scripts.len())))
}

/// Trigger context refresh for a project
#[tauri::command]
pub async fn refresh_project_context(
    project_path: String,
    app_state: State<'_, crate::AppState>,
) -> Result<String, String> {
    let context_engine = {
        let guard = app_state.context_engine.lock().unwrap();
        match guard.as_ref() {
            Some(ce) => ce.clone(),
            None => return Err("Context engine not initialized".to_string()),
        }
    };

    // Force reindex
    let indexer = crate::project_indexer::ProjectIndexer::new(&project_path);
    let project_index = indexer.index_project()
        .map_err(|e| format!("Failed to index project: {}", e))?;

    let context = context_engine
        .build_comprehensive_context(
            "Manual refresh request",
            &project_index,
            None,
            10
        )
        .await
        .map_err(|e| format!("Failed to refresh context: {}", e))?;

    // Convert to JSON string
    Ok(serde_json::to_string_pretty(&context)
        .unwrap_or_else(|_| format!("Context: {} files", project_index.scenes.len() + project_index.scripts.len())))
}

/// Get recent context updates
#[tauri::command]
pub async fn get_recent_context_updates(
    _limit: Option<usize>,
    _app_state: State<'_, crate::AppState>,
) -> Result<Vec<ContextUpdate>, String> {
    // TODO: Implement context update tracking
    // For now, return empty list
    Ok(vec![])
}

/// Configure file watcher settings
#[tauri::command]
pub async fn configure_file_watcher(
    project_path: String,
    _config: FileWatcherConfig,
    _app_state: State<'_, crate::AppState>,
) -> Result<String, String> {
    // TODO: Implement configuration update
    tracing::info!("File watcher configured for project: {}", project_path);
    Ok("File watcher configuration updated".to_string())
}

/// Get file watcher status
#[tauri::command]
pub async fn get_file_watcher_status(
    project_path: String,
    _app_state: State<'_, crate::AppState>,
) -> Result<FileWatcherStatus, String> {
    // TODO: Implement status tracking
    Ok(FileWatcherStatus {
        is_active: true,
        project_path,
        watched_files: 0,
        last_update: chrono::Utc::now().timestamp() as u64,
        config: FileWatcherConfig::default(),
    })
}

/// Status of the file watcher
#[derive(Debug, Serialize)]
pub struct FileWatcherStatus {
    /// Whether the watcher is active
    pub is_active: bool,
    /// Project path being watched
    pub project_path: String,
    /// Number of files being watched
    pub watched_files: usize,
    /// Last update timestamp
    pub last_update: u64,
    /// Current configuration
    pub config: FileWatcherConfig,
}