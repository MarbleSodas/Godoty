use anyhow::Result;
use std::path::PathBuf;
use std::time::Duration;
use std::sync::{Mutex, OnceLock};
use tauri::{AppHandle, Emitter, Manager};
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
enum RagExecutable {
    Bundled(PathBuf),  // Standalone bundled executable
    Python { cmd: String, script: PathBuf },  // Python interpreter + script
}

fn find_bundled_executable(app: &AppHandle) -> Option<PathBuf> {
    // Determine the executable name based on platform
    let exe_name = if cfg!(target_os = "windows") {
        "rag_server.exe"
    } else {
        "rag_server"
    };

    // Try to resolve from resources directory
    match app.path().resolve(exe_name, tauri::path::BaseDirectory::Resource) {
        Ok(exe_path) => {
            // Check if it exists (it might not in dev builds)
            if exe_path.exists() {
                println!("Found bundled RAG executable at: {:?}", exe_path);
                return Some(exe_path);
            } else {
                println!("Executable path resolved but file doesn't exist: {:?}", exe_path);
            }
        }
        Err(e) => {
            println!("Could not resolve executable path: {}", e);
        }
    }

    None
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

fn find_rag_executable(app: &AppHandle) -> Result<RagExecutable> {
    // First, try to find bundled executable
    if let Some(bundled_path) = find_bundled_executable(app) {
        println!("Using bundled RAG executable");
        return Ok(RagExecutable::Bundled(bundled_path));
    }

    // Fall back to Python + script
    println!("Bundled executable not found, falling back to Python interpreter");
    let script_path = write_embedded_server_script(app)?;
    let found = find_python_cmd().ok_or_else(|| {
        anyhow::anyhow!("Python not found. Please install Python or use a bundled build.")
    })?;

    Ok(RagExecutable::Python {
        cmd: found.cmd,
        script: script_path,
    })
}

pub fn start_rag(app: &AppHandle, state: &mut RagSidecarState, port: u16) -> Result<()> {
    if state.is_running() { return Ok(()); }
    clear_last_error();

    // Find the appropriate executable (bundled or Python)
    let executable = find_rag_executable(app)?;

    // Prepare command based on executable type
    let mut cmd = match &executable {
        RagExecutable::Bundled(exe_path) => {
            println!("Starting bundled RAG server from: {:?}", exe_path);
            app.shell().command(exe_path.to_string_lossy().to_string())
        }
        RagExecutable::Python { cmd: python_cmd, script } => {
            println!("Starting RAG server with Python: {} {:?}", python_cmd, script);
            let mut c = app.shell().command(python_cmd);
            c = c.arg("-u").arg(script);
            c
        }
    };

    // Set environment variables
    let mut rag_root = Storage::get_config_dir()?; rag_root.push("rag_db");
    cmd = cmd.env("RAG_DB_ROOT", rag_root.to_string_lossy().to_string());
    cmd = cmd.env("RAG_PORT", port.to_string());
    cmd = cmd.env("RAG_EMBEDDING_MODEL", std::env::var("RAG_EMBEDDING_MODEL").unwrap_or_else(|_| "sentence-transformers/all-MiniLM-L6-v2".into()));

    let (rx, child) = match cmd.spawn() {
        Ok(ok) => ok,
        Err(e) => {
            let msg = match &executable {
                RagExecutable::Bundled(path) => {
                    format!("Failed to spawn bundled RAG server (path='{}'): {}.", path.display(), e)
                }
                RagExecutable::Python { cmd: python_cmd, .. } => {
                    format!("Failed to spawn Python for RAG sidecar (cmd='{}'): {}. Ensure Python is installed and accessible on PATH.", python_cmd, e)
                }
            };
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
    state.script_path = match executable {
        RagExecutable::Bundled(path) => Some(path),
        RagExecutable::Python { script, .. } => Some(script),
    };

    let _ = app.emit("rag-status", RagStatusPayload{running:true, port:Some(port), last_error:None});
    Ok(())
}

pub fn stop_rag(state: &mut RagSidecarState) -> Result<()> {
    if let Some(child) = state.child.take() { let _ = child.kill(); std::thread::sleep(Duration::from_millis(200)); }
    Ok(())
}

