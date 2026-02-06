use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;

pub struct SidecarManager;

impl SidecarManager {
    pub fn start_sidecar<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
        let sidecar_command = app.shell().sidecar("opencode-cli").unwrap();
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

    pub fn shutdown() {
        // Placeholder for shutdown logic
        println!("Sidecar shutdown placeholder");
    }

    pub fn health_check() -> bool {
        // Stub returning true
        true
    }
}
