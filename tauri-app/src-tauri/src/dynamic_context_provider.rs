use crate::context_engine::ContextEngine;
use crate::project_indexer::{ProjectIndex, ProjectIndexer};
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::fs;
use tokio::sync::{mpsc, RwLock};
use uuid::Uuid;

/// Information about a file change event
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileChangeEvent {
    /// Path of the changed file
    pub path: PathBuf,
    /// Type of change
    pub change_type: FileChangeType,
    /// When the change was detected
    pub timestamp: u64,
    /// File size in bytes
    pub size: Option<u64>,
    /// Additional metadata
    pub metadata: HashMap<String, String>,
}

/// Types of file changes
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum FileChangeType {
    /// File was created
    Created,
    /// File content was modified
    Modified,
    /// File was deleted
    Deleted,
    /// File was renamed
    Renamed { from: PathBuf, to: PathBuf },
    /// Directory content changed
    DirectoryChanged,
}

/// Configuration for file watching
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileWatcherConfig {
    /// Paths to watch (relative to project root)
    pub watch_paths: Vec<String>,
    /// File patterns to include (glob patterns)
    pub include_patterns: Vec<String>,
    /// File patterns to exclude
    pub exclude_patterns: Vec<String>,
    /// Whether to watch recursively
    pub recursive: bool,
    /// Debounce time for file events (ms)
    pub debounce_ms: u64,
    /// Maximum file size to process (bytes)
    pub max_file_size: u64,
}

impl Default for FileWatcherConfig {
    fn default() -> Self {
        Self {
            watch_paths: vec![
                "res://".to_string(),
                "addons/".to_string(),
                "*.gd".to_string(),
                "*.tscn".to_string(),
                "*.cs".to_string(),
                "*.json".to_string(),
                "*.md".to_string(),
            ],
            include_patterns: vec![
                "**/*.gd".to_string(),
                "**/*.tscn".to_string(),
                "**/*.cs".to_string(),
                "**/*.json".to_string(),
                "**/*.md".to_string(),
                "**/*.tres".to_string(),
                "**/*.import".to_string(),
                "**/*.cfg".to_string(),
            ],
            exclude_patterns: vec![
                "**/.git/**".to_string(),
                "**/node_modules/**".to_string(),
                "**/target/**".to_string(),
                "**/*.tmp".to_string(),
                "**/*.log".to_string(),
            ],
            recursive: true,
            debounce_ms: 500,
            max_file_size: 10 * 1024 * 1024, // 10MB
        }
    }
}

/// Context update information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextUpdate {
    /// Unique ID for this update
    pub id: String,
    /// Type of update
    pub update_type: ContextUpdateType,
    /// Files that changed
    pub changed_files: Vec<PathBuf>,
    /// When the update occurred
    pub timestamp: u64,
    /// Updated project index (if available)
    pub project_index: Option<ProjectIndex>,
    /// Generated context content
    pub context_content: Option<String>,
    /// Relevance score for this update
    pub relevance_score: f32,
}

/// Types of context updates
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum ContextUpdateType {
    /// Initial context build
    Initial,
    /// File changes detected
    FileChanges,
    /// Full reindex
    Reindex,
    /// Incremental update
    Incremental,
    /// Error occurred
    Error { message: String },
}

/// Dynamic project context provider with file watching
pub struct DynamicProjectContextProvider {
    /// Project root path
    project_path: PathBuf,
    /// File watcher configuration
    config: FileWatcherConfig,
    /// Context engine for building context
    context_engine: Arc<ContextEngine>,
    /// Project indexer
    indexer: Arc<ProjectIndexer>,
    /// Current project index
    current_index: Arc<RwLock<Option<ProjectIndex>>>,
    /// Channel for sending file change events
    file_change_tx: mpsc::UnboundedSender<FileChangeEvent>,
    /// Channel for receiving file change events
    file_change_rx: Arc<RwLock<mpsc::UnboundedReceiver<FileChangeEvent>>>,
    /// Channel for sending context updates
    context_update_tx: mpsc::UnboundedSender<ContextUpdate>,
    /// Cached context with timestamp
    cached_context: Arc<RwLock<Option<(String, u64)>>>,
    /// Map of file paths to their last modification times
    file_mod_times: Arc<RwLock<HashMap<PathBuf, u64>>>,
    /// Debounce timer handle
    debounce_handle: Arc<RwLock<Option<tokio::task::JoinHandle<()>>>>,
}

