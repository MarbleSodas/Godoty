use anyhow::{Result, anyhow};
use serde_json::Value;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use futures_util::{SinkExt, StreamExt};
use std::sync::Arc;
use tokio::sync::Mutex;

type WsStream = tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>>;

#[derive(Clone)]
pub struct WebSocketClient {
    stream: Arc<Mutex<WsStream>>,
}

impl WebSocketClient {
    #[tracing::instrument]
    pub async fn connect(url: &str) -> Result<Self> {
        tracing::debug!("Connecting to WebSocket");
        let (ws_stream, _) = connect_async(url).await
            .map_err(|e| {
                tracing::error!(error = %e, "WebSocket connection failed");
                anyhow!("WebSocket connection failed: {}", e)
            })?;
        tracing::debug!("WebSocket connection established");

        Ok(Self {
            stream: Arc::new(Mutex::new(ws_stream)),
        })
    }

    #[tracing::instrument(skip(self, command))]
    pub async fn send_command(&self, command: &Value) -> Result<Value> {
        let mut stream = self.stream.lock().await;

        // Send command
        let cmd_str = serde_json::to_string(command)?;
        let cmd_preview: String = cmd_str.chars().take(200).collect();
        tracing::debug!(command_preview = %cmd_preview, "Sending command over WebSocket");
        let message = Message::Text(cmd_str);
        stream.send(message).await
            .map_err(|e| {
                tracing::error!(error = %e, "Failed to send message");
                anyhow!("Failed to send message: {}", e)
            })?;

        // Wait for response
        if let Some(msg) = stream.next().await {
            let msg = msg.map_err(|e| {
                tracing::error!(error = %e, "Failed to receive message");
                anyhow!("Failed to receive message: {}", e)
            })?;

            if let Message::Text(text) = msg {
                let resp_preview: String = text.chars().take(200).collect();
                tracing::debug!(response_preview = %resp_preview, "Received response from WebSocket");
                let response: Value = serde_json::from_str(&text)?;
                return Ok(response);
            }
        }

        tracing::warn!("No response received from WebSocket");
        Err(anyhow!("No response received"))
    }
}

