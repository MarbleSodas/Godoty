use crate::chat_session::{ChatMessage, ChatSession, MessageRole};
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::fs;
use tokio::sync::RwLock;
use uuid::Uuid;

/// Session metadata for tracking
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionMetadata {
    /// Unique session identifier
    pub id: String,
    /// Session title (derived from first message)
    pub title: String,
    /// Creation timestamp
    pub created_at: chrono::DateTime<chrono::Utc>,
    /// Last update timestamp
    pub updated_at: chrono::DateTime<chrono::Utc>,
    /// Number of messages in session
    pub message_count: usize,
    /// Project path associated with session
    pub project_path: Option<String>,
    /// Tags for organization
    pub tags: Vec<String>,
    /// Whether session is archived
    pub archived: bool,
}

/// Full session data with metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PersistedSession {
    /// Session metadata
    pub metadata: SessionMetadata,
    /// Actual chat session
    pub session: ChatSession,
}

/// Conversation manager trait for different strategies
#[async_trait::async_trait]
pub trait ConversationManager: Send + Sync {
    /// Add a message to the conversation
    async fn add_message(&mut self, message: ChatMessage) -> Result<()>;

    /// Get messages for LLM context (may truncate or summarize)
    async fn get_context_messages(&self, max_tokens: Option<usize>) -> Result<Vec<ChatMessage>>;

    /// Get all messages
    #[allow(dead_code)] // Future conversation management feature
    async fn get_all_messages(&self) -> Result<Vec<ChatMessage>>;

    /// Get message count
    async fn get_message_count(&self) -> usize;

    /// Clear conversation
    #[allow(dead_code)] // Future conversation management feature
    async fn clear(&mut self) -> Result<()>;

    /// Get conversation summary (if supported)
    async fn get_summary(&self) -> Result<Option<String>>;
}

/// Sliding window conversation manager
#[derive(Debug, Clone)]
pub struct SlidingWindowManager {
    messages: Vec<ChatMessage>,
    /// Maximum number of messages to keep
    max_messages: usize,
    /// Keep system messages always
    keep_system_messages: bool,
}

impl SlidingWindowManager {
    pub fn new(max_messages: usize, keep_system_messages: bool) -> Self {
        Self {
            messages: Vec::new(),
            max_messages,
            keep_system_messages,
        }
    }

    #[allow(dead_code)] // Future token management feature
    pub fn with_token_limit(max_tokens: usize) -> Self {
        // Approximate 4 chars per token
        let _max_recovery_depth = max_tokens * 4;
        Self {
            messages: Vec::new(),
            max_messages: 100, // Will be adjusted based on token count
            keep_system_messages: true,
        }
    }
}

#[async_trait::async_trait]
impl ConversationManager for SlidingWindowManager {
    async fn add_message(&mut self, message: ChatMessage) -> Result<()> {
        self.messages.push(message);
        self.truncate_if_needed();
        Ok(())
    }

    async fn get_context_messages(&self, max_tokens: Option<usize>) -> Result<Vec<ChatMessage>> {
        let mut messages = self.messages.clone();

        if let Some(max_tokens) = max_tokens {
            // Estimate tokens and truncate if needed
            let mut total_tokens = 0;
            let mut keep_indices = Vec::new();

            // Always keep system messages
            for (i, msg) in messages.iter().enumerate() {
                if msg.role == MessageRole::System && self.keep_system_messages {
                    keep_indices.push(i);
                    total_tokens += self.estimate_tokens(&msg.content);
                }
            }

            // Add other messages from newest to oldest within token limit
            for (i, msg) in messages.iter().enumerate().rev() {
                if msg.role == MessageRole::System || keep_indices.contains(&i) {
                    continue;
                }

                let msg_tokens = self.estimate_tokens(&msg.content);
                if total_tokens + msg_tokens > max_tokens {
                    break;
                }

                total_tokens += msg_tokens;
                keep_indices.push(i);
            }

            keep_indices.sort_unstable();
            messages = messages.into_iter().enumerate()
                .filter(|(i, _)| keep_indices.contains(i))
                .map(|(_, msg)| msg)
                .collect();
        }

        Ok(messages)
    }

