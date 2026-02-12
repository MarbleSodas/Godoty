mod config;
mod setup;
mod sidecar;
mod updater;
mod commands;

use tauri::Manager;

// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .setup(|app| {
            app.manage(sidecar::SidecarState::default());
            setup::init_config(app.handle())?;
            sidecar::SidecarManager::start_sidecar(app.handle());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            greet,
            commands::get_sidecar_version,
            commands::check_sidecar_update,
            commands::perform_sidecar_update,
            commands::restart_sidecar
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| match event {
            tauri::RunEvent::ExitRequested { .. } => {
                sidecar::SidecarManager::shutdown(app_handle);
            }
            _ => {}
        });
}
