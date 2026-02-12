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

pub fn get_sidecar_path<R: Runtime>(app_handle: &AppHandle<R>) -> Result<PathBuf, tauri::Error> {
    let config_dir = get_config_dir(app_handle)?;
    let bin_dir = config_dir.join("bin");
    // Ensure bin directory exists not here but where it is used (sidecar/updater) or lazily.
    // But strictly speaking, a "get path" shouldn't create dirs.
    // However, for convenience, we return the expected path.

    let ext = if cfg!(target_os = "windows") {
        ".exe"
    } else {
        ""
    };
    Ok(bin_dir.join(format!("opencode-cli{}", ext)))
}