    async fn get_all_messages(&self) -> Result<Vec<ChatMessage>> {
        Ok(self.messages.clone())
    }

    async fn get_message_count(&self) -> usize {
        self.messages.len()
    }

    async fn clear(&mut self) -> Result<()> {
        self.messages.clear();
        Ok(())
    }

    async fn get_summary(&self) -> Result<Option<String>> {
        Ok(None) // Sliding window doesn't maintain summary
    }
}

impl SlidingWindowManager {
    fn truncate_if_needed(&mut self) {
        if self.messages.len() <= self.max_messages {
            return;
        }

        // Count system messages
        let system_count = self.messages.iter()
            .filter(|m| m.role == MessageRole::System)
            .count();

        if self.keep_system_messages && system_count > 0 {
            // Keep system messages, remove oldest non-system messages
            let mut to_remove = self.messages.len() - self.max_messages;
            self.messages.retain(|msg| {
                if msg.role == MessageRole::System {
                    true
                } else if to_remove > 0 {
                    to_remove -= 1;
                    false
                } else {
                    true
                }
            });
        } else {
            // Remove oldest messages
            let remove_count = self.messages.len() - self.max_messages;
            self.messages.drain(0..remove_count);
        }
    }

    fn estimate_tokens(&self, text: &str) -> usize {
        // Rough estimation: ~4 characters per token for English
        (text.len() + 3) / 4
    }
}

/// Summarizing conversation manager
#[derive(Debug, Clone)]
pub struct SummarizingManager {
    messages: Vec<ChatMessage>,
    summary: Option<String>,
    last_summary_index: usize,
    max_messages_before_summary: usize,
    #[allow(dead_code)] // Future summary token management
    summary_token_limit: usize,
}

impl SummarizingManager {
    pub fn new(max_messages: usize, summary_token_limit: usize) -> Self {
        Self {
            messages: Vec::new(),
            summary: None,
            last_summary_index: 0,
            max_messages_before_summary: max_messages,
            summary_token_limit,
        }
    }

    async fn create_summary(&mut self) -> Result<String> {
        // This would integrate with LLM to create summary
        // For now, return a placeholder
        let messages_to_summarize: Vec<_> = self.messages.iter()
            .skip(self.last_summary_index)
            .filter(|m| m.role != MessageRole::System)
            .collect();

        if messages_to_summarize.is_empty() {
            return Ok(String::new());
        }

        // TODO: Integrate with LLM for actual summarization
        Ok(format!("Summary of {} messages", messages_to_summarize.len()))
    }
}

#[async_trait::async_trait]
impl ConversationManager for SummarizingManager {
    async fn add_message(&mut self, message: ChatMessage) -> Result<()> {
        self.messages.push(message);

        // Check if we need to create a summary
        if self.messages.len() > self.max_messages_before_summary {
            let summary = self.create_summary().await?;
            if !summary.is_empty() {
                self.summary = Some(summary);
                self.last_summary_index = self.messages.len() - 10; // Keep last 10 messages
            }
        }

        Ok(())
    }

    async fn get_context_messages(&self, max_tokens: Option<usize>) -> Result<Vec<ChatMessage>> {
        let mut messages = Vec::new();

        // Add system messages first
        for msg in &self.messages {
            if msg.role == MessageRole::System {
                messages.push(msg.clone());
            }
        }

        // Add summary if available
        if let Some(summary) = &self.summary {
            messages.push(ChatMessage {
                id: Uuid::new_v4().to_string(),
                role: MessageRole::System,
                content: format!("Previous conversation summary: {}", summary),
                timestamp: std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_secs(),
                thought_process: None,
                context_used: None,
                visual_snapshot_b64: None,
                visual_snapshot_meta: None,
                metrics: None,
            });
        }

        // Add recent messages after summary
        for msg in self.messages.iter().skip(self.last_summary_index) {
            messages.push(msg.clone());
        }

        // Apply token limit if specified
        if let Some(max_tokens) = max_tokens {
            let mut total_tokens = 0;
            let mut result = Vec::new();

            for msg in messages.into_iter().rev() {
                let msg_tokens = (msg.content.len() + 3) / 4;
                if total_tokens + msg_tokens > max_tokens {
                    break;
                }
                total_tokens += msg_tokens;
                result.insert(0, msg);
            }

            messages = result;
        }

        Ok(messages)
    }

