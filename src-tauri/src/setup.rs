use crate::config::get_config_dir;
use std::fs;
use tauri::{AppHandle, Manager};

pub fn init_config(app_handle: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let config_dir = get_config_dir(app_handle)?;

    if !config_dir.exists() {
        fs::create_dir_all(&config_dir)?;
    }

    let resources = vec!["resources/opencode.json", "resources/antigravity.json"];

    for resource_path in resources {
        let filename = std::path::Path::new(resource_path)
            .file_name()
            .ok_or("Invalid resource path")?;

        let target_path = config_dir.join(filename);

        if !target_path.exists() {
            let resource_full_path = app_handle
                .path()
                .resolve(resource_path, tauri::path::BaseDirectory::Resource)?;

            if resource_full_path.exists() {
                fs::copy(resource_full_path, target_path)?;
            }
        }
    }

    Ok(())
}
