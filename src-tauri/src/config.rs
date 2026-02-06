use std::path::PathBuf;
use tauri::{path::BaseDirectory, AppHandle, Manager};

/// Returns the path to the Godoty configuration directory: ~/.config/godoty/
pub fn get_config_dir(app_handle: &AppHandle) -> Result<PathBuf, tauri::Error> {
    app_handle.path().resolve("godoty", BaseDirectory::Config)
}
