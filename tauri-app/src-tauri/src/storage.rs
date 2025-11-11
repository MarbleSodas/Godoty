use crate::chat_session::ChatSession;
use crate::llm_config::{all_providers, get_available_models, AgentLlmConfig, ApiKeyStore};
use crate::project_indexer::ProjectIndex;
use anyhow::Result;
use keyring::Entry;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::time::SystemTime;

#[derive(Serialize, Deserialize)]
struct CachedProjectIndex {
    index: ProjectIndex,
    timestamp: u64,
    project_path: String,
}

#[derive(Serialize, Deserialize, Default)]
struct ProjectIndexCache {
    projects: HashMap<String, CachedProjectIndex>,
}

#[derive(Serialize, Deserialize)]
struct CachedGodotDocs {
    docs: String,
    timestamp: u64,
}

pub struct Storage {
    api_key: Option<String>,
    project_path: Option<String>,
    godot_executable_paths: HashMap<String, String>, // project_path -> godot_executable_path
}

impl Storage {
    pub fn new() -> Self {
        let mut storage = Self {
            api_key: None,
            project_path: None,
            godot_executable_paths: HashMap::new(),
        };
        // Try to load config from file
        if let Ok(config) = storage.load_config_from_file() {
            storage.api_key = config
                .get("api_key")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string());
            storage.project_path = config
                .get("project_path")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string());

