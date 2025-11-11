use anyhow::{anyhow, Result};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, ChildStdout, Command};

/// Minimal stdio JSON-RPC client for MCP DesktopCommander
pub struct McpClient {
    #[allow(dead_code)]
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    next_id: i64,
    project_root: PathBuf,
}

impl McpClient {
    /// Spawns the DesktopCommander MCP server via npx and performs a best-effort initialize handshake.
    pub async fn new(project_root: &Path) -> Result<Self> {
        let mut cmd = Command::new("npx");
        cmd.arg("-y")
            .arg("@wonderwhy-er/desktop-commander@latest")
            .current_dir(project_root)
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::inherit());

        let mut child = cmd.spawn().map_err(|e| anyhow!(
            "Failed to spawn DesktopCommander MCP (is Node/npm installed and npx on PATH?): {}",
            e
        ))?;

        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| anyhow!("Failed to open MCP stdin"))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| anyhow!("Failed to open MCP stdout"))?;

        let mut client = McpClient {
            child,
            stdin,
            stdout: BufReader::new(stdout),
            next_id: 1,
            project_root: project_root.to_path_buf(),
        };

        // Best-effort initialize; ignore failures (some servers may not require it)
        let _ = client.initialize().await;

        Ok(client)
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

    /// Call a DesktopCommander tool by name with args object
    pub async fn call_tool(&mut self, tool: &str, mut args: Value) -> Result<Value> {
        if !args.is_object() {
            args = json!({});
        }
        // Ensure all paths are project-root relative by setting cwd via spawn; still sanity-check here
        self.validate_paths_within_root(&args)?;

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
            return Err(anyhow!("MCP error: {}", err));
        }
        Ok(resp.get("result").cloned().unwrap_or(resp))
    }

    fn validate_paths_within_root(&self, args: &Value) -> Result<()> {
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
                                if k.to_lowercase().contains("path") { check_one(&self.project_root, s)?; }
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
            if n == 0 { return Err(anyhow!("MCP server closed stdout")); }
            let l = line.trim_end_matches(['\r','\n']);
            if l.is_empty() { break; }
            if let Some(rest) = l.strip_prefix("Content-Length:") {
                content_length = Some(rest.trim().parse::<usize>().map_err(|e| anyhow!(e))?);
            }
        }
        let len = content_length.ok_or_else(|| anyhow!("Missing Content-Length header from MCP"))?;
        let mut buf = vec![0u8; len];
        self.stdout.read_exact(&mut buf).await?;
        let v: Value = serde_json::from_slice(&buf)?;
        Ok(v)
    }
}

