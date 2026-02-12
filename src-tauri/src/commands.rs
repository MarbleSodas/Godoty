use crate::sidecar::SidecarManager;
use crate::updater::{Updater, Release};
use tauri::{AppHandle, Runtime};

#[derive(serde::Serialize)]
pub struct SidecarVersion {
    pub version: String,
    pub path: String,
}

#[derive(serde::Serialize)]
pub struct UpdateInfo {
    pub available: bool,
    pub latest_version: String,
    pub current_version: String,
    pub release: Option<Release>,
}

#[tauri::command]
pub fn get_sidecar_version<R: Runtime>(app: AppHandle<R>) -> Result<SidecarVersion, String> {
    let updater = Updater::new(&app);
    let path = updater.get_sidecar_path().map_err(|e| e.to_string())?;
    let version = updater.get_current_version().map_err(|e| e.to_string())?;
    Ok(SidecarVersion {
        version,
        path: path.to_string_lossy().to_string(),
    })
}

#[tauri::command]
pub async fn check_sidecar_update<R: Runtime>(app: AppHandle<R>) -> Result<UpdateInfo, String> {
    // Run blocking network call in a blocking thread to avoid blocking the async runtime
    let app_handle = app.clone();
    let result = tauri::async_runtime::spawn_blocking(move || {
        let updater = Updater::new(&app_handle);
        let current_version = updater.get_current_version().map_err(|e| e.to_string())?;
        let release = updater.get_latest_release().map_err(|e| e.to_string())?;
        Ok::<(String, Release), String>((current_version, release))
    }).await.map_err(|e| e.to_string())??;

    let (current_version, release) = result;
    
    let latest_ver_str = release.tag_name.trim_start_matches('v');
    let current_ver_str = current_version.trim_start_matches('v');
    
    let available = if let (Ok(latest), Ok(current)) = (
        semver::Version::parse(latest_ver_str),
        semver::Version::parse(current_ver_str)
    ) {
        latest > current
    } else {
        latest_ver_str != current_ver_str && latest_ver_str != "0.0.0"
    };
    
    Ok(UpdateInfo {
        available,
        latest_version: release.tag_name.clone(),
        current_version,
        release: Some(release),
    })
}

#[tauri::command]
pub async fn perform_sidecar_update<R: Runtime>(app: AppHandle<R>, release: Release) -> Result<(), String> {
    let app_handle = app.clone();
    let release_clone = release.clone();
    
    // Download and install update in background thread
    tauri::async_runtime::spawn_blocking(move || {
        let updater = Updater::new(&app_handle);
        updater.perform_update(&release_clone).map_err(|e| e.to_string())
    }).await
      .map_err(|e| e.to_string())??;
    
    // Restart sidecar on main thread (or safe context)
    SidecarManager::restart_sidecar(&app);
    Ok(())
}

#[tauri::command]
pub async fn restart_sidecar<R: Runtime>(app: AppHandle<R>) -> Result<(), String> {
    SidecarManager::restart_sidecar(&app);
    Ok(())
}
