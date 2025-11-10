use anyhow::Result;
use std::path::PathBuf;
use std::time::Duration;
use tauri::{AppHandle, Manager, Emitter};
use tauri::path::BaseDirectory;
use tauri_plugin_shell::{process::{CommandChild, CommandEvent}, ShellExt};

#[derive(Default)]
pub struct LiteLLMState {
    pub child: Option<CommandChild>,
    pub port: u16,
    pub master_key: Option<String>,
    pub config_resolved_path: Option<PathBuf>,
}

impl LiteLLMState {
    pub fn is_running(&self) -> bool {
        self.child.is_some()
    }
}

#[derive(serde::Serialize, Debug, Clone, Copy)]
struct SidecarStatusPayload {
    running: bool,
    port: Option<u16>,
}


/// Resolve the bundled litellm_config.yaml path inside app resources
fn resolve_config_path(app: &AppHandle) -> Result<PathBuf> {
    let path = app
        .path()
        .resolve("litellm_config.yaml", BaseDirectory::Resource)?;
    Ok(path)
}


/// Try to locate the `litellm` binary even when PATH is minimal (e.g., GUI launch on macOS)
fn find_litellm_cmd() -> Option<String> {
    // Search current PATH
    if let Some(paths) = std::env::var_os("PATH") {
        for dir in std::env::split_paths(&paths) {
            let candidate = dir.join("litellm");
            if candidate.exists() {
                if let Some(s) = candidate.to_str() {
                    return Some(s.to_string());
                }
            }
        }
    }
    // Common absolute locations
    let fallbacks = [
        "/opt/homebrew/bin/litellm",
        "/usr/local/bin/litellm",
        "/usr/bin/litellm",
    ];
    for p in fallbacks {
        if std::path::Path::new(p).exists() {
            return Some(p.to_string());
        }
    }
    None
}

/// Start LiteLLM proxy as a managed child process via tauri-plugin-shell
/// - Sets OPENROUTER_API_KEY and LITELLM_MASTER_KEY env for the child
/// - Uses the bundled resources/litellm_config.yaml
pub fn start_litellm(
    app: &AppHandle,
    state: &mut LiteLLMState,
    openrouter_api_key: Option<&str>,
    master_key: &str,
    port: u16,
) -> Result<()> {
    if state.is_running() {
        // Already running
        return Ok(());
    }

    let config_path = resolve_config_path(app)?;

    // Prefer spawning a system-installed `litellm` binary.
    // Try to find absolute path on macOS/Linux when PATH is sanitized (e.g., GUI launch)
    let litellm_cmd = find_litellm_cmd().unwrap_or_else(|| "litellm".to_string());
    // Command: litellm proxy --host 127.0.0.1 --port <port> --config <config_path>
    let mut cmd = app
        .shell()
        .command(&litellm_cmd)
        .arg("proxy")
        .args(["--host", "127.0.0.1"])
        .args(["--port", &port.to_string()])
        .args(["--config", &config_path.to_string_lossy()]);

    // Inject secrets only into the child process environment
    if let Some(k) = openrouter_api_key {
        cmd = cmd.env("OPENROUTER_API_KEY", k);
    }
    cmd = cmd.env("LITELLM_MASTER_KEY", master_key);

    let (rx, child) = cmd.spawn().map_err(|e| {
        anyhow::anyhow!(
            "Failed to spawn litellm (cmd='{}'): {}. Install with: pipx install 'litellm[proxy]' or pip3 install 'litellm[proxy]'. If already installed, ensure it's on PATH or update capabilities to allow its absolute path.",
            litellm_cmd,
            e
        )
    })?;

    // Spawn listener to emit event when the sidecar terminates unexpectedly
    let app_for_thread = app.clone();
    let port_for_thread = port;
    tauri::async_runtime::spawn(async move {
        let mut rx = rx;
        while let Some(event) = rx.recv().await {
            if let CommandEvent::Terminated(..) = event {
                let _ = app_for_thread.emit(
                    "litellm-status",
                    SidecarStatusPayload { running: false, port: Some(port_for_thread) },
                );
                break;
            }
        }
    });

    // Save state
    state.child = Some(child);
    state.port = port;
    state.master_key = Some(master_key.to_string());
    state.config_resolved_path = Some(config_path);

    // Emit started event
    let _ = app.emit(
        "litellm-status",
        SidecarStatusPayload { running: true, port: Some(port) },
    );

    Ok(())
}

pub fn stop_litellm(state: &mut LiteLLMState) -> Result<()> {
    if let Some(child) = state.child.take() {
        // Best-effort kill; ignore errors if already exited
        let _ = child.kill();
        // Allow a short grace period
        std::thread::sleep(Duration::from_millis(200));
    }
    state.master_key = None;
    Ok(())
}

