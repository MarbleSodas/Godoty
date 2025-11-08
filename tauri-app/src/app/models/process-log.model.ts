export type LogLevel = 'debug' | 'info' | 'warning' | 'error';
export type LogCategory = 'agent_activity' | 'information_flow' | 'action' | 'message_update' | 'chat_event' | 'tool_call';

export interface ProcessLogEntry {
  id: string;
  timestamp: number; // epoch millis
  level: LogLevel;
  category: LogCategory;
  message: string; // Plain-language summary
  agent?: string; // Agent name/identifier
  task?: string; // Current task/action being performed
  actionType?: string; // e.g., "File Read", "API Call", "Message Update"
  status?: 'idle' | 'processing' | 'waiting' | 'completed' | 'error' | 'started';
  sessionId?: string; // Optional association to a chat session
  details?: any; // Structured details for display
  data?: any; // Optional structured details (legacy/back-compat)
}

export interface ProcessLogGroup {
  title: string;
  entries: ProcessLogEntry[];
}

