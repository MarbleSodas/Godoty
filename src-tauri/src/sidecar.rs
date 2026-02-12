use crate::config::get_config_dir;
use crate::updater::Updater;
use tauri::Manager;
use std::sync::{Arc, Mutex};
use std::process::{Command, Stdio, Child};
use std::time::Duration;
use std::io::{BufRead, BufReader};
use std::thread;

pub struct SidecarState {
    pub child: Arc<Mutex<Option<Child>>>,
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
    #[allow(dead_code)]
    fn cleanup_stale_sidecar(port: &str) {
        use std::net::TcpStream;

        println!("[Sidecar] Cleaning up stale sidecar instances...");

        let current_pid = std::process::id();

        #[cfg(unix)]
        {
            if let Ok(output) = Command::new("ps")
                .args(["-A", "-o", "pid,comm"])
                .output()
            {
                let stdout = String::from_utf8_lossy(&output.stdout);
                for line in stdout.lines() {
                    let parts: Vec<&str> = line.split_whitespace().collect();
                    if parts.len() >= 2 {
                        let pid_str = parts[0];
                        let comm = parts[1..].join(" ");
                        
                        if comm.contains("opencode") {
                            if let Ok(pid) = pid_str.parse::<u32>() {
                                if pid != current_pid {
                                    println!("[Sidecar] Found stale process '{}' (PID {}), killing...", comm, pid);
                                    let _ = Command::new("kill").arg(pid.to_string()).output();
                                }
                            }
                        }
                    }
                }
                thread::sleep(Duration::from_millis(500));
            }
        }

        #[cfg(windows)]
        {
             let _ = Command::new("taskkill")
                .args(["/F", "/IM", "opencode-cli*", "/T"])
                .output();
             let _ = Command::new("taskkill")
                .args(["/F", "/IM", "opencode*", "/T"])
                .output();
             thread::sleep(Duration::from_millis(500));
        }

        let addr = format!("127.0.0.1:{}", port);
        let sock_addr: std::net::SocketAddr = match addr.parse() {
            Ok(a) => a,
            Err(_) => return,
        };

        if TcpStream::connect_timeout(&sock_addr, Duration::from_millis(500)).is_err() {
            return;
        }

        println!("[Sidecar] Port {} is still occupied, checking for orphaned sidecar...", port);

        #[cfg(unix)]
        {
            let output = match Command::new("lsof")
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

                if let Ok(ps_output) = Command::new("ps")
                    .args(["-p", pid, "-o", "comm="])
                    .output()
                {
                    let comm = String::from_utf8_lossy(&ps_output.stdout);
                    if comm.contains("opencode") {
                        println!("[Sidecar] Killing orphaned sidecar (PID {})", pid);
                        let _ = Command::new("kill").arg(pid).output();
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
                thread::sleep(Duration::from_millis(1000));
            }
        }

        #[cfg(windows)]
        {
            eprintln!("[Sidecar] Port {} is occupied; please close the process manually", port);
        }
    }

    fn is_sidecar_running(port: &str) -> bool {
        use std::io::{Read, Write};
        use std::net::TcpStream;

        let addr = format!("127.0.0.1:{}", port);
        let sock_addr: std::net::SocketAddr = match addr.parse() {
            Ok(a) => a,
            Err(_) => return false,
        };

        if let Ok(mut stream) = TcpStream::connect_timeout(&sock_addr, Duration::from_millis(100)) {
            stream.set_read_timeout(Some(Duration::from_millis(500))).ok();
            stream.set_write_timeout(Some(Duration::from_millis(500))).ok();

            let request = format!(
                "GET /health HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nConnection: close\r\n\r\n",
                port
            );

            if stream.write_all(request.as_bytes()).is_ok() {
                let mut buf = [0u8; 1024];
                if let Ok(n) = stream.read(&mut buf) {
                    if n > 0 {
                        let response = String::from_utf8_lossy(&buf[..n]);
                        if response.contains("HTTP/1.1 200") || response.contains("HTTP/1.0 200") {
                            return true;
                        }
                    }
                }
            }
        }
        false
    }

    pub fn start_sidecar<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
        let port = std::env::var("GODOTY_PORT").unwrap_or_else(|_| "4096".to_string());

        if Self::is_sidecar_running(&port) {
            println!("[Sidecar] Found existing healthy instance on port {}, reusing it.", port);
            
            let port_clone = port.clone();
            let app_clone = app.clone();
            tauri::async_runtime::spawn(async move {
                Self::wait_for_healthy(&port_clone);
                if let Some(main_window) = app_clone.get_webview_window("main") {
                    println!("[Sidecar] Showing main window");
                    let _ = main_window.show();
                }
            });
            return;
        }
        
        #[cfg(not(debug_assertions))]
        Self::cleanup_stale_sidecar(&port);

        let config_dir = get_config_dir(app).expect("Failed to get config dir");
        println!("[Sidecar] Starting with config dir: {:?}", config_dir);
        let opencode_config_path = config_dir.join("opencode.json");
        let godot_doc_dir = config_dir.join("godot_docs");

        let updater = Updater::new(app);
        let sidecar_path = match updater.ensure_installed() {
            Ok(path) => path,
            Err(e) => {
                eprintln!("[Sidecar] Failed to ensure sidecar installation: {}", e);
                return;
            }
        };

        println!("[Sidecar] Spawning sidecar from {:?}", sidecar_path);

        let mut command = Command::new(sidecar_path);
        command
            .args(["serve", "--port", &port])
            .env("OPENCODE_CONFIG_FILE", opencode_config_path.to_string_lossy().to_string())
            .env("OPENCODE_CONFIG_DIR", config_dir.to_string_lossy().to_string())
            .env("OPENCODE_DATA_DIR", config_dir.join("data").to_string_lossy().to_string())
            .env("XDG_CONFIG_HOME", config_dir.to_string_lossy().to_string())
            .env("XDG_DATA_HOME", config_dir.join("data").to_string_lossy().to_string())
            .env("XDG_CACHE_HOME", config_dir.join("cache").to_string_lossy().to_string())
            .env("GODOT_DOC_DIR", godot_doc_dir.to_string_lossy().to_string())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        if let Ok(godot_path) = std::env::var("GODOT_PATH") {
            println!("[Sidecar] Forwarding GODOT_PATH: {}", godot_path);
            command.env("GODOT_PATH", godot_path);
        }

        match command.spawn() {
            Ok(mut child) => {
                let stdout = child.stdout.take();
                let stderr = child.stderr.take();

                if let Some(stdout) = stdout {
                    thread::spawn(move || {
                        let reader = BufReader::new(stdout);
                        for line in reader.lines() {
                            if let Ok(l) = line {
                                println!("[Sidecar Output]: {}", l);
                            }
                        }
                    });
                }

                if let Some(stderr) = stderr {
                    thread::spawn(move || {
                        let reader = BufReader::new(stderr);
                        for line in reader.lines() {
                            if let Ok(l) = line {
                                eprintln!("[Sidecar Error]: {}", l);
                            }
                        }
                    });
                }

                if let Some(state) = app.try_state::<SidecarState>() {
                    let mut child_lock = state.child.lock().unwrap();
                    *child_lock = Some(child);
                    println!("[Sidecar] Process spawned and stored in state");
                } else {
                    eprintln!("[Sidecar] Failed to get SidecarState - process will be orphaned!");
                }
            }
            Err(e) => {
                eprintln!("[Sidecar] Failed to spawn sidecar: {}", e);
                return;
            }
        }

        let port_clone = port.clone();
        let app_clone = app.clone();
        tauri::async_runtime::spawn(async move {
            Self::wait_for_healthy(&port_clone);
            if let Some(main_window) = app_clone.get_webview_window("main") {
                println!("[Sidecar] Showing main window");
                let _ = main_window.show();
            }
        });
    }

    fn wait_for_healthy(port: &str) {
        let mut attempts = 0;
        loop {
            if Self::is_sidecar_running(port) {
                println!("[Sidecar] Health check passed on port {}", port);
                break;
            }
            attempts += 1;
            if attempts > 30 {
                eprintln!("[Sidecar] Timed out waiting for sidecar health check");
                break;
            }
            thread::sleep(Duration::from_millis(500));
        }
    }

    pub fn shutdown<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
        if let Some(state) = app.try_state::<SidecarState>() {
            let mut child_lock = state.child.lock().unwrap();
            if let Some(mut child) = child_lock.take() {
                println!("[Sidecar] Shutting down process...");
                let _ = child.kill();
            }
        }
    }

    pub fn restart_sidecar<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
        println!("[Sidecar] Restarting...");
        Self::shutdown(app);
        thread::sleep(Duration::from_millis(500));
        Self::start_sidecar(app);
    }
}
