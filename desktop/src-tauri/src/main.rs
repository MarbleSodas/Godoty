// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod sidecar;

use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // Spawn the Python sidecar on startup
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                if let Err(e) = sidecar::spawn_brain(&handle).await {
                    eprintln!("Failed to spawn brain sidecar: {}", e);
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            sidecar::start_brain,
            sidecar::stop_brain,
            sidecar::get_brain_status,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
