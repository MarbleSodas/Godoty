import { useState } from "react";
import "./SettingsPanel.css";

interface SettingsPanelProps {
  apiKey: string;
  onSaveApiKey: (key: string) => void;
  onReconnect: () => void;
}

export function SettingsPanel({ apiKey, onSaveApiKey, onReconnect }: SettingsPanelProps) {
  const [editingKey, setEditingKey] = useState(false);
  const [tempKey, setTempKey] = useState(apiKey);

  const handleSave = () => {
    onSaveApiKey(tempKey);
    setEditingKey(false);
  };

  const handleCancel = () => {
    setTempKey(apiKey);
    setEditingKey(false);
  };

  return (
    <div className="settings-panel-container">
      <h2>⚙️ Settings</h2>

      <div className="settings-section">
        <h3>OpenAI API Key</h3>
        {editingKey ? (
          <div className="api-key-edit">
            <input
              type="password"
              value={tempKey}
              onChange={(e) => setTempKey(e.target.value)}
              placeholder="sk-..."
              className="api-key-input"
            />
            <div className="button-group">
              <button onClick={handleSave} className="save-button">
                💾 Save
              </button>
              <button onClick={handleCancel} className="cancel-button">
                ❌ Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="api-key-display">
            <div className="api-key-status">
              {apiKey ? "✅ Configured" : "❌ Not configured"}
            </div>
            <button onClick={() => setEditingKey(true)} className="edit-button">
              ✏️ Edit
            </button>
          </div>
        )}
      </div>

      <div className="settings-section">
        <h3>Connection</h3>
        <button onClick={onReconnect} className="reconnect-button">
          🔄 Reconnect to Godot
        </button>
        <p className="info-text">
          Make sure the Godoty plugin is enabled in your Godot project and the editor is running.
        </p>
      </div>

      <div className="settings-section">
        <h3>About</h3>
        <p className="info-text">
          Godoty AI Assistant helps you build games in Godot using natural language commands.
        </p>
        <p className="info-text">
          Version: 0.1.0
        </p>
      </div>
    </div>
  );
}