    async fn get_all_messages(&self) -> Result<Vec<ChatMessage>> {
        Ok(self.messages.clone())
    }

    async fn get_message_count(&self) -> usize {
        self.messages.len()
    }

    async fn clear(&mut self) -> Result<()> {
        self.messages.clear();
        self.summary = None;
        self.last_summary_index = 0;
        Ok(())
    }

    async fn get_summary(&self) -> Result<Option<String>> {
        Ok(self.summary.clone())
    }
}

/// File-based session manager
#[derive(Clone)]
pub struct FileSessionManager {
    sessions_dir: PathBuf,
    active_sessions: Arc<RwLock<HashMap<String, PersistedSession>>>,
    conversation_manager_type: ConversationManagerType,
}

/// Types of conversation managers
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ConversationManagerType {
    SlidingWindow { max_messages: usize },
    Summarizing { max_messages: usize, summary_limit: usize },
}

impl FileSessionManager {
    /// Create new FileSessionManager
    pub async fn new(sessions_dir: PathBuf, manager_type: ConversationManagerType) -> Result<Self> {
        // Ensure sessions directory exists
        fs::create_dir_all(&sessions_dir).await
            .with_context(|| format!("Failed to create sessions directory: {:?}", sessions_dir))?;

        let manager = Self {
            sessions_dir,
            active_sessions: Arc::new(RwLock::new(HashMap::new())),
            conversation_manager_type: manager_type,
        };

        // Load existing sessions
        manager.load_all_sessions().await?;

        Ok(manager)
    }

    /// Create a new session
    pub async fn create_session(
        &self,
        project_path: Option<String>,
        initial_context: Option<String>,
    ) -> Result<String> {
        let session_id = Uuid::new_v4().to_string();
        let now = chrono::Utc::now();

        // Create initial chat session
        let mut session = ChatSession::new(
            Some("New Session".to_string()),
            project_path.clone(),
        );

        // Add system context if provided
        if let Some(context) = initial_context {
            session.add_message(ChatMessage {
                id: Uuid::new_v4().to_string(),
                role: MessageRole::System,
                content: context,
                timestamp: now.timestamp() as u64,
                thought_process: None,
                context_used: None,
                visual_snapshot_b64: None,
                visual_snapshot_meta: None,
                metrics: None,
            });
        }

        let metadata = SessionMetadata {
            id: session_id.clone(),
            title: "New Session".to_string(),
            created_at: now,
            updated_at: now,
            message_count: session.get_messages().len(),
            project_path,
            tags: Vec::new(),
            archived: false,
        };

        let persisted = PersistedSession {
            metadata,
            session,
        };

        // Save to file
        self.save_session(&persisted).await?;

        // Add to active sessions
        let mut sessions = self.active_sessions.write().await;
        sessions.insert(session_id.clone(), persisted);

        Ok(session_id)
    }

    /// Get a session by ID
    pub async fn get_session(&self, session_id: &str) -> Result<Option<PersistedSession>> {
        // Check active sessions first
        {
            let sessions = self.active_sessions.read().await;
            if let Some(session) = sessions.get(session_id) {
                return Ok(Some(session.clone()));
            }
        }

        // Load from file if not in memory
        let session_path = self.get_session_path(session_id);
        if session_path.exists() {
            let content = fs::read_to_string(&session_path).await?;
            let session: PersistedSession = serde_json::from_str(&content)?;

            // Add to active sessions
            let mut sessions = self.active_sessions.write().await;
            sessions.insert(session_id.to_string(), session.clone());

            Ok(Some(session))
        } else {
            Ok(None)
        }
    }

