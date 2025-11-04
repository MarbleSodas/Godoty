export interface Command {
  id: string;
  input: string;
  timestamp: Date;
  status: 'pending' | 'success' | 'error';
  response?: string;
}

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected';

// Message Status Types
export type MessageStatus =
  | 'sending'      // User message being sent to backend
  | 'sent'         // User message successfully sent
  | 'thinking'     // AI is processing/thinking
  | 'gathering'    // AI is gathering data/context
  | 'generating'   // AI is generating response
  | 'streaming'    // AI response is streaming in
  | 'executing'    // AI is executing a command/action
  | 'complete'     // Message/response is complete
  | 'error';       // Error occurred

// Process Status for real-time updates
export interface ProcessStatus {
  status: MessageStatus;
  message?: string;
  progress?: number; // 0-100 for progress indication
  timestamp: number;
}

// Chat Session Models
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  thought_process?: ThoughtStep[];
  context_used?: ContextSnapshot;
  status?: MessageStatus; // Current status of the message
  isStreaming?: boolean; // Whether message is currently streaming
}

export interface ThoughtStep {
  step_number: number;
  description: string;
  reasoning: string;
  timestamp: number;
}

export interface ContextSnapshot {
  godot_docs_used: boolean;
  project_files_referenced: string[];
  previous_messages_count: number;
  total_context_size: number;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  created_at: number;
  updated_at: number;
  project_path?: string;
  metadata: SessionMetadata;
}

export interface SessionMetadata {
  total_commands: number;
  successful_commands: number;
  failed_commands: number;
  total_tokens_used: number;
}

