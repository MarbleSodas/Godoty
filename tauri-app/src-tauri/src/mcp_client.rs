use anyhow::{anyhow, Result};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, ChildStdout, Command};
use tracing::{debug, info, warn, error};

/// Configuration for an MCP server
#[derive(Debug, Clone)]
pub struct McpServerConfig {
    pub server_id: String,
    pub command: String,
    pub args: Vec<String>,
    #[allow(dead_code)] // Description used for logging and debugging
    pub description: String,
    pub enabled: bool,
    /// Use bundled binary instead of external command
    pub use_bundled: bool,
    /// Optional custom path to bundled binary
    pub binary_path: Option<std::path::PathBuf>,
}

impl Default for McpServerConfig {
    fn default() -> Self {
        Self {
            server_id: "desktop-commander".to_string(),
            command: "npx".to_string(),
            args: vec!["-y".to_string(), "@wonderwhy-er/desktop-commander@latest".to_string()],
            description: "Desktop file system and process management".to_string(),
            enabled: true,
            use_bundled: false,
            binary_path: None,
        }
    }
}

/// Individual MCP server connection
pub struct McpServerConnection {
    #[allow(dead_code)]
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    next_id: i64,
    config: McpServerConfig,
}

impl McpServerConnection {
    pub async fn new(config: McpServerConfig, project_root: &Path) -> Result<Self> {
        let (command, args, command_type) = {
            // Try custom binary path first, then auto-discovered bundled binary
            if let Some(custom_binary_path) = &config.binary_path {
                if custom_binary_path.exists() {
                    info!(
                        server_id = %config.server_id,
                        binary_path = %custom_binary_path.display(),
                        "Starting MCP server with custom bundled binary"
                    );
                    (custom_binary_path.to_string_lossy().to_string(), vec![], "bundled")
                } else {
                    warn!(
                        server_id = %config.server_id,
                        binary_path = %custom_binary_path.display(),
                        "Custom bundled binary not found, falling back to auto-discovery"
                    );
                    // Try auto-discovered bundled binary
                    if let Some(binary_path) = get_bundled_binary_path(&config.server_id) {
                        info!(
                            server_id = %config.server_id,
                            binary_path = %binary_path.display(),
                            "Starting MCP server with auto-discovered bundled binary"
                        );
                        (binary_path.to_string_lossy().to_string(), vec![], "bundled")
                    } else {
                        // No bundled binary available, fall back to npx
                        warn!(
                            server_id = %config.server_id,
                            "No bundled binary available, falling back to npx"
                        );
                        let package_name = get_package_name_for_server(&config.server_id);
                        (get_npx_command(), vec!["-y".to_string(), package_name], "fallback")
                    }
                }
            } else if let Some(binary_path) = get_bundled_binary_path(&config.server_id) {
                info!(
                    server_id = %config.server_id,
                    binary_path = %binary_path.display(),
                    "Starting MCP server with auto-discovered bundled binary"
                );
                (binary_path.to_string_lossy().to_string(), vec![], "bundled")
            } else {
                // No bundled binary available, use configured command (npx or fallback)
                if config.use_bundled {
                    warn!(
                        server_id = %config.server_id,
                        "Bundled binary not found, falling back to npx"
                    );
                    // We wanted to use bundled but it's not available, fall back to npx
                    let package_name = get_package_name_for_server(&config.server_id);
                    (get_npx_command(), vec!["-y".to_string(), package_name], "fallback")
                } else {
                    info!(
                        server_id = %config.server_id,
                        command = %config.command,
                        "Starting MCP server with external command"
                    );
                    // Use the configured external command, but replace "npx" with full path if needed
                    let command = if config.command == "npx" {
                        get_npx_command()
                    } else {
                        config.command.clone()
                    };
                    (command, config.args.clone(), "external")
                }
            }
        };

        let mut cmd = Command::new(&command);
        cmd.args(&args)
            .current_dir(project_root)
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::inherit());

