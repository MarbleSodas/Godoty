import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, map, tap } from 'rxjs';

export interface ToolCall {
  name: string;
  input: any;
  status: 'running' | 'completed' | 'failed';
  result?: any;
  error?: string;
}

export interface ExecutionStep {
  id: string;
  title: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
}

export interface ExecutionPlan {
  title: string;
  steps: ExecutionStep[];
  status: 'pending' | 'running' | 'completed' | 'failed';
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  tokens?: number;
  cost?: number;
  isStreaming?: boolean;

  // Extended fields for agentic flow
  toolCalls?: ToolCall[];
  plan?: ExecutionPlan;
}

export interface Session {
  id: string;
  title: string;
  date: Date;
  active: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class ChatService {
  private apiUrl = 'http://127.0.0.1:8000/api/agent';

  constructor(private http: HttpClient) { }

  // Session Management
  createSession(sessionId: string, title?: string): Observable<any> {
    const body: any = { session_id: sessionId };
    if (title) {
      body.title = title;
    }
    return this.http.post(`${this.apiUrl}/sessions`, body);
  }

  listSessions(): Observable<Session[]> {
    return this.http.get<any>(`${this.apiUrl}/sessions`).pipe(
      map(response => {
        if (response.status === 'success' && response.sessions) {
          // Backend returns a dictionary of sessions
          return Object.entries(response.sessions).map(([id, data]: [string, any]) => ({
            id: id,
            title: data.metadata?.title || `Session ${id}`,
            date: new Date(data.metadata?.created_at || Date.now()),
            active: false
          })).sort((a, b) => b.date.getTime() - a.date.getTime()); // Sort by date, newest first
        }
        return [];
      })
    );
  }

  getSession(sessionId: string): Observable<any> {
    return this.http.get(`${this.apiUrl}/sessions/${sessionId}`);
  }

  deleteSession(sessionId: string): Observable<any> {
    return this.http.delete(`${this.apiUrl}/sessions/${sessionId}`);
  }

  // Chat Interaction
  sendMessage(sessionId: string, message: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/sessions/${sessionId}/chat`, { message });
  }

  async *sendMessageStream(sessionId: string, message: string): AsyncGenerator<any> {
    const response = await fetch(`${this.apiUrl}/sessions/${sessionId}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }

    if (!response.body) {
      throw new Error('Response body is null');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          console.log('[SSE] Stream complete');
          break;
        }

        buffer += decoder.decode(value, { stream: true });

        // Process complete lines (split by \n)
        const lines = buffer.split('\n');

        // Keep the last incomplete line in buffer
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmedLine = line.trim();

          // Skip empty lines
          if (!trimmedLine) {
            continue;
          }

          console.log('[SSE] Raw line:', trimmedLine);

          // Process SSE data lines
          if (trimmedLine.startsWith('data: ')) {
            const data = trimmedLine.slice(6).trim();

            // Skip DONE signal
            if (data === '[DONE]') {
              console.log('[SSE] Received DONE signal');
              continue;
            }

            // Parse and yield JSON data
            try {
              const parsed = JSON.parse(data);
              console.log('[SSE] Parsed event:', parsed);

              // Yield the parsed event
              yield parsed;
            } catch (e) {
              console.error('[SSE] Error parsing JSON:', e, 'Data:', data);
              // Yield error event so UI can show something went wrong
              yield {
                type: 'error',
                data: {
                  message: 'Failed to parse server response',
                  raw: data
                }
              };
            }
          }
          // Log event type lines (for debugging)
          else if (trimmedLine.startsWith('event: ')) {
            const eventType = trimmedLine.slice(7).trim();
            console.log('[SSE] Event type:', eventType);
          }
          // Log unexpected lines
          else {
            console.warn('[SSE] Unexpected line format:', trimmedLine);
          }
        }
      }

      // Process any remaining buffer content
      if (buffer.trim()) {
        console.log('[SSE] Processing final buffer:', buffer);
        const trimmedBuffer = buffer.trim();
        if (trimmedBuffer.startsWith('data: ')) {
          const data = trimmedBuffer.slice(6).trim();
          if (data && data !== '[DONE]') {
            try {
              const parsed = JSON.parse(data);
              console.log('[SSE] Parsed final event:', parsed);
              yield parsed;
            } catch (e) {
              console.error('[SSE] Error parsing final buffer:', e, 'Data:', data);
            }
          }
        }
      }
    } catch (error) {
      console.error('[SSE] Stream error:', error);
      // Yield error event
      yield {
        type: 'error',
        data: {
          message: error instanceof Error ? error.message : 'Stream error occurred',
          error: error
        }
      };
      throw error;
    } finally {
      reader.releaseLock();
    }
  }

  // Plan Generation (Direct Agent)
  createPlan(prompt: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/plan`, { prompt });
  }
}
