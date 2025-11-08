// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tracing_subscriber::{fmt, EnvFilter};

fn main() {
    // Initialize tracing with RUST_LOG support; default to 'info' if not set
    let env_filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));

    fmt()
        .with_env_filter(env_filter)
        .with_target(true)
        .with_level(true)
        .compact()
        .init();

    tauri_app_lib::run()
}
