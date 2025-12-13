//! Sidecar management for the Python brain process

use std::sync::atomic::{AtomicBool, Ordering};
use tauri::AppHandle;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandChild;
use std::sync::Mutex;

static BRAIN_RUNNING: AtomicBool = AtomicBool::new(false);
static BRAIN_PROCESS: Mutex<Option<CommandChild>> = Mutex::new(None);

/// Spawn the brain sidecar process
pub async fn spawn_brain(app: &AppHandle) -> Result<(), String> {
    if BRAIN_RUNNING.load(Ordering::SeqCst) {
        return Ok(());
    }

    let shell = app.shell();
    
    let (mut rx, child) = shell
        .sidecar("godoty-brain")
        .map_err(|e| format!("Failed to create sidecar command: {}", e))?
        .args(["--host", "127.0.0.1", "--port", "8000"])
        .spawn()
        .map_err(|e| format!("Failed to spawn brain process: {}", e))?;

    // Store the child process handle
    {
        let mut process = BRAIN_PROCESS.lock().unwrap();
        *process = Some(child);
    }
    
    BRAIN_RUNNING.store(true, Ordering::SeqCst);

    // Handle stdout/stderr in background
    tauri::async_runtime::spawn(async move {
        use tauri_plugin_shell::process::CommandEvent;
        
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    println!("[Brain] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Stderr(line) => {
                    eprintln!("[Brain] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Terminated(payload) => {
                    println!("[Brain] Process terminated with code: {:?}", payload.code);
                    BRAIN_RUNNING.store(false, Ordering::SeqCst);
                    break;
                }
                _ => {}
            }
        }
    });

    // Wait a moment for the server to start
    tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;
    
    Ok(())
}

#[tauri::command]
pub async fn start_brain(app: AppHandle) -> Result<String, String> {
    spawn_brain(&app).await?;
    Ok("Brain started".to_string())
}

#[tauri::command]
pub async fn stop_brain() -> Result<String, String> {
    let mut process = BRAIN_PROCESS.lock().unwrap();
    if let Some(child) = process.take() {
        child.kill().map_err(|e| format!("Failed to kill brain process: {}", e))?;
        BRAIN_RUNNING.store(false, Ordering::SeqCst);
        Ok("Brain stopped".to_string())
    } else {
        Ok("Brain was not running".to_string())
    }
}

#[tauri::command]
pub fn get_brain_status() -> bool {
    BRAIN_RUNNING.load(Ordering::SeqCst)
}
