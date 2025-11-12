use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::time::SystemTime;
use uuid::Uuid;

/// Represents a single message in a chat session
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatMessage {
    pub id: String,
    pub role: MessageRole,
    pub content: String,
    pub timestamp: u64,
    pub thought_process: Option<Vec<ThoughtStep>>,
    pub context_used: Option<ContextSnapshot>,
    // Optional visual snapshot attached to this message (base64 PNG + metadata)
    pub visual_snapshot_b64: Option<String>,
    pub visual_snapshot_meta: Option<serde_json::Value>,
    #[serde(default)]
    pub metrics: Option<MessageMetrics>,
}

/// Role of the message sender
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum MessageRole {
    User,
    Assistant,
    System,
}

/// Represents a single step in the AI's thought process
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThoughtStep {
    pub step_number: usize,
    pub description: String,
    pub reasoning: String,
    pub timestamp: u64,
}

/// Snapshot of context used for a particular message
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextSnapshot {
    pub godot_docs_used: bool,
    pub project_files_referenced: Vec<String>,
    pub previous_messages_count: usize,
    pub total_context_size: usize,
    #[serde(default)]
    pub visual_analysis_used: bool,
}

/// Represents a complete chat session
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatSession {
    pub id: String,
    pub title: String,
    pub messages: Vec<ChatMessage>,
    pub created_at: u64,
    pub updated_at: u64,
    pub project_path: Option<String>,
    pub metadata: SessionMetadata,
}

/// Metadata about the session
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionMetadata {
    pub total_commands: usize,

    pub successful_commands: usize,
    pub failed_commands: usize,
    pub total_tokens_used: usize,
    #[serde(default)]
    pub total_cost_usd: f64,
}

impl ChatSession {
    /// Create a new chat session
    pub fn new(title: Option<String>, project_path: Option<String>) -> Self {
        let now = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .unwrap()
            .as_secs();

        Self {
            id: Uuid::new_v4().to_string(),
            title: title.unwrap_or_else(|| format!("Session {}", now)),
            messages: Vec::new(),
            created_at: now,
            updated_at: now,
            project_path,

            metadata: SessionMetadata {
                total_commands: 0,
                successful_commands: 0,
                failed_commands: 0,
                total_tokens_used: 0,
                total_cost_usd: 0.0,
            },
        }
    }

    /// Add a message to the session
    pub fn add_message(&mut self, message: ChatMessage) {
        self.messages.push(message);
        self.updated_at = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .unwrap()
            .as_secs();
    }

    /// Get all messages in chronological order
    pub fn get_messages(&self) -> &[ChatMessage] {
        &self.messages
    }

    /// Get the last N messages
    pub fn get_recent_messages(&self, count: usize) -> &[ChatMessage] {
        let start = self.messages.len().saturating_sub(count);
        &self.messages[start..]
    }

    /// Get messages for context (formatted for AI)
    pub fn get_context_messages(&self, max_messages: usize) -> Vec<(String, String)> {
        self.get_recent_messages(max_messages)
            .iter()
            .map(|msg| {
                let role = match msg.role {
                    MessageRole::User => "user",
                    MessageRole::Assistant => "assistant",
                    MessageRole::System => "system",
                };
                (role.to_string(), msg.content.clone())
            })
            .collect()
    }

    /// Update session metadata after command execution
    pub fn update_metadata(&mut self, success: bool, tokens_used: usize) {
        self.metadata.total_commands += 1;
        if success {
            self.metadata.successful_commands += 1;
        } else {
            self.metadata.failed_commands += 1;
        }
        self.metadata.total_tokens_used += tokens_used;
    }

    /// Update session cost by adding a message cost
    pub fn add_message_cost(&mut self, cost: f64) {
        self.metadata.total_cost_usd += cost;
    }

    /// Update session tokens by adding message tokens
    pub fn add_message_tokens(&mut self, tokens: u32) {
        self.metadata.total_tokens_used += tokens as usize;
    }

    /// Update the session title
    pub fn update_title(&mut self, new_title: String) {
        self.title = new_title;
        self.updated_at = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .unwrap()
            .as_secs();
    }

    /// Build accumulated context from all messages
    pub fn build_accumulated_context(&self) -> String {
        let mut context = String::new();

        context.push_str("# Chat History Context\n\n");

        for (idx, msg) in self.messages.iter().enumerate() {
            let role_label = match msg.role {
                MessageRole::User => "👤 User",
                MessageRole::Assistant => "🤖 Assistant",
                MessageRole::System => "⚙️ System",
            };

            context.push_str(&format!("## Message {} - {}\n", idx + 1, role_label));
            context.push_str(&format!("{}\n\n", msg.content));

            // Include thought process if available
            if let Some(thoughts) = &msg.thought_process {
                context.push_str("### Thought Process:\n");
                for thought in thoughts {
                    context.push_str(&format!(
                        "{}. {}\n",
                        thought.step_number, thought.description
                    ));
                }
                context.push('\n');
            }
        }

        context
    }
}

