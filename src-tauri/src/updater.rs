use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use tauri::{AppHandle, Manager, Runtime};
use zip::ZipArchive;

#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct Asset {
    pub name: String,
    pub browser_download_url: String,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct Release {
    pub tag_name: String,
    pub assets: Vec<Asset>,
    pub body: Option<String>,
    pub published_at: Option<String>,
}

#[derive(Clone)]
pub struct Updater<R: Runtime> {
    client: Client,
    app_handle: AppHandle<R>,
}

impl<R: Runtime> Updater<R> {
    pub fn new(app: &AppHandle<R>) -> Self {
        Self {
            client: Client::builder()
                .user_agent("godoty-updater")
                .timeout(std::time::Duration::from_secs(30))
                .build()
                .unwrap(),
            app_handle: app.clone(),
        }
    }

    pub fn get_sidecar_path(&self) -> Result<PathBuf, Box<dyn std::error::Error + Send + Sync>> {
        let path = crate::config::get_sidecar_path(&self.app_handle)
            .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;
        if let Some(parent) = path.parent() {
            if !parent.exists() {
                fs::create_dir_all(parent)
                    .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;
            }
        }
        Ok(path)
    }

    pub fn ensure_installed(&self) -> Result<PathBuf, Box<dyn std::error::Error + Send + Sync>> {
        let install_path = self.get_sidecar_path()?;

        if install_path.exists() {
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                if let Ok(metadata) = fs::metadata(&install_path) {
                    let mut perms = metadata.permissions();
                    if perms.mode() & 0o111 == 0 {
                        perms.set_mode(0o755);
                        let _ = fs::set_permissions(&install_path, perms);
                    }
                }
            }
            return Ok(install_path);
        }

        println!(
            "[Updater] Sidecar not found at {:?}, installing from bundle...",
            install_path
        );

        let bundled_path = self
            .find_bundled_binary()
            .map_err(|e| Box::<dyn std::error::Error + Send + Sync>::from(e))?;
        println!("[Updater] Found bundled binary at {:?}", bundled_path);

        if let Some(parent) = install_path.parent() {
            fs::create_dir_all(parent)
                .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;
        }

