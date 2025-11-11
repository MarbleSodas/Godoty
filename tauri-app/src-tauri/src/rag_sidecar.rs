use anyhow::Result;
use std::path::PathBuf;
use std::time::Duration;
use std::sync::{Mutex, OnceLock};
use tauri::{AppHandle, Emitter};
use tauri_plugin_shell::{process::{CommandChild, CommandEvent}, ShellExt};

use crate::storage::Storage;

static LAST_ERROR: OnceLock<Mutex<Option<String>>> = OnceLock::new();
fn last_err() -> &'static Mutex<Option<String>> { LAST_ERROR.get_or_init(|| Mutex::new(None)) }
pub fn set_last_error(msg: String) { if let Ok(mut g) = last_err().lock() { *g = Some(msg); } }
pub fn get_last_error() -> Option<String> { last_err().lock().ok().and_then(|g| g.clone()) }
pub fn clear_last_error() { if let Ok(mut g) = last_err().lock() { *g = None; } }

#[derive(Default)]
pub struct RagSidecarState {
    pub child: Option<CommandChild>,
    pub port: u16,
    pub script_path: Option<PathBuf>,
}

impl RagSidecarState { pub fn is_running(&self) -> bool { self.child.is_some() } }

#[derive(serde::Serialize, Debug, Clone)]
struct RagStatusPayload { running: bool, port: Option<u16>, last_error: Option<String> }

fn write_embedded_server_script(_app: &AppHandle) -> Result<PathBuf> {
    // Embed rag_server.py at compile time and write it under the config dir
    let code: &str = include_str!("../rag_server.py");
    let mut dir = Storage::get_config_dir()?;
    dir.push("rag_sidecar");
    std::fs::create_dir_all(&dir)?;
    let path = dir.join("rag_server.py");
    // Write only if missing or size differs
    let needs_write = match std::fs::read_to_string(&path) { Ok(existing) => existing != code, Err(_) => true };
    if needs_write { std::fs::write(&path, code)?; }
    Ok(path)
}

#[derive(Debug, Clone)]
struct FoundPy { cmd: String }
fn find_python_cmd() -> Option<FoundPy> {
    // Respect override
    if let Ok(override_cmd) = std::env::var("RAG_PYTHON_CMD") {
        if !override_cmd.trim().is_empty() { return Some(FoundPy{cmd:override_cmd}); }
    }
    fn exists_in_dir(dir: &std::path::Path, names: &[&str]) -> Option<String> {
        for name in names {
            let candidate = dir.join(name);
            if candidate.exists() {
                if let Some(s) = candidate.to_str() { return Some(s.to_string()); }
            }
        }
        None
    }
    if let Some(paths) = std::env::var_os("PATH") {
        for dir in std::env::split_paths(&paths) {
            if cfg!(target_os = "windows") {
                if let Some(s) = exists_in_dir(&dir, &["py.exe","py","python.exe","python"]) {
                    return Some(FoundPy{cmd:s});
                }
            } else if let Some(s) = exists_in_dir(&dir, &["python3","python"]) {
                return Some(FoundPy{cmd:s});
            }
        }
    }
    // Fallbacks
    if cfg!(target_os = "windows") { Some(FoundPy{cmd:"py".into()}) } else { Some(FoundPy{cmd:"python3".into()}) }
}

pub fn start_rag(app: &AppHandle, state: &mut RagSidecarState, port: u16) -> Result<()> {
    if state.is_running() { return Ok(()); }
    clear_last_error();

    let script_path = write_embedded_server_script(app)?;

    // Prepare command
    let found = find_python_cmd().unwrap_or(FoundPy{cmd:"python".into()});
    let mut cmd = app.shell().command(&found.cmd);
    cmd = cmd.arg("-u").arg(&script_path);

    // Env
    let mut rag_root = Storage::get_config_dir()?; rag_root.push("rag_db");
    cmd = cmd.env("RAG_DB_ROOT", rag_root.to_string_lossy().to_string());
    cmd = cmd.env("RAG_PORT", port.to_string());
    cmd = cmd.env("RAG_EMBEDDING_MODEL", std::env::var("RAG_EMBEDDING_MODEL").unwrap_or_else(|_| "sentence-transformers/all-MiniLM-L6-v2".into()));

    let (rx, child) = match cmd.spawn() {
        Ok(ok) => ok,
        Err(e) => {
            let msg = format!("Failed to spawn Python for RAG sidecar (cmd='{}'): {}. Ensure Python is installed and accessible on PATH.", found.cmd, e);
            set_last_error(msg.clone());
            let _ = app.emit("rag-status", RagStatusPayload{running:false, port:Some(port), last_error:Some(msg)});
            return Err(anyhow::anyhow!(e));
        }
    };

    // Listen to process output
    let app_for_thread = app.clone();
    let port_for_thread = port;
    tauri::async_runtime::spawn(async move {
        let mut rx = rx;
        while let Some(ev) = rx.recv().await {
            match ev {
                CommandEvent::Stdout(line) => { println!("RAG: {}", String::from_utf8_lossy(&line)); },
                CommandEvent::Stderr(line) => {
                    let msg = String::from_utf8_lossy(&line).to_string();
                    eprintln!("RAG Error: {}", msg);
                    set_last_error(msg.clone());
                    let _ = app_for_thread.emit("rag-status", RagStatusPayload{running:true, port:Some(port_for_thread), last_error:Some(msg)});
                },
                CommandEvent::Terminated(..) => {
                    let _ = app_for_thread.emit("rag-status", RagStatusPayload{running:false, port:Some(port_for_thread), last_error:get_last_error()});
                    break;
                },
                _ => {}
            }
        }
    });

    state.child = Some(child);
    state.port = port;
    state.script_path = Some(script_path);

    let _ = app.emit("rag-status", RagStatusPayload{running:true, port:Some(port), last_error:None});
    Ok(())
}

pub fn stop_rag(state: &mut RagSidecarState) -> Result<()> {
    if let Some(child) = state.child.take() { let _ = child.kill(); std::thread::sleep(Duration::from_millis(200)); }
    Ok(())
}

