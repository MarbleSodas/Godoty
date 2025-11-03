use std::sync::{Arc, Mutex};
use tauri::State;

mod websocket;
mod ai;
mod storage;

use websocket::WebSocketClient;
use ai::AIProcessor;
use storage::Storage;

#[derive(Default)]
struct AppState {
    ws_client: Arc<Mutex<Option<WebSocketClient>>>,
    ai_processor: Arc<Mutex<Option<AIProcessor>>>,
    storage: Arc<Mutex<Storage>>,
}

#[tauri::command]
async fn connect_to_godot(state: State<'_, AppState>) -> Result<String, String> {
    match WebSocketClient::connect("ws://127.0.0.1:9001").await {
        Ok(client) => {
            let mut ws_client = state.ws_client.lock().unwrap();
            *ws_client = Some(client);
            Ok("Connected to Godot".to_string())
        }
        Err(e) => Err(format!("Failed to connect: {}", e))
    }
}

#[tauri::command]
async fn process_command(
    input: String,
    state: State<'_, AppState>,
) -> Result<String, String> {
    // Get API key
    let api_key = {
        let storage = state.storage.lock().unwrap();
        storage.get_api_key().ok_or("API key not configured")?
    };

    // Initialize AI processor if needed and get a clone
    let processor = {
        let mut ai_processor = state.ai_processor.lock().unwrap();
        if ai_processor.is_none() {
            *ai_processor = Some(AIProcessor::new(&api_key));
        }
        ai_processor.as_ref().unwrap().clone()
    };

    // Process command with AI
    let commands = processor.process_input(&input).await
        .map_err(|e| format!("AI processing failed: {}", e))?;

    // Send commands to Godot
    let client = {
        let ws_client = state.ws_client.lock().unwrap();
        ws_client.as_ref().ok_or("Not connected to Godot")?.clone()
    };

    let mut results = Vec::new();
    for cmd in commands {
        let result = client.send_command(&cmd).await
            .map_err(|e| format!("Failed to send command: {}", e))?;
        results.push(result);
    }

    Ok(format!("Executed {} commands successfully", results.len()))
}

#[tauri::command]
fn get_api_key(state: State<'_, AppState>) -> Result<String, String> {
    let storage = state.storage.lock().unwrap();
    storage.get_api_key().ok_or("API key not configured".to_string())
}

#[tauri::command]
fn save_api_key(key: String, state: State<'_, AppState>) -> Result<(), String> {
    let mut storage = state.storage.lock().unwrap();
    storage.save_api_key(&key).map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            connect_to_godot,
            process_command,
            get_api_key,
            save_api_key
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
