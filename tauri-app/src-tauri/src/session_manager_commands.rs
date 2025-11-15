use crate::chat_session::ChatMessage;
use crate::session_manager::{ConversationManagerType, FileSessionManager};
use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::Arc;
use tauri::State;

/// Request to create a new file session
#[derive(Debug, Deserialize)]
pub struct CreateFileSessionRequest {
    /// Project path associated with the session
    pub project_path: Option<String>,
    /// Initial system context
    pub initial_context: Option<String>,
    /// Conversation manager type
    #[allow(dead_code)] // Future session management configuration
    pub conversation_manager: ConversationManagerType,
}

/// Response containing session ID
#[derive(Debug, Serialize)]
pub struct CreateFileSessionResponse {
    /// The created session ID
    pub session_id: String,
}

/// Request to add a message to a session
#[derive(Debug, Deserialize)]
pub struct AddSessionMessageRequest {
    /// Session ID
    pub session_id: String,
    /// Message to add
    pub message: ChatMessage,
}

/// Response with conversation context
#[derive(Debug, Serialize)]
pub struct GetConversationContextResponse {
    /// Messages for LLM context
    pub messages: Vec<ChatMessage>,
    /// Current message count
    pub message_count: usize,
    /// Conversation summary if available
    pub summary: Option<String>,
}

/// Get session manager, initializing if needed
async fn get_session_manager(
    app_state: State<'_, crate::AppState>,
) -> Result<Arc<FileSessionManager>, String> {
    // Check if session manager exists
    {
        let guard = app_state.file_session_manager.lock().unwrap();
        if let Some(sm) = guard.as_ref() {
            return Ok(sm.clone());
        }
    } // Lock released

    // Initialize session manager
    let sessions_dir = crate::storage::Storage::get_config_dir()
        .map_err(|e| format!("Failed to get config directory: {}", e))?
        .join("sessions");

    let manager = FileSessionManager::new(
        sessions_dir,
        ConversationManagerType::SlidingWindow { max_messages: 50 },
    ).await.map_err(|e| format!("Failed to create session manager: {}", e))?;

    // Store in state
    {
        let mut guard = app_state.file_session_manager.lock().unwrap();
        *guard = Some(Arc::new(manager.clone()));
    }

    Ok(Arc::new(manager))
}

/// Create a new file-based session
#[tauri::command]
pub async fn create_file_session(
    request: CreateFileSessionRequest,
    app_state: State<'_, crate::AppState>,
) -> Result<CreateFileSessionResponse, String> {
    let session_manager = get_session_manager(app_state).await?;

    let session_id = session_manager.create_session(
        request.project_path,
        request.initial_context,
    ).await.map_err(|e| format!("Failed to create session: {}", e))?;

    Ok(CreateFileSessionResponse { session_id })
}

/// Get a file session by ID
#[tauri::command]
pub async fn get_file_session(
    session_id: String,
    app_state: State<'_, crate::AppState>,
) -> Result<Option<crate::session_manager::PersistedSession>, String> {
    let session_manager = get_session_manager(app_state).await?;
    session_manager.get_session(&session_id)
        .await
        .map_err(|e| format!("Failed to get session: {}", e))
}

/// Update a file session
#[tauri::command]
pub async fn update_file_session(
    session_id: String,
    session: crate::session_manager::PersistedSession,
    app_state: State<'_, crate::AppState>,
) -> Result<(), String> {
    let session_manager = get_session_manager(app_state).await?;

    session_manager.update_session(&session_id, &session)
        .await
        .map_err(|e| format!("Failed to update session: {}", e))
}

/// List all file sessions
#[tauri::command]
pub async fn list_file_sessions(
    app_state: State<'_, crate::AppState>,
) -> Result<Vec<crate::session_manager::SessionMetadata>, String> {
    let session_manager = get_session_manager(app_state).await?;

    session_manager.list_sessions()
        .await
        .map_err(|e| format!("Failed to list sessions: {}", e))
}

/// Delete a file session
#[tauri::command]
pub async fn delete_file_session(
    session_id: String,
    app_state: State<'_, crate::AppState>,
) -> Result<(), String> {
    let session_manager = get_session_manager(app_state).await?;

    session_manager.delete_session(&session_id)
        .await
        .map_err(|e| format!("Failed to delete session: {}", e))
}

/// Archive a file session
#[tauri::command]
pub async fn archive_file_session(
    session_id: String,
    app_state: State<'_, crate::AppState>,
) -> Result<(), String> {
    let session_manager = get_session_manager(app_state).await?;

    session_manager.archive_session(&session_id)
        .await
        .map_err(|e| format!("Failed to archive session: {}", e))
}

/// Add a message to a session
#[tauri::command]
pub async fn add_session_message(
    request: AddSessionMessageRequest,
    app_state: State<'_, crate::AppState>,
) -> Result<(), String> {
    let session_manager = get_session_manager(app_state).await?;

    session_manager.add_message(&request.session_id, request.message)
        .await
        .map_err(|e| format!("Failed to add message: {}", e))
}

/// Get conversation context for a session
#[tauri::command]
pub async fn get_conversation_context(
    session_id: String,
    max_tokens: Option<usize>,
    app_state: State<'_, crate::AppState>,
) -> Result<GetConversationContextResponse, String> {
    let session_manager = get_session_manager(app_state).await?;

    let conversation_manager = session_manager.get_conversation_manager(&session_id)
        .await
        .map_err(|e| format!("Failed to get conversation manager: {}", e))?;

    let messages = conversation_manager.get_context_messages(max_tokens)
        .await
        .map_err(|e| format!("Failed to get context messages: {}", e))?;

    let message_count = conversation_manager.get_message_count().await;
    let summary = conversation_manager.get_summary()
        .await
        .map_err(|e| format!("Failed to get summary: {}", e))?;

    Ok(GetConversationContextResponse {
        messages,
        message_count,
        summary,
    })
}

/// Cleanup old sessions
#[tauri::command]
pub async fn cleanup_old_sessions(
    days_old: u64,
    app_state: State<'_, crate::AppState>,
) -> Result<usize, String> {
    let session_manager = get_session_manager(app_state).await?;

    session_manager.cleanup_old_sessions(days_old)
        .await
        .map_err(|e| format!("Failed to cleanup old sessions: {}", e))
}

/// Initialize session manager with custom configuration
#[tauri::command]
pub async fn initialize_session_manager(
    sessions_dir: Option<String>,
    conversation_manager: ConversationManagerType,
    app_state: State<'_, crate::AppState>,
) -> Result<(), String> {
    // Determine sessions directory
    let sessions_path = if let Some(dir) = sessions_dir {
        PathBuf::from(dir)
    } else {
        crate::storage::Storage::get_config_dir()
            .map_err(|e| format!("Failed to get config directory: {}", e))?
            .join("sessions")
    };

    // Create new session manager
    let manager = FileSessionManager::new(sessions_path, conversation_manager)
        .await
        .map_err(|e| format!("Failed to create session manager: {}", e))?;

    // Update the session manager in state
    {
        let mut session_manager_guard = app_state.file_session_manager.lock().unwrap();
        *session_manager_guard = Some(Arc::new(manager));
    }

    Ok(())
}