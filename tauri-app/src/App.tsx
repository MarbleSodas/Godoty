import { useState, useEffect } from "react";
import "./App.css";
import { CommandInput } from "./components/CommandInput";
import { StatusPanel } from "./components/StatusPanel";
import { CommandHistory } from "./components/CommandHistory";
import { SettingsPanel } from "./components/SettingsPanel";
import { invoke } from "@tauri-apps/api/core";

interface Command {
  id: string;
  input: string;
  timestamp: Date;
  status: "pending" | "success" | "error";
  response?: string;
}

function App() {
  const [commands, setCommands] = useState<Command[]>([]);
  const [connectionStatus, setConnectionStatus] = useState<"disconnected" | "connecting" | "connected">("disconnected");
  const [apiKey, setApiKey] = useState<string>("");

  useEffect(() => {
    // Load API key from storage
    loadApiKey();

    // Connect to Godot
    connectToGodot();
  }, []);

  const loadApiKey = async () => {
    try {
      const key = await invoke<string>("get_api_key");
      setApiKey(key);
    } catch (error) {
      console.error("Failed to load API key:", error);
    }
  };

  const connectToGodot = async () => {
    setConnectionStatus("connecting");
    try {
      await invoke("connect_to_godot");
      setConnectionStatus("connected");
    } catch (error) {
      console.error("Failed to connect to Godot:", error);
      setConnectionStatus("disconnected");
    }
  };

  const handleCommandSubmit = async (input: string) => {
    const command: Command = {
      id: Date.now().toString(),
      input,
      timestamp: new Date(),
      status: "pending",
    };

    setCommands((prev) => [command, ...prev]);

    try {
      // Process command with AI
      const response = await invoke<string>("process_command", { input });

      setCommands((prev) =>
        prev.map((cmd) =>
          cmd.id === command.id
            ? { ...cmd, status: "success", response }
            : cmd
        )
      );
    } catch (error) {
      setCommands((prev) =>
        prev.map((cmd) =>
          cmd.id === command.id
            ? { ...cmd, status: "error", response: String(error) }
            : cmd
        )
      );
    }
  };

  const handleSaveApiKey = async (key: string) => {
    try {
      await invoke("save_api_key", { key });
      setApiKey(key);
    } catch (error) {
      console.error("Failed to save API key:", error);
    }
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>🎮 Godoty AI Assistant</h1>
        <StatusPanel status={connectionStatus} />
      </header>

      <main className="app-main">
        <div className="left-panel">
          <CommandInput onSubmit={handleCommandSubmit} disabled={connectionStatus !== "connected" || !apiKey} />
          <CommandHistory commands={commands} />
        </div>

        <div className="right-panel">
          <SettingsPanel apiKey={apiKey} onSaveApiKey={handleSaveApiKey} onReconnect={connectToGodot} />
        </div>
      </main>
    </div>
  );
}

export default App;