impl DynamicProjectContextProvider {
    /// Create a new dynamic context provider
    pub async fn new(
        project_path: PathBuf,
        config: Option<FileWatcherConfig>,
        context_engine: Arc<ContextEngine>,
        indexer: Arc<ProjectIndexer>,
    ) -> Result<(Self, mpsc::UnboundedReceiver<ContextUpdate>)> {
        let config = config.unwrap_or_default();
        let (file_change_tx, file_change_rx) = mpsc::unbounded_channel();
        let (context_update_tx, context_update_rx) = mpsc::unbounded_channel();

        let provider = Self {
            project_path: project_path.clone(),
            config,
            context_engine,
            indexer,
            current_index: Arc::new(RwLock::new(None)),
            file_change_tx,
            file_change_rx: Arc::new(RwLock::new(file_change_rx)),
            context_update_tx,
            cached_context: Arc::new(RwLock::new(None)),
            file_mod_times: Arc::new(RwLock::new(HashMap::new())),
            debounce_handle: Arc::new(RwLock::new(None)),
        };

        // Send initial context update
        let initial_update = ContextUpdate {
            id: Uuid::new_v4().to_string(),
            update_type: ContextUpdateType::Initial,
            changed_files: Vec::new(),
            timestamp: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_secs(),
            project_index: None,
            context_content: None,
            relevance_score: 1.0,
        };

        let _ = provider.context_update_tx.send(initial_update);

        Ok((provider, context_update_rx))
    }

    /// Start watching for file changes
    pub async fn start_watching(&self) -> Result<()> {
        // Initial scan
        self.scan_project_directory().await?;

        // Start the file watcher loop
        let provider = self.clone();
        tokio::spawn(async move {
            provider.file_watcher_loop().await;
        });

        // Start the context update processor
        let provider = self.clone();
        tokio::spawn(async move {
            provider.context_update_processor().await;
        });

        Ok(())
    }

    /// Scan the project directory for initial state
    async fn scan_project_directory(&self) -> Result<()> {
        let mut file_mod_times = self.file_mod_times.write().await;

        // Scan all watch paths
        for watch_path in &self.config.watch_paths {
            let full_path = self.project_path.join(watch_path);
            if full_path.exists() {
                self.scan_directory_recursive(&full_path, &mut *file_mod_times).await?;
            }
        }

        // Trigger initial reindex
        let _ = self.file_change_tx.send(FileChangeEvent {
            path: self.project_path.clone(),
            change_type: FileChangeType::DirectoryChanged,
            timestamp: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_secs(),
            size: None,
            metadata: HashMap::new(),
        });

        Ok(())
    }