            // Load godot_executable_paths if present
            if let Some(paths_obj) = config
                .get("godot_executable_paths")
                .and_then(|v| v.as_object())
            {
                for (key, value) in paths_obj {
                    if let Some(path_str) = value.as_str() {
                        storage
                            .godot_executable_paths
                            .insert(key.clone(), path_str.to_string());
                    }
                }
            }


        }
        storage
    }

    pub fn get_api_key(&self) -> Option<String> {
        self.api_key.clone()
    }

    pub fn save_api_key(&mut self, key: &str) -> Result<()> {
        self.api_key = Some(key.to_string());
        self.save_config_to_file()
    }

    pub fn get_project_path(&self) -> Option<String> {
        self.project_path.clone()
    }

    pub fn save_project_path(&mut self, path: &str) -> Result<()> {
        self.project_path = Some(path.to_string());
        self.save_config_to_file()
    }

    /// Get the Godot executable path for a specific project
    pub fn get_godot_executable_path(&self, project_path: &str) -> Option<String> {
        self.godot_executable_paths.get(project_path).cloned()
    }

    /// Save the Godot executable path for a specific project
    pub fn save_godot_executable_path(
        &mut self,
        project_path: &str,
        executable_path: &str,
    ) -> Result<()> {
        self.godot_executable_paths
            .insert(project_path.to_string(), executable_path.to_string());
        self.save_config_to_file()
    }

    /// Get all project-to-executable mappings
    #[allow(dead_code)]
    pub fn get_all_godot_executable_paths(&self) -> &HashMap<String, String> {
        &self.godot_executable_paths
    }

    /// Remove the Godot executable path for a specific project
    pub fn remove_godot_executable_path(&mut self, project_path: &str) -> Result<()> {
        self.godot_executable_paths.remove(project_path);
        self.save_config_to_file()
    }

    pub fn get_config_dir() -> Result<PathBuf> {
        let mut path =
            dirs::config_dir().ok_or_else(|| anyhow::anyhow!("Could not find config directory"))?;
        path.push("godoty");
        fs::create_dir_all(&path)?;
        Ok(path)
    }

    /// Normalize a path to use as a consistent key across platforms
    /// Converts to absolute path and uses forward slashes
    fn normalize_path(path: &str) -> String {
        use std::path::Path;

        let path_buf = Path::new(path);

        // Try to canonicalize (resolve to absolute path)
        let normalized = if let Ok(canonical) = path_buf.canonicalize() {
            canonical
        } else {
            // If canonicalize fails (e.g., path doesn't exist), use as-is
            path_buf.to_path_buf()
        };

        // Convert to string with forward slashes for consistency
        normalized
            .to_string_lossy()
            .replace('\\', "/")
            .to_lowercase() // Make case-insensitive on Windows
    }

    fn get_config_path() -> Result<PathBuf> {
        let mut path = Self::get_config_dir()?;
        path.push("config.json");
        Ok(path)
    }

    fn load_config_from_file(&self) -> Result<serde_json::Value> {
        let path = Self::get_config_path()?;
        let content = fs::read_to_string(path)?;
        let config: serde_json::Value = serde_json::from_str(&content)?;
        Ok(config)
    }

    fn save_config_to_file(&self) -> Result<()> {
        let path = Self::get_config_path()?;
        let mut config = serde_json::Map::new();

        if let Some(ref key) = self.api_key {
            config.insert(
                "api_key".to_string(),
                serde_json::Value::String(key.clone()),
            );
        }

        if let Some(ref path) = self.project_path {
            config.insert(
                "project_path".to_string(),
                serde_json::Value::String(path.clone()),
            );
        }

        // Save godot_executable_paths
        if !self.godot_executable_paths.is_empty() {
            let mut paths_map = serde_json::Map::new();
            for (proj_path, exec_path) in &self.godot_executable_paths {
                paths_map.insert(
                    proj_path.clone(),
                    serde_json::Value::String(exec_path.clone()),
                );
            }
            config.insert(
                "godot_executable_paths".to_string(),
                serde_json::Value::Object(paths_map),
            );
        }


        fs::write(
            path,
            serde_json::to_string_pretty(&serde_json::Value::Object(config))?,
        )?;
        Ok(())
    }

    // Project Index Cache Methods

    pub fn save_project_index(&self, index: &ProjectIndex, project_path: &str) -> Result<()> {
        let mut path = Self::get_config_dir()?;
        path.push("project_index_cache.json");

        let timestamp = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)?
            .as_secs();

        let cached = CachedProjectIndex {
            index: index.clone(),
            timestamp,
            project_path: project_path.to_string(),
        };

        // Load existing cache or create new one
        let mut cache = if path.exists() {
            let content = fs::read_to_string(&path)?;
            serde_json::from_str::<ProjectIndexCache>(&content).unwrap_or_default()
        } else {
            ProjectIndexCache::default()
        };

        // Normalize the project path to use as a key
        let normalized_path = Self::normalize_path(project_path);

        // Insert or update the project index
        cache.projects.insert(normalized_path, cached);

        // Save the updated cache
        fs::write(path, serde_json::to_string_pretty(&cache)?)?;
        Ok(())
    }

    pub fn load_project_index(&self, project_path: &str) -> Result<ProjectIndex> {
        let mut path = Self::get_config_dir()?;
        path.push("project_index_cache.json");

        if !path.exists() {
            return Err(anyhow::anyhow!("No project index cache found"));
        }

        let content = fs::read_to_string(path)?;
        let cache: ProjectIndexCache = serde_json::from_str(&content)?;

        // Normalize the project path to use as a key
        let normalized_path = Self::normalize_path(project_path);

        // Get the cached index for this specific project
        let cached = cache.projects.get(&normalized_path).ok_or_else(|| {
            anyhow::anyhow!("No cached index found for project: {}", project_path)
        })?;

        Ok(cached.index.clone())
    }

    pub fn is_project_index_valid(&self, project_path: &str, max_age_seconds: u64) -> bool {
        let mut path = match Self::get_config_dir() {
            Ok(p) => p,
            Err(_) => return false,
        };
        path.push("project_index_cache.json");

        if !path.exists() {
            return false;
        }

        let content = match fs::read_to_string(&path) {
            Ok(c) => c,
            Err(_) => return false,
        };

        let cache: ProjectIndexCache = match serde_json::from_str(&content) {
            Ok(c) => c,
            Err(_) => return false,
        };

        // Normalize the project path to use as a key
        let normalized_path = Self::normalize_path(project_path);

        // Get the cached index for this specific project
        let cached = match cache.projects.get(&normalized_path) {
            Some(c) => c,
            None => return false,
        };

        // Check age
        let now = match SystemTime::now().duration_since(SystemTime::UNIX_EPOCH) {
            Ok(d) => d.as_secs(),
            Err(_) => return false,
        };

        if now - cached.timestamp >= max_age_seconds {
            return false;
        }

        // Check if any project files have been modified since the cache was created
        if let Ok(has_changes) = Self::check_project_modifications(project_path, cached.timestamp) {
            !has_changes
        } else {
            false
        }
    }

    fn check_project_modifications(project_path: &str, cache_timestamp: u64) -> Result<bool> {
        use std::path::Path;

        let project_dir = Path::new(project_path);
        if !project_dir.exists() {
            return Ok(true); // Project doesn't exist, invalidate cache
        }

        // Check if project.godot has been modified
        let project_file = project_dir.join("project.godot");
        if project_file.exists() {
            if let Ok(metadata) = fs::metadata(&project_file) {
                if let Ok(modified) = metadata.modified() {
                    if let Ok(duration) = modified.duration_since(SystemTime::UNIX_EPOCH) {
                        if duration.as_secs() > cache_timestamp {
                            return Ok(true); // Project file modified
                        }
                    }
                }
            }
        }

        // For a more thorough check, we could scan all .tscn, .gd, and .tres files
        // but that would be expensive. Instead, we'll rely on the age check and manual refresh

        Ok(false)
    }

    // Godot Documentation Cache Methods

    pub fn save_godot_docs(&self, docs: &str) -> Result<()> {
        let mut path = Self::get_config_dir()?;
        path.push("godot_docs_cache.json");

        let timestamp = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)?
            .as_secs();

        let cached = CachedGodotDocs {
            docs: docs.to_string(),
            timestamp,
        };

        fs::write(path, serde_json::to_string_pretty(&cached)?)?;
        Ok(())
    }

    pub fn load_godot_docs(&self) -> Result<String> {
        let mut path = Self::get_config_dir()?;
        path.push("godot_docs_cache.json");

        let content = fs::read_to_string(path)?;
        let cached: CachedGodotDocs = serde_json::from_str(&content)?;

        Ok(cached.docs)
    }

    pub fn is_godot_docs_valid(&self, max_age_seconds: u64) -> bool {
        let mut path = match Self::get_config_dir() {
            Ok(p) => p,
            Err(_) => return false,
        };
        path.push("godot_docs_cache.json");

        if !path.exists() {
            return false;
        }

        let content = match fs::read_to_string(&path) {
            Ok(c) => c,
            Err(_) => return false,
        };

        let cached: CachedGodotDocs = match serde_json::from_str(&content) {
            Ok(c) => c,
            Err(_) => return false,
        };

        // Check age
        let now = match SystemTime::now().duration_since(SystemTime::UNIX_EPOCH) {
            Ok(d) => d.as_secs(),
            Err(_) => return false,
        };

        now - cached.timestamp < max_age_seconds
    }

    pub fn clear_cache(&self) -> Result<()> {
        let config_dir = Self::get_config_dir()?;

        // Remove project index cache
        let mut path = config_dir.clone();
        path.push("project_index_cache.json");
        if path.exists() {
            fs::remove_file(path)?;
        }

        // Remove godot docs cache
        let mut path = config_dir;
        path.push("godot_docs_cache.json");
        if path.exists() {
            fs::remove_file(path)?;
        }

        Ok(())
    }
}

