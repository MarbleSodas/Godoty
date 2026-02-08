use std::path::PathBuf;
use tauri::{path::BaseDirectory, AppHandle, Manager, Runtime};

/// Returns the path to the Godoty configuration directory: ~/.config/godoty/
pub fn get_config_dir<R: Runtime>(app_handle: &AppHandle<R>) -> Result<PathBuf, tauri::Error> {
    app_handle.path().resolve("godoty", BaseDirectory::Config)
}