    /// Recursively scan a directory
    fn scan_directory_recursive<'a>(
        &'a self,
        dir_path: &'a Path,
        file_mod_times: &'a mut HashMap<PathBuf, u64>,
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<()>> + Send + 'a>> {
        Box::pin(async move {
            let mut entries = fs::read_dir(dir_path).await?;

            while let Some(entry) = entries.next_entry().await? {
                let path = entry.path();

                if path.is_dir() && self.config.recursive {
                    self.scan_directory_recursive(&path, file_mod_times).await?;
            } else if path.is_file() {
                if let Ok(metadata) = entry.metadata().await {
                    if let Ok(mod_time) = metadata.modified() {
                        let mod_timestamp = mod_time
                            .duration_since(UNIX_EPOCH)
                            .unwrap_or_default()
                            .as_secs();

                        file_mod_times.insert(path.clone(), mod_timestamp);
                    }
                }
            }
        }

            Ok(())
        })
    }

    /// Main file watcher loop
    async fn file_watcher_loop(&self) {
        let _last_scan = SystemTime::now();

        loop {
            // Check for file changes
            if let Err(e) = self.check_for_changes().await {
                tracing::error!("Error checking for file changes: {}", e);

                // Send error update
                let error_update = ContextUpdate {
                    id: Uuid::new_v4().to_string(),
                    update_type: ContextUpdateType::Error {
                        message: e.to_string(),
                    },
                    changed_files: Vec::new(),
                    timestamp: SystemTime::now()
                        .duration_since(UNIX_EPOCH)
                        .unwrap()
                        .as_secs(),
                    project_index: None,
                    context_content: None,
                    relevance_score: 0.0,
                };

                let _ = self.context_update_tx.send(error_update);
            }

            // Check if debounce timer is needed
            {
                let mut debounce_handle = self.debounce_handle.write().await;
                if debounce_handle.is_none() {
                    // Start debounce timer
                    let provider = self.clone();
                    let file_change_tx = self.file_change_tx.clone();
                    let context_update_tx = self.context_update_tx.clone();

                    *debounce_handle = Some(tokio::spawn(async move {
                        tokio::time::sleep(Duration::from_millis(provider.config.debounce_ms)).await;
                        provider.process_pending_changes(&file_change_tx, &context_update_tx).await;
                        {
                            let mut handle = provider.debounce_handle.write().await;
                            *handle = None;
                        }
                    }));
                }
            }

            // Sleep before next check
            tokio::time::sleep(Duration::from_millis(250)).await;
        }
    }

    /// Check for file changes
    async fn check_for_changes(&self) -> Result<()> {
        let mut file_mod_times = self.file_mod_times.write().await;
        let mut changes = Vec::new();

        for watch_path in &self.config.watch_paths {
            let full_path = self.project_path.join(watch_path);
            if full_path.exists() {
                self.check_directory_changes(&full_path, &mut *file_mod_times, &mut changes).await?;
            }
        }

        // Check for deleted files
        let mut to_remove = Vec::new();
        for (path, _) in file_mod_times.iter() {
            if !path.exists() {
                to_remove.push(path.clone());
                changes.push(FileChangeEvent {
                    path: path.clone(),
                    change_type: FileChangeType::Deleted,
                    timestamp: SystemTime::now()
                        .duration_since(UNIX_EPOCH)
                        .unwrap()
                        .as_secs(),
                    size: None,
                    metadata: HashMap::new(),
                });
            }
        }

        for path in to_remove {
            file_mod_times.remove(&path);
        }

        // Send detected changes
        for change in changes {
            let _ = self.file_change_tx.send(change);
        }

        Ok(())
    }

    /// Check a directory for changes
    fn check_directory_changes<'a>(
        &'a self,
        dir_path: &'a Path,
        file_mod_times: &'a mut HashMap<PathBuf, u64>,
        changes: &'a mut Vec<FileChangeEvent>,
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<()>> + Send + 'a>> {
        Box::pin(async move {
            let mut entries = fs::read_dir(dir_path).await?;

            while let Some(entry) = entries.next_entry().await? {
                let path = entry.path();

                if path.is_dir() && self.config.recursive {
                    self.check_directory_changes(&path, file_mod_times, changes).await?;
            } else if path.is_file() {
                if let Some(prev_mod_time) = file_mod_times.get_mut(&path) {
                    if let Ok(metadata) = entry.metadata().await {
                        if let Ok(mod_time) = metadata.modified() {
                            let mod_timestamp = mod_time
                                .duration_since(UNIX_EPOCH)
                                .unwrap_or_default()
                                .as_secs();

                            if mod_timestamp != *prev_mod_time {
                                *prev_mod_time = mod_timestamp;

                                changes.push(FileChangeEvent {
                                    path: path.clone(),
                                    change_type: FileChangeType::Modified,
                                    timestamp: mod_timestamp,
                                    size: Some(metadata.len()),
                                    metadata: HashMap::new(),
                                });
                            }
                        }
                    }
                } else {
                    // New file
                    if let Ok(metadata) = entry.metadata().await {
                        if let Ok(mod_time) = metadata.modified() {
                            let mod_timestamp = mod_time
                                .duration_since(UNIX_EPOCH)
                                .unwrap_or_default()
                                .as_secs();

                            file_mod_times.insert(path.clone(), mod_timestamp);

                            changes.push(FileChangeEvent {
                                path: path.clone(),
                                change_type: FileChangeType::Created,
                                timestamp: mod_timestamp,
                                size: Some(metadata.len()),
                                metadata: HashMap::new(),
                            });
                        }
                    }
                }
            }
        }

            Ok(())
        })
    }

    /// Process pending file changes
    async fn process_pending_changes(
        &self,
        _file_change_tx: &mpsc::UnboundedSender<FileChangeEvent>,
        context_update_tx: &mpsc::UnboundedSender<ContextUpdate>,
    ) {
        // Collect pending changes
        let mut changes = Vec::new();

        {
            let mut file_change_rx = self.file_change_rx.write().await;
            while let Ok(change) = file_change_rx.try_recv() {
                changes.push(change);

                // Prevent infinite loop in case of rapid changes
                if changes.len() >= 100 {
                    break;
                }
            }
        }

        if !changes.is_empty() {
            // Filter changes based on patterns
            let filtered_changes: Vec<_> = changes.into_iter()
                .filter(|change| {
                    self.should_process_file(&change.path)
                })
                .collect();

            if !filtered_changes.is_empty() {
                // Send context update
                let update = ContextUpdate {
                    id: Uuid::new_v4().to_string(),
                    update_type: ContextUpdateType::FileChanges,
                    changed_files: filtered_changes.iter().map(|c| c.path.clone()).collect(),
                    timestamp: SystemTime::now()
                        .duration_since(UNIX_EPOCH)
                        .unwrap()
                        .as_secs(),
                    project_index: None,
                    context_content: None,
                    relevance_score: self.calculate_relevance_score(&filtered_changes),
                };

                let _ = context_update_tx.send(update);
            }
        }
    }

    /// Check if a file should be processed
    fn should_process_file(&self, path: &Path) -> bool {
        // Check size limit
        if let Ok(metadata) = std::fs::metadata(path) {
            if metadata.len() > self.config.max_file_size {
                return false;
            }
        }

        let path_str = path.to_string_lossy();

        // Check include patterns
        let included = self.config.include_patterns.iter()
            .any(|pattern| self.matches_pattern(&path_str, pattern));

        if !included {
            return false;
        }

        // Check exclude patterns
        !self.config.exclude_patterns.iter()
            .any(|pattern| self.matches_pattern(&path_str, pattern))
    }

    /// Simple pattern matching (supports wildcards)
    fn matches_pattern(&self, path: &str, pattern: &str) -> bool {
        // Convert glob pattern to regex for matching
        let regex_pattern = pattern
            .replace("**", r".*")
            .replace("*", r"[^/]*")
            .replace("?", r"[^/]");

        if let Ok(re) = regex::Regex::new(&format!("^{}$", regex_pattern)) {
            re.is_match(path)
        } else {
            // Fallback to simple string comparison
            path.contains(&pattern.replace("**", "") as &str)
        }
    }

    /// Calculate relevance score for changes
    fn calculate_relevance_score(&self, changes: &[FileChangeEvent]) -> f32 {
        let mut score = 0.0;
        let total_changes = changes.len();

        for change in changes {
            match change.change_type {
                FileChangeType::Created => score += 2.0,
                FileChangeType::Modified => score += 1.0,
                FileChangeType::Deleted => score += 1.5,
                FileChangeType::Renamed { .. } => score += 1.0,
                FileChangeType::DirectoryChanged => score += 0.5,
            }
        }

        if total_changes > 0 {
            score / total_changes as f32
        } else {
            0.0
        }
    }

    /// Process context updates and rebuild context
    /// Note: This method is not used internally as the receiver is owned by the caller
    async fn context_update_processor(&self) {
        // The context_update_rx is returned to the caller in new(),
        // so this provider doesn't have access to receive updates.
        // The caller should handle receiving and processing updates.
        loop {
            tokio::time::sleep(Duration::from_millis(1000)).await;
        }
    }

    /// Process a single context update
    #[allow(dead_code)] // Dynamic context infrastructure - enhancement plan
    async fn process_context_update(&self, update: &ContextUpdate) {
        match update.update_type {
            ContextUpdateType::Initial | ContextUpdateType::Reindex => {
                // Full reindex
                if let Err(e) = self.rebuild_context().await {
                    tracing::error!("Failed to rebuild context: {}", e);
                }
            }
            ContextUpdateType::FileChanges => {
                // Incremental update
                if let Err(e) = self.update_context_incremental(&update.changed_files).await {
                    tracing::error!("Failed to update context incrementally: {}", e);
                }
            }
            ContextUpdateType::Incremental => {
                // Handle incremental update
                if let Err(e) = self.rebuild_context().await {
                    tracing::error!("Failed to process incremental update: {}", e);
                }
            }
            ContextUpdateType::Error { .. } => {
                // Error already logged elsewhere
            }
        }
    }

    /// Rebuild the entire context
    async fn rebuild_context(&self) -> Result<()> {
        tracing::info!("Rebuilding context for project: {:?}", self.project_path);

        // Reindex the project
        let index = self.indexer
            .index_project()
            .context("Failed to index project")?;

        // Update current index
        {
            let mut current_index = self.current_index.write().await;
            *current_index = Some(index.clone());
        }

        // Build comprehensive context
        let context = self.context_engine
            .build_comprehensive_context(
                "Dynamic context update",
                &index,
                None,
                10,
            )
            .await
            .context("Failed to build context")?;

        // Convert context to JSON string
        let context_json = serde_json::to_string(&context)
            .unwrap_or_else(|_| "{}".to_string());

        // Update cache
        {
            let mut cached = self.cached_context.write().await;
            *cached = Some((
                context_json.clone(),
                SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .unwrap()
                    .as_secs(),
            ));
        }

        // Send update notification
        let update = ContextUpdate {
            id: Uuid::new_v4().to_string(),
            update_type: ContextUpdateType::Reindex,
            changed_files: Vec::new(),
            timestamp: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_secs(),
            project_index: Some(index),
            context_content: Some(context_json),
            relevance_score: 1.0,
        };

        let _ = self.context_update_tx.send(update);

        Ok(())
    }

    /// Update context incrementally based on changed files
    async fn update_context_incremental(&self, changed_files: &[PathBuf]) -> Result<()> {
        if changed_files.is_empty() {
            return Ok(());
        }

        tracing::info!("Updating context for {} changed files", changed_files.len());

        // Get current cached context
        let cached = {
            let cached_guard = self.cached_context.read().await;
            cached_guard.clone()
        };

        // If no cached context, do full rebuild
        if cached.is_none() {
            return self.rebuild_context().await;
        }

        let (_current_context, _timestamp) = cached.unwrap();

        // For now, do a full rebuild
        // TODO: Implement proper incremental context updates
        self.rebuild_context().await
    }

    /// Get the current context
    #[allow(dead_code)] // Dynamic context infrastructure - enhancement plan
    pub async fn get_current_context(&self) -> Result<String> {
        {
            let cached = self.cached_context.read().await;
            if let Some((context, timestamp)) = cached.as_ref() {
                // Check if cache is still valid (5 minutes)
                let now = SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .unwrap()
                    .as_secs();

                if now - *timestamp < 300 {
                    return Ok(context.clone());
                }
            }
        }

        // Cache expired or missing, rebuild
        self.rebuild_context().await?;

        // Return from updated cache
        let cached = self.cached_context.read().await;
        if let Some((context, _)) = cached.as_ref() {
            Ok(context.clone())
        } else {
            Err(anyhow::anyhow!("Failed to build context"))
        }
    }

    /// Get the current project index
    #[allow(dead_code)] // Dynamic context infrastructure - enhancement plan
    pub async fn get_project_index(&self) -> Option<ProjectIndex> {
        self.current_index.read().await.clone()
    }

    /// Manually trigger a context refresh
    #[allow(dead_code)] // Dynamic context infrastructure - enhancement plan
    pub async fn refresh_context(&self) -> Result<()> {
        self.rebuild_context().await
    }
}

