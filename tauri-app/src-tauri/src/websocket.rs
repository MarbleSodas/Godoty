use anyhow::{Result, anyhow};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use futures_util::{SinkExt, StreamExt};
use std::sync::Arc;
use tokio::sync::Mutex;

type WsStream = tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>>;

pub struct WebSocketClient {
    stream: Arc<Mutex<WsStream>>,
}

impl WebSocketClient {
    pub async fn connect(url: &str) -> Result<Self> {
        let (ws_stream, _) = connect_async(url).await
            .map_err(|e| anyhow!("WebSocket connection failed: {}", e))?;
        
        Ok(Self {
            stream: Arc::new(Mutex::new(ws_stream)),
        })
    }
    
    pub async fn send_command(&self, command: &Value) -> Result<Value> {
        let mut stream = self.stream.lock().await;
        
        // Send command
        let message = Message::Text(serde_json::to_string(command)?);
        stream.send(message).await
            .map_err(|e| anyhow!("Failed to send message: {}", e))?;
        
        // Wait for response
        if let Some(msg) = stream.next().await {
            let msg = msg.map_err(|e| anyhow!("Failed to receive message: {}", e))?;
            
            if let Message::Text(text) = msg {
                let response: Value = serde_json::from_str(&text)?;
                return Ok(response);
            }
        }
        
        Err(anyhow!("No response received"))
    }
}