impl Default for Storage {
    fn default() -> Self {
        Self::new()
    }
}

// Chat Session Storage Methods
impl Storage {
    /// Save all chat sessions to disk
    pub fn save_chat_sessions(&self, sessions: &[ChatSession]) -> Result<()> {
        let mut path = Self::get_config_dir()?;
        path.push("chat_sessions.json");

        let json = serde_json::to_string_pretty(sessions)?;
        fs::write(path, json)?;
        Ok(())
    }

    /// Load all chat sessions from disk
    pub fn load_chat_sessions(&self) -> Result<Vec<ChatSession>> {
        let mut path = Self::get_config_dir()?;
        path.push("chat_sessions.json");

        if !path.exists() {
            return Ok(Vec::new());
        }

        let content = fs::read_to_string(path)?;
        let sessions: Vec<ChatSession> = serde_json::from_str(&content)?;
        Ok(sessions)
    }

    /// Save a single chat session
    pub fn save_chat_session(&self, session: &ChatSession) -> Result<()> {
        let mut sessions = self.load_chat_sessions().unwrap_or_default();

        // Update or add the session
        if let Some(existing) = sessions.iter_mut().find(|s| s.id == session.id) {
            *existing = session.clone();
        } else {
            sessions.push(session.clone());
        }

        self.save_chat_sessions(&sessions)
    }

