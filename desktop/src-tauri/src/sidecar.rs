//! Sidecar management for the Python brain process

use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;
use tauri::AppHandle;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandChild;
use std::sync::Mutex;

static BRAIN_RUNNING: AtomicBool = AtomicBool::new(false);
static BRAIN_PROCESS: Mutex<Option<CommandChild>> = Mutex::new(None);

const BRAIN_URL: &str = "http://127.0.0.1:8000";
const HEALTH_CHECK_TIMEOUT: Duration = Duration::from_secs(2);
const GRACEFUL_SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(3);
const STARTUP_TIMEOUT: Duration = Duration::from_secs(30);
const STARTUP_POLL_INTERVAL: Duration = Duration::from_millis(200);

/// Check if the brain server is responding to health checks
async fn check_brain_health() -> bool {
    let client = reqwest::Client::builder()
        .timeout(HEALTH_CHECK_TIMEOUT)
        .build();
    
    match client {
        Ok(client) => {
            match client.get(format!("{}/health", BRAIN_URL)).send().await {
                Ok(response) => response.status().is_success(),
                Err(_) => false,
            }
        }
        Err(_) => false,
    }
}

/// Wait for the brain to become ready with health checks
async fn wait_for_brain_ready() -> Result<(), String> {
    let start = std::time::Instant::now();
    
    while start.elapsed() < STARTUP_TIMEOUT {
        if check_brain_health().await {
            println!("[Sidecar] Brain health check passed");
            return Ok(());
        }
        tokio::time::sleep(STARTUP_POLL_INTERVAL).await;
    }
    
    Err("Brain failed to become ready within timeout".to_string())
}

/// Request graceful shutdown via HTTP endpoint
async fn request_graceful_shutdown() -> bool {
    let client = reqwest::Client::builder()
        .timeout(GRACEFUL_SHUTDOWN_TIMEOUT)
        .build();
    
    match client {
        Ok(client) => {
            match client.post(format!("{}/shutdown", BRAIN_URL)).send().await {
                Ok(response) => {
                    if response.status().is_success() {
                        println!("[Sidecar] Graceful shutdown acknowledged");
                        // Wait a moment for the process to exit cleanly
                        tokio::time::sleep(Duration::from_millis(500)).await;
                        true
                    } else {
                        eprintln!("[Sidecar] Shutdown endpoint returned error: {:?}", response.status());
                        false
                    }
                }
                Err(e) => {
                    eprintln!("[Sidecar] Failed to request graceful shutdown: {}", e);
                    false
                }
            }
        }
        Err(e) => {
            eprintln!("[Sidecar] Failed to create HTTP client: {}", e);
            false
        }
    }
}

/// Spawn the brain sidecar process
pub async fn spawn_brain(app: &AppHandle) -> Result<(), String> {
    if BRAIN_RUNNING.load(Ordering::SeqCst) {
        // Already running, just verify it's healthy
        if check_brain_health().await {
            return Ok(());
        }
        // Not healthy, stop and restart
        println!("[Sidecar] Brain not responding, restarting...");
        let _ = stop_brain_internal(true).await;
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
                    // Clear the process handle
                    let mut process = BRAIN_PROCESS.lock().unwrap();
                    *process = None;
                    break;
                }
                _ => {}
            }
        }
    });

    // Wait for the server to start and verify it's healthy
    wait_for_brain_ready().await?;
    
    Ok(())
}

/// Internal stop function with graceful shutdown option
async fn stop_brain_internal(graceful: bool) -> Result<String, String> {
    // Try graceful shutdown first if requested
    if graceful && BRAIN_RUNNING.load(Ordering::SeqCst) {
        if request_graceful_shutdown().await {
            // Give the process time to exit
            tokio::time::sleep(Duration::from_millis(500)).await;
            
            // Check if it's still running
            if !BRAIN_RUNNING.load(Ordering::SeqCst) {
                return Ok("Brain stopped gracefully".to_string());
            }
        }
    }
    
    // Force kill if graceful failed or wasn't requested
    let mut process = BRAIN_PROCESS.lock().unwrap();
    if let Some(child) = process.take() {
        child.kill().map_err(|e| format!("Failed to kill brain process: {}", e))?;
        BRAIN_RUNNING.store(false, Ordering::SeqCst);
        Ok("Brain stopped (forced)".to_string())
    } else {
        Ok("Brain was not running".to_string())
    }
}

#[tauri::command]
pub async fn start_brain(app: AppHandle) -> Result<String, String> {
    spawn_brain(&app).await?;
    Ok("Brain started".to_string())
}

#[tauri::command]
pub async fn stop_brain() -> Result<String, String> {
    stop_brain_internal(true).await
}

/// Synchronous version for cleanup on app exit
/// Uses blocking runtime to call async graceful shutdown
pub fn stop_brain_sync() -> Result<String, String> {
    // First try graceful shutdown via HTTP
    let graceful_result = std::thread::spawn(|| {
        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .ok()?;
        
        rt.block_on(async {
            if request_graceful_shutdown().await {
                // Wait for process to exit
                tokio::time::sleep(Duration::from_millis(500)).await;
                Some(())
            } else {
                None
            }
        })
    }).join();
    
    if let Ok(Some(())) = graceful_result {
        if !BRAIN_RUNNING.load(Ordering::SeqCst) {
            return Ok("Brain stopped gracefully".to_string());
        }
    }
    
    // Fall back to force kill
    let mut process = BRAIN_PROCESS.lock().unwrap();
    if let Some(child) = process.take() {
        child.kill().map_err(|e| format!("Failed to kill brain process: {}", e))?;
        BRAIN_RUNNING.store(false, Ordering::SeqCst);
        Ok("Brain stopped (forced)".to_string())
    } else {
        Ok("Brain was not running".to_string())
    }
}

#[tauri::command]
pub fn get_brain_status() -> bool {
    BRAIN_RUNNING.load(Ordering::SeqCst)
}

#[tauri::command]
pub async fn is_brain_ready() -> bool {
    check_brain_health().await
}