        fs::copy(&bundled_path, &install_path)
            .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;
        println!("[Updater] Copied to {:?}", install_path);

        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&install_path, fs::Permissions::from_mode(0o755))
                .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;
        }

        Ok(install_path)
    }

    fn find_bundled_binary(&self) -> Result<PathBuf, String> {
        // In development, it might be in `src-tauri/bin` or just `bin` relative to CWD
        // In production, it's in the resource directory.

        // Try resource directory first (Production)
        if let Ok(resource_dir) = self.app_handle.path().resource_dir() {
            if let Ok(entries) = fs::read_dir(&resource_dir) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
                        // Tauri bundles binaries with target triple suffix, e.g., "opencode-cli-x86_64-apple-darwin"
                        if name.starts_with("opencode-cli")
                            && !name.ends_with(".old")
                            && !path.is_dir()
                        {
                            return Ok(path);
                        }
                    }
                }
            }
        }

        // Try local bin directory (Development)
        // Check current working directory + /bin
        // Check src-tauri/bin if we are in project root (less likely at runtime)
        let possible_paths = vec![
            PathBuf::from("bin/opencode-cli"),
            PathBuf::from("bin/opencode-cli.exe"),
            PathBuf::from("src-tauri/bin/opencode-cli"),
            PathBuf::from("src-tauri/bin/opencode-cli.exe"),
            // Check target/release/opencode-cli if running from cargo run
            PathBuf::from("target/release/opencode-cli"),
            PathBuf::from("target/debug/opencode-cli"),
        ];

        for path in possible_paths {
            if let Ok(abs_path) = fs::canonicalize(&path) {
                if abs_path.exists() {
                    return Ok(abs_path);
                }
            } else if path.exists() {
                return Ok(path);
            }
        }

        Err("Could not find bundled opencode-cli binary in resources or local bin folder".into())
    }

    pub fn get_latest_release(&self) -> Result<Release, Box<dyn std::error::Error + Send + Sync>> {
        let url = "https://api.github.com/repos/anomalyco/opencode/releases/latest";
        let resp = self
            .client
            .get(url)
            .send()
            .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;
        if !resp.status().is_success() {
            return Err(Box::<dyn std::error::Error + Send + Sync>::from(format!(
                "Failed to fetch release: {}",
                resp.status()
            )));
        }
        let release: Release = resp
            .json()
            .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;
        Ok(release)
    }

    pub fn get_current_version(&self) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let bin_path = self.get_sidecar_path()?;

        if !bin_path.exists() {
            return Ok("0.0.0".to_string());
        }

        // Run `opencode-cli --version`
        // Expected output: "opencode-cli 0.1.0" or just "0.1.0"
        let output = std::process::Command::new(&bin_path)
            .arg("--version")
            .output()
            .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;

        if !output.status.success() {
            return Ok("0.0.0".to_string());
        }

        let version_str = String::from_utf8_lossy(&output.stdout).trim().to_string();
        // Parse "opencode 0.1.2" -> "0.1.2"
        if let Some(last) = version_str.split_whitespace().last() {
            // simplistic check if it looks like a version
            if last.contains('.') {
                return Ok(last.to_string());
            }
        }

        Ok(version_str)
    }

    fn get_target_asset_name(&self) -> String {
        #[cfg(all(target_os = "macos", target_arch = "aarch64"))]
        return "aarch64-apple-darwin".to_string();

        #[cfg(all(target_os = "macos", target_arch = "x86_64"))]
        return "x86_64-apple-darwin".to_string();

        #[cfg(target_os = "windows")]
        return "x86_64-pc-windows-msvc".to_string();

        #[cfg(target_os = "linux")]
        return "x86_64-unknown-linux-gnu".to_string();
    }

    pub fn perform_update(
        &self,
        release: &Release,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let target = self.get_target_asset_name();
        // Find asset that contains the target string
        let asset = release
            .assets
            .iter()
            .find(|a| a.name.contains(&target))
            .ok_or_else(|| {
                Box::<dyn std::error::Error + Send + Sync>::from(format!(
                    "No matching asset found for target: {}",
                    target
                ))
            })?;

        println!("[Updater] Downloading {}...", asset.name);

        let resp = self
            .client
            .get(&asset.browser_download_url)
            .send()
            .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;
        if !resp.status().is_success() {
            return Err(Box::<dyn std::error::Error + Send + Sync>::from(format!(
                "Failed to download asset: {}",
                resp.status()
            )));
        }
        let bytes = resp
            .bytes()
            .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;

        // Use a temp directory
        let temp_dir = std::env::temp_dir().join("godoty-update");
        if !temp_dir.exists() {
            fs::create_dir_all(&temp_dir)
                .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;
        }

        let archive_path = temp_dir.join(&asset.name);
        fs::write(&archive_path, &bytes)
            .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;

        // Prepare destination
        let bin_path = self.get_sidecar_path()?;

        // KILL existing process if running
        #[cfg(target_os = "windows")]
        {
            let _ = std::process::Command::new("taskkill")
                .args(["/F", "/IM", "opencode-cli.exe", "/T"])
                .output();
            std::thread::sleep(std::time::Duration::from_millis(500));
        }
        #[cfg(unix)]
        {
            let _ = std::process::Command::new("pkill")
                .args(["-f", "opencode-cli"])
                .output();
            std::thread::sleep(std::time::Duration::from_millis(500));
        }

        // Move old binary to .old (backup/cleanup)
        if bin_path.exists() {
            let old_path = bin_path.with_extension("old");
            if old_path.exists() {
                let _ = fs::remove_file(&old_path);
            }
            // On Windows, rename might fail if still locked.
            if let Err(e) = fs::rename(&bin_path, &old_path) {
                eprintln!("[Updater] Warning: Could not rename current binary: {}", e);
                // Try to remove it directly
                if let Err(e) = fs::remove_file(&bin_path) {
                    return Err(Box::<dyn std::error::Error + Send + Sync>::from(format!(
                        "Could not remove current binary: {}",
                        e
                    )));
                }
            }
        }

        // Extract
        let mut extracted = false;
        if asset.name.ends_with(".zip") {
            let file = fs::File::open(&archive_path)
                .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;
            let mut archive = ZipArchive::new(file)
                .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;

            for i in 0..archive.len() {
                let mut file = archive
                    .by_index(i)
                    .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;
                let name = file.name().to_string();
                // We look for the executable inside the zip
                // It might be nested or named differently, but usually contains "opencode"
                if name.contains("opencode") && !name.ends_with("/") {
                    let mut out = fs::File::create(&bin_path)
                        .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;
                    std::io::copy(&mut file, &mut out)
                        .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;
                    extracted = true;
                    break;
                }
            }
        } else {
            // Treat as binary
            fs::copy(&archive_path, &bin_path)
                .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;
            extracted = true;
        }

        if extracted {
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                fs::set_permissions(&bin_path, fs::Permissions::from_mode(0o755))
                    .map_err(|e| Box::new(e) as Box<dyn std::error::Error + Send + Sync>)?;
            }
            println!("[Updater] Update installed to {:?}", bin_path);
        } else {
            return Err(Box::<dyn std::error::Error + Send + Sync>::from(
                "Could not extract executable from update archive",
            ));
        }

        Ok(())
    }
}
