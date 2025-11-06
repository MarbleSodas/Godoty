export type LogLevel = 'debug' | 'info' | 'warning' | 'error';
export type LogCategory = 'agent_activity' | 'information_flow' | 'action';

export interface ProcessLogEntry {
  id: string;
  timestamp: number; // epoch millis
  level: LogLevel;
  category: LogCategory;
  message: string; // Plain-language summary
  agent?: string; // Agent name/identifier
  task?: string; // Current task/action being performed
  status?: 'idle' | 'processing' | 'waiting' | 'completed' | 'error';
  sessionId?: string; // Optional association to a chat session
  data?: any; // Optional structured details (input/output, tool results, etc.)
}

export interface ProcessLogGroup {
  title: string;
  entries: ProcessLogEntry[];
}

