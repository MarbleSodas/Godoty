import "./StatusPanel.css";

interface StatusPanelProps {
  status: "disconnected" | "connecting" | "connected";
}

export function StatusPanel({ status }: StatusPanelProps) {
  const getStatusIcon = () => {
    switch (status) {
      case "connected":
        return "🟢";
      case "connecting":
        return "🟡";
      case "disconnected":
        return "🔴";
    }
  };

  const getStatusText = () => {
    switch (status) {
      case "connected":
        return "Connected to Godot";
      case "connecting":
        return "Connecting...";
      case "disconnected":
        return "Disconnected";
    }
  };

  return (
    <div className={`status-panel status-${status}`}>
      <span className="status-icon">{getStatusIcon()}</span>
      <span className="status-text">{getStatusText()}</span>
    </div>
  );
}

