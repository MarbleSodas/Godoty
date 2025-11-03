export interface Command {
  id: string;
  input: string;
  timestamp: Date;
  status: 'pending' | 'success' | 'error';
  response?: string;
}

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected';