// Implement Clone for the provider
impl Clone for DynamicProjectContextProvider {
    fn clone(&self) -> Self {
        Self {
            project_path: self.project_path.clone(),
            config: self.config.clone(),
            context_engine: self.context_engine.clone(),
            indexer: self.indexer.clone(),
            current_index: self.current_index.clone(),
            file_change_tx: self.file_change_tx.clone(),
            file_change_rx: self.file_change_rx.clone(),
            context_update_tx: self.context_update_tx.clone(),
            cached_context: self.cached_context.clone(),
            file_mod_times: self.file_mod_times.clone(),
            debounce_handle: self.debounce_handle.clone(),
        }
    }
}

impl DynamicProjectContextProvider {
    /// Get recent context updates
    pub async fn get_recent_context_updates(&self, limit: usize) -> Result<Vec<ContextUpdate>> {
        let mut updates = Vec::new();

        // Collect recent changes from the cache
        {
            let cached_guard = self.cached_context.read().await;
            if let Some((_context, timestamp)) = cached_guard.as_ref() {
                // Create a synthetic context update from the cached context
                updates.push(ContextUpdate {
                    id: uuid::Uuid::new_v4().to_string(),
                    update_type: ContextUpdateType::Incremental,
                    changed_files: vec![self.project_path.clone()],
                    timestamp: *timestamp,
                    project_index: None,
                    context_content: None,
                    relevance_score: 0.0,
                });
            }
        }

        // Limit the number of updates
        updates.truncate(limit);

        Ok(updates)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[tokio::test]
    async fn test_file_watcher_config() {
        let config = FileWatcherConfig::default();
        assert_eq!(config.debounce_ms, 500);
        assert_eq!(config.max_file_size, 10 * 1024 * 1024);
        assert!(config.recursive);
    }

    #[tokio::test]
    async fn test_pattern_matching() {
        let provider = DynamicProjectContextProvider::new(
            PathBuf::from("/test"),
            None,
            Arc::new(ContextEngine::new("test-api-key")),
            Arc::new(ProjectIndexer::new("/test")),
        ).await.unwrap().0;

        assert!(provider.matches_pattern("test.gd", "*.gd"));
        assert!(provider.matches_pattern("src/test.gd", "**/*.gd"));
        assert!(!provider.matches_pattern("test.txt", "*.gd"));
    }
}