    /// Delete a chat session
    pub fn delete_chat_session(&self, session_id: &str) -> Result<()> {
        let mut sessions = self.load_chat_sessions()?;
        sessions.retain(|s| s.id != session_id);
        self.save_chat_sessions(&sessions)
    }

    /// Clear all chat sessions
    pub fn clear_chat_sessions(&self) -> Result<()> {
        let mut path = Self::get_config_dir()?;
        path.push("chat_sessions.json");

        if path.exists() {
            fs::remove_file(path)?;
        }

        Ok(())
    }

    // Agent LLM Configuration Methods

    /// Save agent LLM configuration to disk
    pub fn save_agent_llm_config(&self, config: &AgentLlmConfig) -> Result<()> {
        let mut path = Self::get_config_dir()?;
        path.push("agent_llm_config.json");

        let json = serde_json::to_string_pretty(config)?;
        fs::write(path, json)?;
        Ok(())
    }

    /// Load agent LLM configuration from disk and merge with defaults to ensure completeness
    pub fn load_agent_llm_config(&self) -> Result<AgentLlmConfig> {
        let mut path = Self::get_config_dir()?;
        path.push("agent_llm_config.json");

        // If no file, return defaults outright
        if !path.exists() {
            return Ok(AgentLlmConfig::default());
        }

        // Parse existing; if corrupt, fall back to defaults
        let content = fs::read_to_string(&path)?;
        let mut loaded: AgentLlmConfig = serde_json::from_str(&content).unwrap_or_default();

        // Merge with defaults to fill missing agents or invalid/missing models
        let defaults = AgentLlmConfig::default();
        let available = get_available_models();

        for (agent, def_sel) in defaults.agents.iter() {
            match loaded.agents.get_mut(agent) {
                Some(sel) => {
                    // Ensure provider has a model set; if model is empty or invalid for its provider, choose a safe default
                    let provider_models = available.get(&sel.provider).cloned().unwrap_or_default();
                    let model_missing = sel.model_name.trim().is_empty();
                    let model_invalid =
                        !model_missing && !provider_models.contains(&sel.model_name);

                    if model_missing || model_invalid {
                        if !provider_models.is_empty() {
                            sel.model_name = provider_models[0].clone();
                        } else {
                            // If provider has no known models, fall back entirely to default selection for this agent
                            sel.provider = def_sel.provider.clone();
                            sel.model_name = def_sel.model_name.clone();
                        }
                    }
                }
                None => {
                    loaded.agents.insert(agent.clone(), def_sel.clone());
                }
            }
        }

        Ok(loaded)
    }

    /// Save API keys securely using the OS keychain
    pub fn save_api_keys(&self, keys: &ApiKeyStore) -> Result<()> {
        for (provider, key) in &keys.keys {
            let account = format!("{:?}", provider); // e.g., "OpenAI", "ZaiGlm"
            let entry = Entry::new("Godoty", &account)?;
            entry.set_password(key)?;
        }
        Ok(())
    }

    /// Load API keys from the OS keychain. If a legacy .keys.json exists, migrate it.
    pub fn load_api_keys(&self) -> Result<ApiKeyStore> {
        // Attempt migration from legacy file
        let mut legacy_path = Self::get_config_dir()?;
        legacy_path.push(".keys.json");
        if legacy_path.exists() {
            if let Ok(content) = fs::read_to_string(&legacy_path) {
                if let Ok(legacy_keys) = serde_json::from_str::<ApiKeyStore>(&content) {
                    for (provider, key) in &legacy_keys.keys {
                        let account = format!("{:?}", provider);
                        if let Ok(entry) = Entry::new("Godoty", &account) {
                            let _ = entry.set_password(key);
                        }
                    }
                    // Best-effort cleanup of legacy file
                    let _ = fs::remove_file(&legacy_path);
                }
            }
        }

        // Now load from keychain
        let mut out = ApiKeyStore::new();
        for provider in all_providers() {
            let account = format!("{:?}", provider);
            if let Ok(entry) = Entry::new("Godoty", &account) {
                if let Ok(secret) = entry.get_password() {
                    if !secret.is_empty() {
                        out.set_key(provider, secret);
                    }
                }
            }
        }
        Ok(out)
    }
}


