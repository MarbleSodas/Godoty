use anyhow::{anyhow, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use tokio::fs;
use tracing::{debug, info, warn};

/// MCP Configuration structure for managing multiple MCP servers
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct McpConfig {
    pub version: String,
    pub servers: HashMap<String, McpServerConfig>,
    pub global_settings: McpGlobalSettings,
}

/// Individual MCP server configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct McpServerConfig {
    pub enabled: bool,
    pub command: String,
    pub args: Vec<String>,
    pub description: String,
    pub timeout_seconds: u64,
    pub retry_attempts: u32,
    pub environment: HashMap<String, String>,
    pub tool_filters: Option<ToolFilters>,
    /// Use bundled binary instead of external command
    pub use_bundled: bool,
    /// Optional custom path to bundled binary
    pub binary_path: Option<PathBuf>,
}

/// Tool filtering configuration for servers
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolFilters {
    pub allowed_tools: Option<Vec<String>>,
    pub denied_tools: Option<Vec<String>>,
    pub allowed_patterns: Option<Vec<String>>,
    pub denied_patterns: Option<Vec<String>>,
}

/// Global MCP settings
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct McpGlobalSettings {
    pub max_concurrent_servers: u32,
    pub default_timeout_seconds: u64,
    pub enable_metrics: bool,
    pub log_level: String,
    pub fallback_on_server_failure: bool,
}

impl Default for McpGlobalSettings {
    fn default() -> Self {
        Self {
            max_concurrent_servers: 10,
            default_timeout_seconds: 30,
            enable_metrics: true,
            log_level: "info".to_string(),
            fallback_on_server_failure: true,
        }
    }
}

impl Default for McpConfig {
    fn default() -> Self {
        let mut servers = HashMap::new();

        // Create server configurations with intelligent binary detection
        servers.insert("desktop-commander".to_string(), Self::create_server_config(
            "desktop-commander",
            "Desktop file system, search, and process management",
            30,
            3,
            "@wonderwhy-er/desktop-commander@latest"
        ));

        servers.insert("sequential-thinking".to_string(), Self::create_server_config(
            "sequential-thinking",
            "Sequential thinking and reasoning tools",
            60,
            2,
            "@modelcontextprotocol/server-sequential-thinking@latest"
        ));

        servers.insert("context7".to_string(), Self::create_server_config(
            "context7",
            "Enhanced documentation and library access",
            45,
            2,
            "@upstash/context7-mcp@latest"
        ));

        Self {
            version: "1.0.0".to_string(),
            servers,
            global_settings: McpGlobalSettings::default(),
        }
    }
}

impl McpConfig {
    /// Create a server configuration with intelligent binary detection
    fn create_server_config(
        server_id: &str,
        description: &str,
        timeout_seconds: u64,
        retry_attempts: u32,
        package_name: &str,
    ) -> McpServerConfig {
        // Determine whether to use bundled binaries based on build mode and availability
        let use_bundled = Self::should_use_bundled_for_server(server_id);

        McpServerConfig {
            enabled: true,
            command: if use_bundled { String::new() } else { Self::get_npx_command() },
            args: if use_bundled {
                vec![]
            } else {
                vec!["-y".to_string(), package_name.to_string()]
            },
            description: description.to_string(),
            timeout_seconds,
            retry_attempts,
            environment: HashMap::new(),
            tool_filters: None,
            use_bundled,
            binary_path: None,
        }
    }

    /// Determine if a specific server should use bundled binaries
    fn should_use_bundled_for_server(server_id: &str) -> bool {
        // In release mode, always try to use bundled binaries
        if !cfg!(debug_assertions) {
            return true;
        }

        // In debug mode, check if bundled binaries are available
        // This allows developers to pre-build binaries for testing
        Self::check_bundled_binary_available(server_id)
    }

    /// Check if a bundled binary is available for a specific server
    fn check_bundled_binary_available(server_id: &str) -> bool {
        // Direct path checking to avoid circular dependencies
        let platform_dir = match std::env::consts::OS {
            "windows" => "windows",
            "macos" => "macos",
            "linux" => "linux",
            _ => return false,
        };

        let binary_name = match server_id {
            "desktop-commander" => "desktop-commander",
            "sequential-thinking" => "sequential-thinking",
            "context7" => "context7",
            _ => return false,
        };

        let mut binary_path = std::path::PathBuf::from("resources/mcp")
            .join(platform_dir)
            .join(binary_name);

        if std::env::consts::OS == "windows" {
            binary_path.set_extension("exe");
        }

        binary_path.exists()
    }

    /// Get the npx command with full path to resolve PATH issues
    fn get_npx_command() -> String {
        if cfg!(target_os = "windows") {
            // Try common Windows locations for npx
            let common_paths = vec![
                r"C:\Program Files\nodejs\npx.cmd",
                r"C:\Program Files (x86)\nodejs\npx.cmd",
            ];

            for path in common_paths {
                if std::path::Path::new(path).exists() {
                    return path.to_string();
                }
            }
        }

        // Fallback to just "npx" and hope it's in PATH
        "npx".to_string()
    }
}

