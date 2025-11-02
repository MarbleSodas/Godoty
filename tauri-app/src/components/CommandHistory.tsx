import "./CommandHistory.css";

interface Command {
  id: string;
  input: string;
  timestamp: Date;
  status: "pending" | "success" | "error";
  response?: string;
}

interface CommandHistoryProps {
  commands: Command[];
}

export function CommandHistory({ commands }: CommandHistoryProps) {
  const formatTime = (date: Date) => {
    return date.toLocaleTimeString();
  };

  const getStatusIcon = (status: Command["status"]) => {
    switch (status) {
      case "success":
        return "✅";
      case "error":
        return "❌";
      case "pending":
        return "⏳";
    }
  };

  return (
    <div className="command-history-container">
      <h2>📜 Command History</h2>
      <div className="history-list">
        {commands.length === 0 ? (
          <p className="empty-message">No commands yet. Start by typing a command above!</p>
        ) : (
          commands.map((command) => (
            <div key={command.id} className={`history-item status-${command.status}`}>
              <div className="history-header">
                <span className="status-icon">{getStatusIcon(command.status)}</span>
                <span className="timestamp">{formatTime(command.timestamp)}</span>
              </div>
              <div className="command-input">{command.input}</div>
              {command.response && (
                <div className="command-response">
                  <strong>Response:</strong> {command.response}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