    /// Update a session
    pub async fn update_session(&self, session_id: &str, session: &PersistedSession) -> Result<()> {
        // Update in memory
        {
            let mut sessions = self.active_sessions.write().await;
            sessions.insert(session_id.to_string(), session.clone());
        }

        // Save to file
        self.save_session(session).await?;

        Ok(())
    }

    /// Add a message to a session
    pub async fn add_message(
        &self,
        session_id: &str,
        message: ChatMessage,
    ) -> Result<()> {
        let mut session = self.get_session(session_id).await?
            .ok_or_else(|| anyhow::anyhow!("Session not found: {}", session_id))?;

        // Update title from first user message if needed
        if session.metadata.title == "New Session" && message.role == MessageRole::User {
            let title = message.content.chars().take(50).collect::<String>();
            session.metadata.title = title;
        }

        // Add message to chat session
        session.session.add_message(message);

        // Update metadata
        session.metadata.updated_at = chrono::Utc::now();
        session.metadata.message_count = session.session.get_messages().len();

        // Save updated session
        self.update_session(session_id, &session).await?;

        Ok(())
    }

    /// Get conversation manager for a session
    pub async fn get_conversation_manager(
        &self,
        session_id: &str,
    ) -> Result<Box<dyn ConversationManager>> {
        let session = self.get_session(session_id).await?
            .ok_or_else(|| anyhow::anyhow!("Session not found: {}", session_id))?;

        let messages = session.session.get_messages();

        let manager: Box<dyn ConversationManager> = match &self.conversation_manager_type {
            ConversationManagerType::SlidingWindow { max_messages } => {
                let mut sw_manager = SlidingWindowManager::new(*max_messages, true);
                for msg in messages {
                    sw_manager.add_message(msg.clone()).await?;
                }
                Box::new(sw_manager)
            }
            ConversationManagerType::Summarizing { max_messages, summary_limit } => {
                let mut sum_manager = SummarizingManager::new(*max_messages, *summary_limit);
                for msg in messages {
                    sum_manager.add_message(msg.clone()).await?;
                }
                Box::new(sum_manager)
            }
        };

        Ok(manager)
    }