        let mut child = cmd.spawn().map_err(|e| anyhow!(
            "Failed to spawn MCP server '{}' (command: {}, type: {}): {}",
            config.server_id,
            command,
            command_type,
            e
        ))?;

        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| anyhow!("Failed to open MCP stdin for {}", config.server_id))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| anyhow!("Failed to open MCP stdout for {}", config.server_id))?;

        let mut connection = McpServerConnection {
            child,
            stdin,
            stdout: BufReader::new(stdout),
            next_id: 1,
            config,
        };

        // Best-effort initialize; ignore failures (some servers may not require it)
        let _ = connection.initialize().await;

        Ok(connection)
    }

    async fn initialize(&mut self) -> Result<()> {
        let id = self.next_id();
        let payload = json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": "initialize",
            "params": {
                "clientInfo": {"name": "Godoty", "version": "0.1.0"},
                "protocolVersion": "2024-11-05"
            }
        });
        self.write_message(&payload).await?;
        let _ = self.read_until_id(id).await?; // ignore contents
        Ok(())
    }

    fn next_id(&mut self) -> i64 {
        let id = self.next_id;
        self.next_id += 1;
        id
    }

    /// Call a tool on this specific MCP server
    pub async fn call_tool(&mut self, tool: &str, mut args: Value) -> Result<Value> {
        if !args.is_object() {
            args = json!({});
        }

        debug!(
            server_id = %self.config.server_id,
            tool_name = %tool,
            args = %args,
            "Calling MCP tool"
        );

        let id = self.next_id();
        let payload = json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": "tools/call",
            "params": { "name": tool, "arguments": args }
        });
        self.write_message(&payload).await?;
        let resp = self.read_until_id(id).await?;

        // Standard JSON-RPC response: {result:{...}} or {error:{...}}
        if let Some(err) = resp.get("error") {
            error!(
                server_id = %self.config.server_id,
                tool_name = %tool,
                error = %err,
                "MCP tool error"
            );
            return Err(anyhow!("MCP error from server '{}': {}", self.config.server_id, err));
        }

        debug!(
            server_id = %self.config.server_id,
            tool_name = %tool,
            "MCP tool executed successfully"
        );

        Ok(resp.get("result").cloned().unwrap_or(resp))
    }

    /// List available tools on this server
    #[allow(dead_code)] // Available for debugging and tool discovery
    pub async fn list_tools(&mut self) -> Result<Value> {
        let id = self.next_id();
        let payload = json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": "tools/list"
        });
        self.write_message(&payload).await?;
        let resp = self.read_until_id(id).await?;

        if let Some(err) = resp.get("error") {
            return Err(anyhow!("Failed to list tools from server '{}': {}", self.config.server_id, err));
        }

        Ok(resp.get("result").cloned().unwrap_or(resp))
    }

    async fn write_message(&mut self, msg: &Value) -> Result<()> {
        let bytes = serde_json::to_vec(msg)?;
        let header = format!("Content-Length: {}\r\n\r\n", bytes.len());
        self.stdin.write_all(header.as_bytes()).await?;
        self.stdin.write_all(&bytes).await?;
        self.stdin.flush().await?;
        Ok(())
    }

    async fn read_until_id(&mut self, target_id: i64) -> Result<Value> {
        loop {
            let msg = self.read_one_message().await?;
            let id = msg.get("id").and_then(|v| v.as_i64());
            if id == Some(target_id) { return Ok(msg); }
            // Ignore notifications or other responses
        }
    }

    async fn read_one_message(&mut self) -> Result<Value> {
        // Read headers
        let mut content_length: Option<usize> = None;
        loop {
            let mut line = String::new();
            let n = self.stdout.read_line(&mut line).await?;
            if n == 0 {
                return Err(anyhow!("MCP server '{}' closed stdout", self.config.server_id));
            }
            let l = line.trim_end_matches(['\r','\n']);
            if l.is_empty() { break; }
            if let Some(rest) = l.strip_prefix("Content-Length:") {
                content_length = Some(rest.trim().parse::<usize>().map_err(|e| anyhow!(e))?);
            }
        }
        let len = content_length.ok_or_else(|| anyhow!("Missing Content-Length header from MCP server '{}'", self.config.server_id))?;
        let mut buf = vec![0u8; len];
        self.stdout.read_exact(&mut buf).await?;
        let v: Value = serde_json::from_slice(&buf)?;
        Ok(v)
    }
}

/// Multi-server MCP client manager
pub struct McpClientManager {
    connections: HashMap<String, McpServerConnection>,
    project_root: PathBuf,
    server_configs: Vec<McpServerConfig>,
}

