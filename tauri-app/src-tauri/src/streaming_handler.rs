use crate::streaming_agent::StreamingAgentResponse;
use crate::strands_agent::{OrchestratorAgent, AgentExecutionContext};
use crate::agent_loop::{AgentLoop, AgentLoopConfig};
use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::{mpsc, RwLock};
use uuid::Uuid;

/// Manages active streaming sessions
pub struct StreamingSessionManager {
    sessions: Arc<RwLock<HashMap<String, StreamingSession>>>,
}

/// Represents an active streaming session
pub struct StreamingSession {
    #[allow(dead_code)] // Session identifier for management
    pub id: String,
    pub sender: mpsc::UnboundedSender<StreamingAgentResponse>,
    #[allow(dead_code)] // Creation timestamp for session cleanup
    pub created_at: std::time::SystemTime,
}

/// Request to start a streaming agent execution
#[derive(Debug, Deserialize)]
pub struct StreamingExecuteRequest {
    /// Session identifier (optional, will generate if not provided)
    pub session_id: Option<String>,
    /// User input to process
    pub user_input: String,
    /// Project context
    pub project_context: String,
    /// Project path for dynamic context
    pub project_path: String,
    /// Chat history (optional)
    #[allow(dead_code)] // Future enhancement: Conversation context
    pub chat_history: Option<String>,
    /// Whether to use streaming mode
    pub use_streaming: Option<bool>,
}

/// Response for streaming execution
#[derive(Debug, Serialize)]
pub struct StreamingExecuteResponse {
    /// Session identifier
    pub session_id: String,
    /// Whether streaming is enabled
    pub streaming_enabled: bool,
    /// Initial message
    pub message: String,
}

impl StreamingSessionManager {
    pub fn new() -> Self {
        Self {
            sessions: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Create a new streaming session
    pub async fn create_session(&self) -> Result<String> {
        let session_id = Uuid::new_v4().to_string();
        let (sender, _receiver) = mpsc::unbounded_channel();

        let session = StreamingSession {
            id: session_id.clone(),
            sender,
            created_at: std::time::SystemTime::now(),
        };

        self.sessions.write().await.insert(session_id.clone(), session);
        Ok(session_id)
    }

    /// Get a session's sender for streaming responses
    pub async fn get_session_sender(&self, session_id: &str) -> Option<mpsc::UnboundedSender<StreamingAgentResponse>> {
        self.sessions.read().await.get(session_id).map(|s| s.sender.clone())
    }

    /// Remove a session
    #[allow(dead_code)] // Session management for streaming cleanup
    pub async fn remove_session(&self, session_id: &str) -> bool {
        self.sessions.write().await.remove(session_id).is_some()
    }

    /// Clean up old sessions (older than 1 hour)
    #[allow(dead_code)] // Session hygiene for streaming management
    pub async fn cleanup_old_sessions(&self) -> usize {
        let now = std::time::SystemTime::now();
        let hour_ago = now.duration_since(std::time::UNIX_EPOCH).unwrap()
            .as_secs() - 3600;

        let mut sessions = self.sessions.write().await;
        let initial_count = sessions.len();

        sessions.retain(|_, session| {
            session.created_at.duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs() > hour_ago
        });

        initial_count - sessions.len()
    }

    /// Execute agent with streaming support
    pub async fn execute_agent_streaming(
        &self,
        request: StreamingExecuteRequest,
        api_key: &str,
    ) -> Result<StreamingExecuteResponse> {
        let session_id = request.session_id.unwrap_or_else(|| Uuid::new_v4().to_string());
        let streaming_enabled = request.use_streaming.unwrap_or(true);

        // Create session if it doesn't exist
        if self.sessions.read().await.get(&session_id).is_none() {
            self.create_session().await?;
        }

        // Get the session sender
        let sender = self.get_session_sender(&session_id).await
            .ok_or_else(|| anyhow::anyhow!("Failed to get session sender"))?;

        // Create agent context
        let context = AgentExecutionContext {
            user_input: request.user_input.clone(),
            project_context: request.project_context,
            previous_output: None,
            dynamic_context_provider: None,
            project_path: Some(request.project_path),
        };

        // If streaming is enabled, start streaming execution using AgentLoop
        if streaming_enabled {
            let orchestrator = OrchestratorAgent::new(api_key);
            let session_id_clone = session_id.clone();

            // Create AgentLoop with configuration
            let loop_config = AgentLoopConfig {
                max_iterations: 15,
                adaptive_reasoning: true,
                min_confidence_threshold: 0.8,
                auto_execute_tools: true,
                iteration_timeout_ms: 30000,
            };

            // Spawn streaming task with AgentLoop
            tokio::spawn(async move {
                let mut agent_loop = AgentLoop::new(context, Some(loop_config));

                if let Err(e) = agent_loop.execute_streaming(&orchestrator, sender, session_id_clone).await {
                    tracing::error!("Agent loop streaming execution failed: {}", e);
                }
            });
        }

        Ok(StreamingExecuteResponse {
            session_id,
            streaming_enabled,
            message: if streaming_enabled {
                "Streaming execution started".to_string()
            } else {
                "Non-streaming execution not yet implemented".to_string()
            },
        })
    }
}

/// Tauri command to start streaming agent execution
#[tauri::command]
pub async fn start_agent_streaming(
    request: StreamingExecuteRequest,
    app_state: tauri::State<'_, crate::AppState>,
    session_manager: tauri::State<'_, StreamingSessionManager>,
) -> Result<StreamingExecuteResponse, String> {
    // Get API key from the state
    let api_key = {
        let store = app_state.api_key_store.lock().unwrap();
        if let Some(k) = store.get_key(&crate::llm_config::LlmProvider::OpenRouter) {
            k.clone()
        } else {
            let storage = app_state.storage.lock().unwrap();
            storage.get_api_key().ok_or("API key not configured")?
        }
    };

    session_manager.execute_agent_streaming(request, &api_key)
        .await
        .map_err(|e| format!("Failed to start streaming execution: {}", e))
}

/// Tauri command to subscribe to streaming responses (returns SSE endpoint)
#[tauri::command]
pub async fn get_streaming_endpoint(
    session_id: String,
    session_manager: tauri::State<'_, StreamingSessionManager>,
) -> Result<String, String> {
    // Check if session exists
    if session_manager.sessions.read().await.get(&session_id).is_none() {
        return Err("Session not found".to_string());
    }

    Ok(format!("/agent-stream/{}", session_id))
}