    /// List all sessions
    pub async fn list_sessions(&self) -> Result<Vec<SessionMetadata>> {
        let mut sessions = Vec::new();

        // Read all session files
        let mut entries = fs::read_dir(&self.sessions_dir).await?;
        while let Some(entry) = entries.next_entry().await? {
            let path = entry.path();
            if path.extension().and_then(|s| s.to_str()) == Some("json") {
                match Self::load_session_from_file(&path).await {
                    Ok(session) => sessions.push(session.metadata),
                    Err(e) => {
                        tracing::warn!("Failed to load session from {:?}: {}", path, e);
                    }
                }
            }
        }

        // Sort by updated_at (newest first)
        sessions.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));

        Ok(sessions)
    }

    /// Delete a session
    pub async fn delete_session(&self, session_id: &str) -> Result<()> {
        // Remove from active sessions
        {
            let mut sessions = self.active_sessions.write().await;
            sessions.remove(session_id);
        }

        // Delete file
        let session_path = self.get_session_path(session_id);
        if session_path.exists() {
            fs::remove_file(&session_path).await?;
        }

        Ok(())
    }

    /// Archive a session
    pub async fn archive_session(&self, session_id: &str) -> Result<()> {
        let mut session = self.get_session(session_id).await?
            .ok_or_else(|| anyhow::anyhow!("Session not found: {}", session_id))?;

        session.metadata.archived = true;
        session.metadata.updated_at = chrono::Utc::now();

        self.update_session(session_id, &session).await?;

        Ok(())
    }

    /// Get session file path
    fn get_session_path(&self, session_id: &str) -> PathBuf {
        self.sessions_dir.join(format!("{}.json", session_id))
    }

    /// Save session to file
    async fn save_session(&self, session: &PersistedSession) -> Result<()> {
        let session_path = self.get_session_path(&session.metadata.id);
        let content = serde_json::to_string_pretty(session)?;
        fs::write(&session_path, content).await?;
        Ok(())
    }

    /// Load session from file
    async fn load_session_from_file(path: &PathBuf) -> Result<PersistedSession> {
        let content = fs::read_to_string(path).await?;
        let session: PersistedSession = serde_json::from_str(&content)?;
        Ok(session)
    }

    /// Load all sessions from disk
    async fn load_all_sessions(&self) -> Result<()> {
        let mut sessions = HashMap::new();

        if !self.sessions_dir.exists() {
            return Ok(());
        }

        let mut entries = fs::read_dir(&self.sessions_dir).await?;
        while let Some(entry) = entries.next_entry().await? {
            let path = entry.path();
            if path.extension().and_then(|s| s.to_str()) == Some("json") {
                match Self::load_session_from_file(&path).await {
                    Ok(session) => {
                        sessions.insert(session.metadata.id.clone(), session);
                    }
                    Err(e) => {
                        tracing::warn!("Failed to load session from {:?}: {}", path, e);
                    }
                }
            }
        }

        let mut active_sessions = self.active_sessions.write().await;
        *active_sessions = sessions;

        Ok(())
    }

    /// Cleanup old sessions
    pub async fn cleanup_old_sessions(&self, days_old: u64) -> Result<usize> {
        let cutoff = chrono::Utc::now() - chrono::Duration::days(days_old as i64);
        let sessions = self.list_sessions().await?;
        let mut removed = 0;

        for session in sessions {
            if session.updated_at < cutoff && !session.archived {
                if let Err(e) = self.delete_session(&session.id).await {
                    tracing::warn!("Failed to delete old session {}: {}", session.id, e);
                } else {
                    removed += 1;
                }
            }
        }

        Ok(removed)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[tokio::test]
    async fn test_sliding_window_manager() {
        let mut manager = SlidingWindowManager::new(3, false);

        // Add messages
        for i in 0..5 {
            manager.add_message(ChatMessage {
                id: Uuid::new_v4().to_string(),
                role: MessageRole::User,
                content: format!("Message {}", i),
                timestamp: std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_secs(),
                thought_process: None,
                context_used: None,
                visual_snapshot_b64: None,
                visual_snapshot_meta: None,
                metrics: None,
            }).await.unwrap();
        }

        // Should only keep last 3 messages
        assert_eq!(manager.get_message_count().await, 3);

        let messages = manager.get_all_messages().await.unwrap();
        assert_eq!(messages[0].content, "Message 2");
        assert_eq!(messages[2].content, "Message 4");
    }

    #[tokio::test]
    async fn test_file_session_manager() {
        let temp_dir = TempDir::new().unwrap();
        let manager = FileSessionManager::new(
            temp_dir.path().to_path_buf(),
            ConversationManagerType::SlidingWindow { max_messages: 10 },
        ).await.unwrap();

        // Create session
        let session_id = manager.create_session(
            Some("/test/project".to_string()),
            Some("Test context".to_string()),
        ).await.unwrap();

        // Add message
        manager.add_message(&session_id, ChatMessage {
            id: Uuid::new_v4().to_string(),
            role: MessageRole::User,
            content: "Hello, world!".to_string(),
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs(),
            thought_process: None,
            context_used: None,
            visual_snapshot_b64: None,
            visual_snapshot_meta: None,
            metrics: None,
        }).await.unwrap();

        // Retrieve session
        let session = manager.get_session(&session_id).await.unwrap().unwrap();
        assert_eq!(session.metadata.message_count, 2); // System + User
        assert_eq!(session.metadata.project_path, Some("/test/project".to_string()));
    }
}