/// MCP Configuration Manager
pub struct McpConfigManager {
    #[allow(dead_code)] // Path stored for future config operations
    config_path: PathBuf,
    #[allow(dead_code)] // Config accessible through public methods
    config: McpConfig,
}

#[allow(dead_code)] // MCP configuration management - enhancement plan
impl McpConfigManager {
    /// Create a new configuration manager with the specified config path
    pub async fn new(config_path: PathBuf) -> Result<Self> {
        let config = if config_path.exists() {
            Self::load_config(&config_path).await?
        } else {
            info!("MCP config file not found, creating default configuration");
            let default_config = McpConfig::default();
            Self::save_config(&config_path, &default_config).await?;
            default_config
        };

        Ok(Self {
            config_path,
            config,
        })
    }

    /// Load configuration from file
    async fn load_config(path: &PathBuf) -> Result<McpConfig> {
        debug!("Loading MCP configuration from {}", path.display());

        let content = fs::read_to_string(path).await
            .map_err(|e| anyhow!("Failed to read MCP config file: {}", e))?;

        let config: McpConfig = serde_json::from_str(&content)
            .map_err(|e| anyhow!("Failed to parse MCP config file: {}", e))?;

        info!("Loaded MCP configuration with {} servers", config.servers.len());
        Ok(config)
    }

