use std::path::PathBuf;
use tauri::{path::BaseDirectory, AppHandle, Manager, Runtime};

/// Returns the path to the Godoty configuration directory.
/// Checks for a "data" directory next to the executable first (Portable Mode).
/// Fallback: ~/.config/godoty/
pub fn get_config_dir<R: Runtime>(app_handle: &AppHandle<R>) -> Result<PathBuf, tauri::Error> {
    if let Ok(path) = std::env::var("GODOTY_CONFIG_DIR") {
        return Ok(PathBuf::from(path));
    }

    if let Ok(mut exe_path) = std::env::current_exe() {
        exe_path.pop();
        let data_dir = exe_path.join("data");
        if data_dir.exists() && data_dir.is_dir() {
            return Ok(data_dir);
        }
    }

    app_handle.path().resolve("godoty", BaseDirectory::Config)
}
