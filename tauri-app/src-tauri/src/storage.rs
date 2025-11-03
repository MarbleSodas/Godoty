use anyhow::Result;
use std::fs;
use std::path::PathBuf;

pub struct Storage {
    api_key: Option<String>,
}

impl Storage {
    pub fn new() -> Self {
        let mut storage = Self {
            api_key: None,
        };
        // Try to load API key from file
        if let Ok(key) = storage.load_api_key_from_file() {
            storage.api_key = Some(key);
        }
        storage
    }
    
    pub fn get_api_key(&self) -> Option<String> {
        self.api_key.clone()
    }
    
    pub fn save_api_key(&mut self, key: &str) -> Result<()> {
        self.api_key = Some(key.to_string());
        self.save_api_key_to_file(key)
    }
    
    fn get_config_path() -> Result<PathBuf> {
        let mut path = dirs::config_dir()
            .ok_or_else(|| anyhow::anyhow!("Could not find config directory"))?;
        path.push("godoty");
        fs::create_dir_all(&path)?;
        path.push("config.json");
        Ok(path)
    }
    
    fn load_api_key_from_file(&self) -> Result<String> {
        let path = Self::get_config_path()?;
        let content = fs::read_to_string(path)?;
        let config: serde_json::Value = serde_json::from_str(&content)?;
        
        config["api_key"]
            .as_str()
            .map(|s| s.to_string())
            .ok_or_else(|| anyhow::anyhow!("API key not found in config"))
    }
    
    fn save_api_key_to_file(&self, key: &str) -> Result<()> {
        let path = Self::get_config_path()?;
        let config = serde_json::json!({
            "api_key": key
        });
        fs::write(path, serde_json::to_string_pretty(&config)?)?;
        Ok(())
    }
}

impl Default for Storage {
    fn default() -> Self {
        Self::new()
    }
}