impl McpClientManager {
    pub async fn new(project_root: &Path) -> Result<Self> {
        let mut manager = Self {
            connections: HashMap::new(),
            project_root: project_root.to_path_buf(),
            server_configs: Self::default_server_configs(),
        };

        manager.initialize_connections().await?;
        Ok(manager)
    }

    /// Get default server configurations for the three main MCP servers
    fn default_server_configs() -> Vec<McpServerConfig> {
        vec![
            // Desktop Commander - File system and process management
            McpServerConfig {
                server_id: "desktop-commander".to_string(),
                command: "npx".to_string(),
                args: vec![
                    "-y".to_string(),
                    "@wonderwhy-er/desktop-commander@latest".to_string()
                ],
                description: "Desktop file system, search, and process management".to_string(),
                enabled: true,
                use_bundled: false, // Will be enabled after build system integration
                binary_path: None,
            },
            // Sequential Thinking - Enhanced reasoning capabilities
            McpServerConfig {
                server_id: "sequential-thinking".to_string(),
                command: "npx".to_string(),
                args: vec![
                    "-y".to_string(),
                    "@modelcontextprotocol/server-sequential-thinking@latest".to_string()
                ],
                description: "Sequential thinking and reasoning tools".to_string(),
                enabled: true,
                use_bundled: false, // Will be enabled after build system integration
                binary_path: None,
            },
            // Context7 - Enhanced documentation and library access
            McpServerConfig {
                server_id: "context7".to_string(),
                command: "npx".to_string(),
                args: vec![
                    "-y".to_string(),
                    "@upstash/context7-mcp@latest".to_string()
                ],
                description: "Enhanced documentation and library access".to_string(),
                enabled: true,
                use_bundled: false, // Will be enabled after build system integration
                binary_path: None,
            },
        ]
    }

    /// Initialize all enabled server connections
    async fn initialize_connections(&mut self) -> Result<()> {
        let mut initialized = 0;
        let mut failed = vec![];

        for config in &self.server_configs.clone() {
            if !config.enabled {
                info!(server_id = %config.server_id, "Skipping disabled MCP server");
                continue;
            }

            match McpServerConnection::new(config.clone(), &self.project_root).await {
                Ok(connection) => {
                    info!(server_id = %config.server_id, "MCP server connected successfully");
                    self.connections.insert(config.server_id.clone(), connection);
                    initialized += 1;
                }
                Err(e) => {
                    warn!(
                        server_id = %config.server_id,
                        error = %e,
                        "Failed to connect to MCP server"
                    );
                    failed.push((config.server_id.clone(), e));
                }
            }
        }

        info!(
            initialized_servers = initialized,
            failed_servers = failed.len(),
            "MCP server initialization complete"
        );

        // Log failed connections but don't fail the entire manager if some servers are unavailable
        for (server_id, error) in failed {
            warn!(
                server_id = %server_id,
                error = %error,
                "MCP server unavailable - features requiring this server will be limited"
            );
        }

        Ok(())
    }

    /// Call a tool on the appropriate server
    pub async fn call_tool(&mut self, tool: &str, args: Value) -> Result<Value> {
        let server_id = self.determine_server_for_tool(tool)?;

        if let Some(connection) = self.connections.get_mut(&server_id) {
            connection.call_tool(tool, args).await
        } else {
            Err(anyhow!(
                "MCP server '{}' is not available for tool '{}'",
                server_id,
                tool
            ))
        }
    }

    /// Determine which server should handle a specific tool
    fn determine_server_for_tool(&self, tool: &str) -> Result<String> {
        match tool {
            // Desktop Commander tools
            tool if tool.starts_with("read_") || tool.starts_with("write_") ||
                 tool.contains("file") || tool.contains("directory") ||
                 tool.contains("search") || tool.contains("process") ||
                 tool == "list_directory" || tool == "create_directory" ||
                 tool == "move_file" || tool == "edit_block" ||
                 tool == "get_file_info" || tool == "start_process" ||
                 tool == "interact_with_process" || tool == "read_process" ||
                 tool == "list_processes" || tool == "kill_process" => {
                Ok("desktop-commander".to_string())
            }
            // Sequential Thinking tools
            tool if tool.contains("sequential") || tool.contains("thinking") ||
                 tool == "brainstorm" || tool == "reflect" => {
                Ok("sequential-thinking".to_string())
            }
            // Context7 tools
            tool if tool.contains("context7") || tool.contains("library") ||
                 tool.contains("documentation") || tool == "resolve_library_id" ||
                 tool == "get_library_docs" => {
                Ok("context7".to_string())
            }
            // Legacy support - try desktop-commander first
            _ => {
                if self.connections.contains_key("desktop-commander") {
                    Ok("desktop-commander".to_string())
                } else if !self.connections.is_empty() {
                    // Fallback to first available server
                    Ok(self.connections.keys().next().unwrap().clone())
                } else {
                    Err(anyhow!("No MCP servers available"))
                }
            }
        }
    }

