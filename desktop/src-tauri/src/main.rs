// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod sidecar;

use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_focus();
            }
        }))
        .setup(|app| {
            let handle = app.handle().clone();
            
            // Block until the sidecar is ready before showing the window
            // This ensures the backend is available before the frontend is visible
            tauri::async_runtime::block_on(async {
                if let Err(e) = sidecar::spawn_brain(&handle).await {
                    eprintln!("Failed to spawn brain sidecar: {}", e);
                } else {
                    println!("[Tauri] Brain sidecar started successfully");
                }
            });
            
            // Show the main window now that the sidecar is ready
            if let Some(window) = app.get_webview_window("main") {
                window.show().expect("Failed to show main window");
                println!("[Tauri] Main window shown");
            }
            
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            sidecar::start_brain,
            sidecar::stop_brain,
            sidecar::get_brain_status,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|_app_handle, event| {
            if let tauri::RunEvent::ExitRequested { .. } = event {
                println!("[Tauri] App exit requested, stopping brain sidecar...");
                // Stop the brain sidecar process before exiting
                if let Err(e) = sidecar::stop_brain_sync() {
                    eprintln!("[Tauri] Failed to stop brain on exit: {}", e);
                } else {
                    println!("[Tauri] Brain sidecar stopped successfully");
                }
            }
        });
}