impl ChatMessage {
    /// Create a new user message
    pub fn user(content: String) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            role: MessageRole::User,
            content,
            timestamp: SystemTime::now()
                .duration_since(SystemTime::UNIX_EPOCH)
                .unwrap()
                .as_secs(),
            thought_process: None,
            context_used: None,
            visual_snapshot_b64: None,
            visual_snapshot_meta: None,
            metrics: None,
        }
    }

    /// Create a new assistant message
    pub fn assistant(
        content: String,
        thought_process: Option<Vec<ThoughtStep>>,
        context_used: Option<ContextSnapshot>,
        visual_snapshot_b64: Option<String>,
        visual_snapshot_meta: Option<serde_json::Value>,
    ) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            role: MessageRole::Assistant,
            content,
            timestamp: SystemTime::now()
                .duration_since(SystemTime::UNIX_EPOCH)
                .unwrap()
                .as_secs(),
            thought_process,
            context_used,
            visual_snapshot_b64,
            visual_snapshot_meta,
            metrics: None,
        }
    }

    /// Create a new system message
    pub fn system(
        content: String,
        thought_process: Option<Vec<ThoughtStep>>,
        context_used: Option<ContextSnapshot>,
        visual_snapshot_meta: Option<serde_json::Value>,
    ) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            role: MessageRole::System,
            content,
            timestamp: SystemTime::now()
                .duration_since(SystemTime::UNIX_EPOCH)
                .unwrap()
                .as_secs(),
            thought_process,
            context_used,
            visual_snapshot_b64: None,
            visual_snapshot_meta,
            metrics: None,
        }
    }
}

/// Manager for handling multiple chat sessions
pub struct ChatSessionManager {
    sessions: Vec<ChatSession>,
    active_session_id: Option<String>,
}

impl ChatSessionManager {
    pub fn new() -> Self {
        Self {
            sessions: Vec::new(),
            active_session_id: None,
        }
    }

    /// Create a new session and set it as active
    pub fn create_session(
        &mut self,
        title: Option<String>,
        project_path: Option<String>,
    ) -> String {
        let session = ChatSession::new(title, project_path);
        let session_id = session.id.clone();
        self.sessions.push(session);
        self.active_session_id = Some(session_id.clone());
        session_id
    }

    /// Get the active session
    pub fn get_active_session(&self) -> Option<&ChatSession> {
        self.active_session_id
            .as_ref()
            .and_then(|id| self.sessions.iter().find(|s| &s.id == id))
    }

    /// Get the active session mutably
    pub fn get_active_session_mut(&mut self) -> Option<&mut ChatSession> {
        let active_id = self.active_session_id.clone();
        active_id
            .as_ref()
            .and_then(move |id| self.sessions.iter_mut().find(|s| &s.id == id))
    }

    /// Set active session by ID
    pub fn set_active_session(&mut self, session_id: &str) -> Result<()> {
        if self.sessions.iter().any(|s| s.id == session_id) {
            self.active_session_id = Some(session_id.to_string());
            Ok(())
        } else {
            Err(anyhow::anyhow!("Session not found"))
        }
    }

    /// Get all sessions
    pub fn get_all_sessions(&self) -> &[ChatSession] {
        &self.sessions
    }

    /// Delete a session
    pub fn delete_session(&mut self, session_id: &str) -> Result<()> {
        let index = self
            .sessions
            .iter()
            .position(|s| s.id == session_id)
            .ok_or_else(|| anyhow::anyhow!("Session not found"))?;

        self.sessions.remove(index);

        // If we deleted the active session, clear it
        if self
            .active_session_id
            .as_ref()
            .map(|id| id == session_id)
            .unwrap_or(false)
        {
            self.active_session_id = None;
        }

        Ok(())
    }

    /// Update the title of a session
    pub fn update_session_title(&mut self, session_id: &str, new_title: String) -> Result<()> {
        let session = self
            .sessions
            .iter_mut()
            .find(|s| s.id == session_id)
            .ok_or_else(|| anyhow::anyhow!("Session not found"))?;

        session.update_title(new_title);
        Ok(())
    }

    /// Load sessions from storage
    pub fn load_sessions(&mut self, sessions: Vec<ChatSession>) {
        self.sessions = sessions;
        // Set the most recent session as active
        if let Some(session) = self.sessions.iter().max_by_key(|s| s.updated_at) {
            self.active_session_id = Some(session.id.clone());
        }
    }

    /// Get a mutable reference to a session by ID (without changing active session)
    pub fn get_session_mut(&mut self, session_id: &str) -> Option<&mut ChatSession> {
        self.sessions.iter_mut().find(|s| s.id == session_id)
    }
}

impl Default for ChatSessionManager {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct MessageMetrics {
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub total_tokens: u32,
    pub latency_ms: u64,
    #[serde(default)]
    pub tool_call_times: Vec<ToolCallMetric>,
    pub cost_estimate_usd: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ToolCallMetric {
    pub name: String,
    pub duration_ms: u64,
}