    /// List all available tools from all connected servers
    #[allow(dead_code)] // Available for debugging and tool discovery
    pub async fn list_all_tools(&mut self) -> Result<Vec<(String, Vec<Value>)>> {
        let mut all_tools = Vec::new();

        for (server_id, connection) in &mut self.connections {
            match connection.list_tools().await {
                Ok(tools) => {
                    if let Some(tool_list) = tools.get("tools").and_then(|t| t.as_array()) {
                        all_tools.push((server_id.clone(), tool_list.clone()));
                    }
                }
                Err(e) => {
                    warn!(
                        server_id = %server_id,
                        error = %e,
                        "Failed to list tools from server"
                    );
                }
            }
        }

        Ok(all_tools)
    }

    /// Check if a specific server is available
    #[allow(dead_code)] // Available for server status checking
    pub fn is_server_available(&self, server_id: &str) -> bool {
        self.connections.contains_key(server_id)
    }

    /// Get list of available servers
    #[allow(dead_code)] // Available for server enumeration
    pub fn get_available_servers(&self) -> Vec<String> {
        self.connections.keys().cloned().collect()
    }

    /// Validate paths within project root (for desktop-commander only)
    pub fn validate_paths_within_root(&self, args: &Value) -> Result<()> {
        fn check_one(root: &Path, p: &str) -> Result<()> {
            let candidate = root.join(p);
            let canon = candidate.canonicalize().unwrap_or(candidate);
            if !canon.starts_with(root) {
                return Err(anyhow!(
                    "Path escapes project root: {} (root: {})",
                    canon.display(),
                    root.display()
                ));
            }
            Ok(())
        }

        if let Value::Object(map) = args {
            for (k, v) in map {
                match v {
                    Value::String(s) => {
                        // Heuristic: common path-like keys
                        let key = k.to_lowercase();
                        if ["path","from","to","source","target","sourcepath","targetpath"].contains(&key.as_str()) {
                            check_one(&self.project_root, s)?;
                        }
                    }
                    Value::Array(arr) => {
                        for item in arr {
                            if let Value::String(s) = item {
                                if k.to_lowercase().contains("path") {
                                    check_one(&self.project_root, s)?;
                                }
                            }
                        }
                    }
                    Value::Object(_) => self.validate_paths_within_root(v)?,
                    _ => {}
                }
            }
        }
        Ok(())
    }
}

/// Get the path to the bundled binary for a server
fn get_bundled_binary_path(server_id: &str) -> Option<std::path::PathBuf> {
    let platform_dir = match std::env::consts::OS {
        "windows" => "windows",
        "macos" => "macos",
        "linux" => "linux",
        _ => return None,
    };

    // Map server IDs to binary names
    let binary_name = match server_id {
        "desktop-commander" => "desktop-commander",
        "sequential-thinking" => "sequential-thinking",
        "context7" => "context7",
        _ => return None,
    };

    let mut binary_path = std::path::PathBuf::from("resources/mcp")
        .join(platform_dir)
        .join(binary_name);

    if std::env::consts::OS == "windows" {
        binary_path.set_extension("exe");
    }

    // Check if the binary exists
    if binary_path.exists() {
        Some(binary_path)
    } else {
        None
    }
}

/// Get the package name for a given server ID
fn get_package_name_for_server(server_id: &str) -> String {
    match server_id {
        "desktop-commander" => "@wonderwhy-er/desktop-commander@latest".to_string(),
        "sequential-thinking" => "@modelcontextprotocol/server-sequential-thinking@latest".to_string(),
        "context7" => "@upstash/context7-mcp@latest".to_string(),
        _ => format!("Unknown server: {}", server_id),
    }
}

// Get the npx command with full path to resolve PATH issues
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

// Legacy compatibility type alias
pub type McpClient = McpClientManager;