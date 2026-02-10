use crate::config::get_config_dir;
use std::fs;
use tauri::{AppHandle, Manager};

pub fn init_config(app_handle: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let config_dir = get_config_dir(app_handle)?;
    println!("[Setup] Initializing config in: {:?}", config_dir);

    if !config_dir.exists() {
        println!("[Setup] Creating config dir");
        fs::create_dir_all(&config_dir)?;
    }

    let dirs = vec!["godot_docs", "data", "cache"];
    for dir in dirs {
        let dir_path = config_dir.join(dir);
        if !dir_path.exists() {
            println!("[Setup] Creating dir: {:?}", dir);
            fs::create_dir_all(&dir_path)?;
        }
    }

    let resources = vec!["resources/opencode.json", "resources/antigravity.json"];

    for resource_path in resources {
        let filename = std::path::Path::new(resource_path)
            .file_name()
            .ok_or("Invalid resource path")?;

        let target_path = config_dir.join(filename);

        println!("[Setup] Copying resource: {:?}", filename);
        let resource_full_path = app_handle
            .path()
            .resolve(resource_path, tauri::path::BaseDirectory::Resource)?;

        println!("[Setup] Resolved resource path: {:?}", resource_full_path);

        if resource_full_path.exists() {
            // We force overwrite to ensure the isolated environment is always up to date
            fs::copy(resource_full_path, target_path)?;
            println!("[Setup] Copied successfully");
        } else {
            println!("[Setup] Resource not found at resolved path!");
        }
    }

    Ok(())
}
