use crate::config::get_config_dir;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;

pub struct SidecarManager;

impl SidecarManager {
    pub fn start_sidecar<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
        let config_dir = get_config_dir(app).expect("Failed to get config dir");
        let opencode_config_path = config_dir.join("opencode.json");

        let sidecar_command = app.shell()
            .sidecar("opencode-cli")
            .unwrap()
            .args(["serve", "--port", "4096"])
            .env("OPENCODE_CONFIG_FILE", opencode_config_path.to_string_lossy().to_string())
            .env("OPENCODE_CONFIG_DIR", config_dir.to_string_lossy().to_string())
            .env("XDG_CONFIG_HOME", config_dir.to_string_lossy().to_string());

        let (mut _rx, _child) = sidecar_command
            .spawn()
            .expect("Failed to spawn sidecar");

        tauri::async_runtime::spawn(async move {
            // read events such as stdout
            while let Some(event) = _rx.recv().await {
                if let CommandEvent::Stdout(line) = event {
                   println!("Sidecar: {:?}", String::from_utf8(line));
                }
            }
        });
    }

    #[allow(dead_code)]
    pub fn shutdown() {
        // Placeholder for shutdown logic
        println!("Sidecar shutdown placeholder");
    }

    #[allow(dead_code)]
    pub fn health_check() -> bool {
        // Stub returning true
        true
    }
}
