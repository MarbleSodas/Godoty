use crate::config::get_config_dir;
use std::fs;
use std::path::Path;
use tauri::{AppHandle, Manager};

pub fn init_config(app_handle: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let config_dir = get_config_dir(app_handle)?;
    println!("[Setup] Initializing config in: {:?}", config_dir);

    if !config_dir.exists() {
        println!("[Setup] Creating config dir");
        fs::create_dir_all(&config_dir)?;
    }

    // Create required subdirectories
    let dirs = vec![
        "godot_docs",
        "godot_docs/classes",
        "data",
        "cache",
        "mcp-servers/godot/scripts",
        "mcp-servers/godot-doc",
    ];
    for dir in dirs {
        let dir_path = config_dir.join(dir);
        if !dir_path.exists() {
            println!("[Setup] Creating dir: {:?}", dir);
            fs::create_dir_all(&dir_path)?;
        }
    }

    // Copy simple resources (antigravity.json is just copied directly)
    copy_resource(
        app_handle,
        "resources/antigravity.json",
        &config_dir.join("antigravity.json"),
    )?;

    // Copy opencode.json with path templating
    copy_opencode_config(app_handle, &config_dir)?;

    // Copy MCP server bundles
    copy_resource(
        app_handle,
        "resources/mcp-servers/godot/server.js",
        &config_dir.join("mcp-servers/godot/server.js"),
    )?;
    copy_resource(
        app_handle,
        "resources/mcp-servers/godot-doc/doc-server.js",
        &config_dir.join("mcp-servers/godot-doc/doc-server.js"),
    )?;

    // Copy GDScript files
    copy_resource(
        app_handle,
        "resources/mcp-servers/godot/scripts/godot_operations.gd",
        &config_dir.join("mcp-servers/godot/scripts/godot_operations.gd"),
    )?;
    copy_resource(
        app_handle,
        "resources/mcp-servers/godot/scripts/viewport_capture.gd",
        &config_dir.join("mcp-servers/godot/scripts/viewport_capture.gd"),
    )?;

    // Copy Godot docs XML class files
    copy_godot_docs(app_handle, &config_dir)?;

    Ok(())
}

/// Copy a single resource file from the app bundle to the target path.
fn copy_resource(
    app_handle: &AppHandle,
    resource_path: &str,
    target_path: &Path,
) -> Result<(), Box<dyn std::error::Error>> {
    println!("[Setup] Copying resource: {}", resource_path);

    let resource_full_path = app_handle
        .path()
        .resolve(resource_path, tauri::path::BaseDirectory::Resource)?;

    if resource_full_path.exists() {
        // Ensure parent directory exists
        if let Some(parent) = target_path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::copy(&resource_full_path, target_path)?;
        println!("[Setup] Copied {} successfully", resource_path);
    } else {
        return Err(format!(
            "Resource not found at resolved path: {:?}",
            resource_full_path
        )
        .into());
    }

    Ok(())
}

/// Copy opencode.json and replace {{CONFIG_DIR}} placeholders with the actual config directory path.
fn copy_opencode_config(
    app_handle: &AppHandle,
    config_dir: &Path,
) -> Result<(), Box<dyn std::error::Error>> {
    let resource_path = "resources/opencode.json";
    let target_path = config_dir.join("opencode.json");

    println!("[Setup] Copying opencode.json with path templating");

    let resource_full_path = app_handle
        .path()
        .resolve(resource_path, tauri::path::BaseDirectory::Resource)?;

    if resource_full_path.exists() {
        let content = fs::read_to_string(&resource_full_path)?;
        let config_dir_str = config_dir.to_string_lossy();
        let templated = content.replace("{{CONFIG_DIR}}", &config_dir_str);
        fs::write(&target_path, templated)?;
        println!(
            "[Setup] opencode.json written with config_dir: {}",
            config_dir_str
        );
    } else {
        return Err(format!(
            "opencode.json resource not found at: {:?}",
            resource_full_path
        )
        .into());
    }

    Ok(())
}

fn copy_godot_docs(
    app_handle: &AppHandle,
    config_dir: &Path,
) -> Result<(), Box<dyn std::error::Error>> {
    let resource_file_path = app_handle.path().resolve(
        "resources/godot_docs/classes/@GlobalScope.xml",
        tauri::path::BaseDirectory::Resource,
    )?;

    let resource_dir_path = resource_file_path
        .parent()
        .ok_or("Could not find parent directory of @GlobalScope.xml")?;

    let target_dir = config_dir.join("godot_docs/classes");
    fs::create_dir_all(&target_dir)?;

    let marker = target_dir.join(".version");
    let current_version = env!("CARGO_PKG_VERSION");

    if marker.exists() {
        if let Ok(stamped) = fs::read_to_string(&marker) {
            if stamped.trim() == current_version {
                println!(
                    "[Setup] Godot docs already up-to-date (v{}), skipping copy",
                    current_version
                );
                return Ok(());
            }
        }
    }

    if resource_dir_path.exists() && resource_dir_path.is_dir() {
        let mut count = 0u32;
        for entry in fs::read_dir(&resource_dir_path)? {
            let entry = entry?;
            let path = entry.path();
            if path.extension().map_or(false, |ext| ext == "xml") {
                if let Some(filename) = path.file_name() {
                    let target = target_dir.join(filename);
                    fs::copy(&path, &target)?;
                    count += 1;
                }
            }
        }
        println!("[Setup] Copied {} Godot doc XML files", count);
        fs::write(&marker, current_version)?;
    } else {
        println!(
            "[Setup] Godot docs resource dir not found at: {:?}",
            resource_dir_path
        );
    }

    Ok(())
}
