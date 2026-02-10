use crate::config::get_config_dir;
use tauri::Manager;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::{CommandEvent, CommandChild};
use std::sync::{Arc, Mutex};

pub struct SidecarState {
    pub child: Arc<Mutex<Option<CommandChild>>>,
}

impl Default for SidecarState {
    fn default() -> Self {
        Self {
            child: Arc::new(Mutex::new(None)),
        }
    }
}

pub struct SidecarManager;

impl SidecarManager {
    /// Kill any orphaned opencode-cli processes listening on the target port.
    /// This handles the case where a previous Tauri session crashed without
    /// properly shutting down the sidecar.
    fn cleanup_stale_sidecar(port: &str) {
        use std::net::TcpStream;
        use std::time::Duration;

        let addr = format!("127.0.0.1:{}", port);
        let sock_addr: std::net::SocketAddr = match addr.parse() {
            Ok(a) => a,
            Err(_) => return,
        };

        if TcpStream::connect_timeout(&sock_addr, Duration::from_millis(500)).is_err() {
            return;
        }

        println!("[Sidecar] Port {} is occupied, checking for orphaned sidecar...", port);

        #[cfg(unix)]
        {
            let output = match std::process::Command::new("lsof")
                .args(["-t", "-i", &format!(":{}", port), "-sTCP:LISTEN"])
                .output()
            {
                Ok(o) => o,
                Err(e) => {
                    eprintln!("[Sidecar] Failed to run lsof: {}", e);
                    return;
                }
            };

            let pids = String::from_utf8_lossy(&output.stdout);
            let mut killed = false;
            for pid_str in pids.trim().lines() {
                let pid = pid_str.trim();
                if pid.is_empty() {
                    continue;
                }

                // Verify this is actually an opencode process before killing
                if let Ok(ps_output) = std::process::Command::new("ps")
                    .args(["-p", pid, "-o", "comm="])
                    .output()
                {
                    let comm = String::from_utf8_lossy(&ps_output.stdout);
                    if comm.contains("opencode") {
                        println!("[Sidecar] Killing orphaned sidecar (PID {})", pid);
                        let _ = std::process::Command::new("kill").arg(pid).output();
                        killed = true;
                    } else {
                        eprintln!(
                            "[Sidecar] Port {} held by non-sidecar process '{}', skipping",
                            port,
                            comm.trim()
                        );
                    }
                }
            }

            if killed {
                // Give killed processes time to exit
                std::thread::sleep(Duration::from_millis(1000));
            }
        }

        #[cfg(windows)]
        {
            eprintln!("[Sidecar] Port {} is occupied; please close the process manually", port);
        }
    }

    pub fn start_sidecar<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
        let port = std::env::var("GODOTY_PORT").unwrap_or_else(|_| "4096".to_string());
        Self::cleanup_stale_sidecar(&port);

        let config_dir = get_config_dir(app).expect("Failed to get config dir");
        println!("[Sidecar] Starting with config dir: {:?}", config_dir);
        let opencode_config_path = config_dir.join("opencode.json");
        let godot_doc_dir = config_dir.join("godot_docs");

        let sidecar_command = app.shell()
            .sidecar("opencode-cli")
            .unwrap()
            .args(["serve", "--port", &port])
            .env("OPENCODE_CONFIG_FILE", opencode_config_path.to_string_lossy().to_string())
            .env("OPENCODE_CONFIG_DIR", config_dir.to_string_lossy().to_string())
            .env("OPENCODE_DATA_DIR", config_dir.join("data").to_string_lossy().to_string())
            .env("XDG_CONFIG_HOME", config_dir.to_string_lossy().to_string())
            .env("XDG_DATA_HOME", config_dir.join("data").to_string_lossy().to_string())
            .env("XDG_CACHE_HOME", config_dir.join("cache").to_string_lossy().to_string())
            .env("GODOT_DOC_DIR", godot_doc_dir.to_string_lossy().to_string());

        let sidecar_command = if let Ok(godot_path) = std::env::var("GODOT_PATH") {
            println!("[Sidecar] Forwarding GODOT_PATH: {}", godot_path);
            sidecar_command.env("GODOT_PATH", godot_path)
        } else {
            sidecar_command
        };

        let (mut _rx, child) = sidecar_command
            .spawn()
            .expect("Failed to spawn sidecar");

        if let Some(state) = app.try_state::<SidecarState>() {
            let mut child_lock = state.child.lock().unwrap();
            *child_lock = Some(child);
            println!("[Sidecar] Process spawned and stored in state");
        } else {
            eprintln!("[Sidecar] Failed to get SidecarState - process will be orphaned!");
        }

        tauri::async_runtime::spawn(async move {
            // read events such as stdout
            while let Some(event) = _rx.recv().await {
                match event {
                    CommandEvent::Stdout(line) => {
                        println!("[Sidecar Output]: {}", String::from_utf8_lossy(&line));
                    }
                    CommandEvent::Stderr(line) => {
                        eprintln!("[Sidecar Error]: {}", String::from_utf8_lossy(&line));
                    }
                    _ => {}
                }
            }
            println!("[Sidecar] Event loop finished");
        });
    }

    pub fn shutdown<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
        if let Some(state) = app.try_state::<SidecarState>() {
            let mut child_lock = state.child.lock().unwrap();
            if let Some(child) = child_lock.take() {
                println!("[Sidecar] Shutting down process...");
                if let Err(e) = child.kill() {
                    eprintln!("[Sidecar] Failed to kill process: {}", e);
                } else {
                    println!("[Sidecar] Process killed successfully");
                }
            }
        }
    }

    #[allow(dead_code)]
    pub fn health_check() -> bool {
        // Stub returning true
        true
    }
}
