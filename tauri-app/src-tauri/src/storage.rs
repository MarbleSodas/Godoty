use anyhow::Result;
use std::fs;
use std::path::PathBuf;
use std::time::SystemTime;
use serde::{Deserialize, Serialize};
use crate::project_indexer::ProjectIndex;
use crate::chat_session::ChatSession;

#[derive(Serialize, Deserialize)]
struct CachedProjectIndex {
    index: ProjectIndex,
    timestamp: u64,
    project_path: String,
}

#[derive(Serialize, Deserialize)]
struct CachedGodotDocs {
    docs: String,
    timestamp: u64,
}
#[derive(Serialize, Deserialize)]
struct CachedTutorials {
    tutorials: String,
    timestamp: u64,
    version_key: Option<String>,
}


pub struct Storage {
    api_key: Option<String>,
    project_path: Option<String>,
}

impl Storage {
    pub fn new() -> Self {
        let mut storage = Self {
            api_key: None,
            project_path: None,
        };
        // Try to load config from file
        if let Ok(config) = storage.load_config_from_file() {
            storage.api_key = config.get("api_key").and_then(|v| v.as_str()).map(|s| s.to_string());
            storage.project_path = config.get("project_path").and_then(|v| v.as_str()).map(|s| s.to_string());
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

    pub fn get_config_dir() -> Result<PathBuf> {
        let mut path = dirs::config_dir()
            .ok_or_else(|| anyhow::anyhow!("Could not find config directory"))?;
        path.push("godoty");
        fs::create_dir_all(&path)?;
        Ok(path)
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
            config.insert("api_key".to_string(), serde_json::Value::String(key.clone()));
        }

        if let Some(ref path) = self.project_path {
            config.insert("project_path".to_string(), serde_json::Value::String(path.clone()));
        }

        fs::write(path, serde_json::to_string_pretty(&serde_json::Value::Object(config))?)?;
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

        fs::write(path, serde_json::to_string_pretty(&cached)?)?;
        Ok(())
    }

    pub fn load_project_index(&self, project_path: &str) -> Result<ProjectIndex> {
        let mut path = Self::get_config_dir()?;
        path.push("project_index_cache.json");

        let content = fs::read_to_string(path)?;
        let cached: CachedProjectIndex = serde_json::from_str(&content)?;

        // Verify the cache is for the same project
        if cached.project_path != project_path {
            return Err(anyhow::anyhow!("Cached index is for a different project"));
        }

        Ok(cached.index)
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

        let cached: CachedProjectIndex = match serde_json::from_str(&content) {
            Ok(c) => c,
            Err(_) => return false,
        };

        // Check if it's for the same project
        if cached.project_path != project_path {
            return false;
        }

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


// Tutorials Cache Methods
impl Storage {
    pub fn save_tutorials(&self, tutorials: &str, version_key: Option<&str>) -> Result<()> {
        let mut path = Self::get_config_dir()?;
        let fname = if let Some(v) = version_key { format!("tutorials_cache_{}.json", v) } else { "tutorials_cache.json".to_string() };
        path.push(fname);

        let timestamp = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)?
            .as_secs();

        let cached = CachedTutorials {
            tutorials: tutorials.to_string(),
            timestamp,
            version_key: version_key.map(|s| s.to_string()),
        };

        fs::write(path, serde_json::to_string_pretty(&cached)?)?;
        Ok(())
    }

    pub fn load_tutorials(&self, version_key: Option<&str>) -> Result<String> {
        let mut path = Self::get_config_dir()?;
        let fname = if let Some(v) = version_key { format!("tutorials_cache_{}.json", v) } else { "tutorials_cache.json".to_string() };
        path.push(fname);

        let content = fs::read_to_string(path)?;
        let cached: CachedTutorials = serde_json::from_str(&content)?;
        Ok(cached.tutorials)
    }

    pub fn is_tutorials_valid(&self, version_key: Option<&str>, max_age_seconds: u64) -> bool {
        let mut path = match Self::get_config_dir() { Ok(p) => p, Err(_) => return false };
        let fname = if let Some(v) = version_key { format!("tutorials_cache_{}.json", v) } else { "tutorials_cache.json".to_string() };
        path.push(fname);

        if !path.exists() { return false; }

        let content = match fs::read_to_string(&path) { Ok(c) => c, Err(_) => return false };
        let cached: CachedTutorials = match serde_json::from_str(&content) { Ok(c) => c, Err(_) => return false };

        let now = match SystemTime::now().duration_since(SystemTime::UNIX_EPOCH) { Ok(d) => d.as_secs(), Err(_) => return false };
        now - cached.timestamp < max_age_seconds
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
}