    /// Save configuration to file
    async fn save_config(path: &PathBuf, config: &McpConfig) -> Result<()> {
        debug!("Saving MCP configuration to {}", path.display());

        // Create parent directory if it doesn't exist
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).await
                .map_err(|e| anyhow!("Failed to create config directory: {}", e))?;
        }

        let content = serde_json::to_string_pretty(config)
            .map_err(|e| anyhow!("Failed to serialize MCP config: {}", e))?;

        fs::write(path, content).await
            .map_err(|e| anyhow!("Failed to write MCP config file: {}", e))?;

        Ok(())
    }

    /// Get the current configuration
    pub fn get_config(&self) -> &McpConfig {
        &self.config
    }

    /// Get enabled server configurations
    pub fn get_enabled_servers(&self) -> HashMap<String, &McpServerConfig> {
        self.config.servers
            .iter()
            .filter(|(_, config)| config.enabled)
            .map(|(id, config)| (id.clone(), config))
            .collect()
    }

    /// Get configuration for a specific server
    pub fn get_server_config(&self, server_id: &str) -> Option<&McpServerConfig> {
        self.config.servers.get(server_id)
    }

    /// Save current configuration to file
    pub async fn save_current_config(&self) -> Result<()> {
        Self::save_config(&self.config_path, &self.config).await
    }

    /// Update server configuration
    pub async fn update_server_config(&mut self, server_id: &str, config: McpServerConfig) -> Result<()> {
        self.config.servers.insert(server_id.to_string(), config);
        self.save_current_config().await?;
        info!("Updated configuration for server: {}", server_id);
        Ok(())
    }

    /// Enable or disable a server
    pub async fn set_server_enabled(&mut self, server_id: &str, enabled: bool) -> Result<()> {
        if let Some(server) = self.config.servers.get_mut(server_id) {
            server.enabled = enabled;
            self.save_current_config().await?;
            info!("{} server: {}", if enabled { "Enabled" } else { "Disabled" }, server_id);
            Ok(())
        } else {
            Err(anyhow!("Server '{}' not found in configuration", server_id))
        }
    }

    /// Add a new server configuration
    pub async fn add_server(&mut self, server_id: &str, config: McpServerConfig) -> Result<()> {
        if self.config.servers.contains_key(server_id) {
            return Err(anyhow!("Server '{}' already exists", server_id));
        }

        self.config.servers.insert(server_id.to_string(), config);
        self.save_current_config().await?;
        info!("Added new server configuration: {}", server_id);
        Ok(())
    }

    /// Remove a server configuration
    pub async fn remove_server(&mut self, server_id: &str) -> Result<()> {
        if self.config.servers.remove(server_id).is_none() {
            return Err(anyhow!("Server '{}' not found in configuration", server_id));
        }

        self.save_current_config().await?;
        info!("Removed server configuration: {}", server_id);
        Ok(())
    }

    /// Update global settings
    pub async fn update_global_settings(&mut self, settings: McpGlobalSettings) -> Result<()> {
        self.config.global_settings = settings;
        self.save_current_config().await?;
        info!("Updated global MCP settings");
        Ok(())
    }

    /// Reload configuration from file
    pub async fn reload(&mut self) -> Result<()> {
        info!("Reloading MCP configuration");
        self.config = Self::load_config(&self.config_path).await?;
        Ok(())
    }

    /// Validate configuration
    pub fn validate(&self) -> Result<()> {
        // Check if at least one server is enabled
        let enabled_count = self.config.servers
            .values()
            .filter(|config| config.enabled)
            .count();

        if enabled_count == 0 {
            warn!("No MCP servers are enabled in configuration");
        }

        // Validate each server configuration
        for (server_id, config) in &self.config.servers {
            if config.enabled {
                if config.command.is_empty() {
                    return Err(anyhow!("Server '{}' has empty command", server_id));
                }

                if config.timeout_seconds == 0 {
                    return Err(anyhow!("Server '{}' has invalid timeout", server_id));
                }
            }
        }

        // Validate global settings
        if self.config.global_settings.max_concurrent_servers == 0 {
            return Err(anyhow!("max_concurrent_servers must be greater than 0"));
        }

        if self.config.global_settings.default_timeout_seconds == 0 {
            return Err(anyhow!("default_timeout_seconds must be greater than 0"));
        }

        debug!("MCP configuration validation passed");
        Ok(())
    }

    /// Get configuration summary for logging
    pub fn get_summary(&self) -> String {
        let enabled_servers: Vec<&String> = self.config.servers
            .iter()
            .filter(|(_, config)| config.enabled)
            .map(|(id, _)| id)
            .collect();

        format!(
            "MCP Config v{} - {}/{} servers enabled, max concurrent: {}, metrics: {}",
            self.config.version,
            enabled_servers.len(),
            self.config.servers.len(),
            self.config.global_settings.max_concurrent_servers,
            self.config.global_settings.enable_metrics
        )
    }

  
    /// Export configuration to a different path
    pub async fn export_config(&self, export_path: &PathBuf) -> Result<()> {
        info!("Exporting MCP configuration to {}", export_path.display());
        Self::save_config(export_path, &self.config).await
    }

    /// Import configuration from a different path
    pub async fn import_config(&mut self, import_path: &PathBuf) -> Result<()> {
        info!("Importing MCP configuration from {}", import_path.display());
        let imported_config = Self::load_config(import_path).await?;
        self.config = imported_config;
        self.save_current_config().await?;
        Ok(())
    }

    /// Reset configuration to defaults
    pub async fn reset_to_defaults(&mut self) -> Result<()> {
        info!("Resetting MCP configuration to defaults");
        self.config = McpConfig::default();
        self.save_current_config().await?;
        Ok(())
    }

    /// Get tool filters for a server
    pub fn get_tool_filters(&self, server_id: &str) -> Option<&ToolFilters> {
        self.config.servers
            .get(server_id)
            .and_then(|config| config.tool_filters.as_ref())
    }

    /// Check if a tool is allowed for a server
    pub fn is_tool_allowed(&self, server_id: &str, tool_name: &str) -> bool {
        if let Some(config) = self.config.servers.get(server_id) {
            if let Some(filters) = &config.tool_filters {
                // Check denied lists first
                if let Some(denied_tools) = &filters.denied_tools {
                    if denied_tools.contains(&tool_name.to_string()) {
                        return false;
                    }
                }

                if let Some(denied_patterns) = &filters.denied_patterns {
                    for pattern in denied_patterns {
                        if tool_name.contains(pattern) {
                            return false;
                        }
                    }
                }

                // If allow lists exist, tool must be in them
                if let Some(allowed_tools) = &filters.allowed_tools {
                    return allowed_tools.contains(&tool_name.to_string());
                }

                if let Some(allowed_patterns) = &filters.allowed_patterns {
                    return allowed_patterns.iter().any(|pattern| tool_name.contains(pattern));
                }
            }
            // No filters or only deny filters - tool is allowed
            true
        } else {
            false // Server not found
        }
    }

    /// Get the path to the bundled binary for a server
    pub fn get_bundled_binary_path(&self, server_id: &str) -> Option<PathBuf> {
        let config = self.config.servers.get(server_id)?;

        // Return custom path if specified
        if let Some(custom_path) = &config.binary_path {
            return Some(custom_path.clone());
        }

        // Generate default bundled binary path
        let platform_dir = match std::env::consts::OS {
            "windows" => "windows",
            "macos" => "macos",
            "linux" => "linux",
            _ => return None,
        };

        let binary_name = match server_id {
            "desktop-commander" => "desktop-commander",
            "sequential-thinking" => "sequential-thinking",
            "context7" => "context7",
            _ => return None,
        };

        let mut binary_path = PathBuf::from("resources/mcp")
            .join(platform_dir)
            .join(binary_name);

        if std::env::consts::OS == "windows" {
            binary_path.set_extension("exe");
        }

        Some(binary_path)
    }

    /// Determine if bundled binaries should be used by default
    pub fn should_use_bundled_by_default() -> bool {
        // Use bundled binaries in release mode, npx in debug mode
        !cfg!(debug_assertions)
    }
}