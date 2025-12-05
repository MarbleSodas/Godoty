import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, map, tap, BehaviorSubject } from 'rxjs';

export interface ProjectMetrics {
  total_cost: number;
  total_tokens: number;
  total_sessions: number;
}

export interface ToolCall {
  name: string;
  input: any;
  status: 'running' | 'completed' | 'failed';
  result?: any;
  error?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  reasoning?: string;
  error?: string;
  isStreaming?: boolean;
  toolCalls?: ToolCall[];
  metrics?: {
    total_tokens: number;
    input_tokens: number;
    output_tokens: number;
    estimated_cost: number;
    model_id: string;
  };
}

export interface Session {
  id: string;
  title: string;
  date: Date;
  active: boolean;
  metrics?: {
    total_estimated_cost: number;
    total_tokens: number;
  };
}

@Injectable({
  providedIn: 'root'
})
export class ChatService {
  private apiUrl = 'http://127.0.0.1:8000/api/agent';
  private currentProjectPath: string | null = null;
  public projectMetrics$ = new BehaviorSubject<ProjectMetrics | null>(null);

  constructor(private http: HttpClient) { }

  setProjectPath(path: string) {
    this.currentProjectPath = path;
    this.loadProjectMetrics();
  }

  private loadProjectMetrics() {
    if (!this.currentProjectPath) return;
    this.http.get<any>(`${this.apiUrl}/metrics/project?path=${encodeURIComponent(this.currentProjectPath)}`)
      .subscribe(response => {
        if (response.status === 'success') {
          this.projectMetrics$.next(response.metrics);
        }
      });
  }

  // Session Management
  createSession(sessionId: string, title?: string): Observable<any> {
    const body: any = { session_id: sessionId };
    if (title) {
      body.title = title;
    }
    if (this.currentProjectPath) {
      body.project_path = this.currentProjectPath;
    }
    return this.http.post(`${this.apiUrl}/sessions`, body);
  }

  listSessions(): Observable<Session[]> {
    let url = `${this.apiUrl}/sessions`;
    if (this.currentProjectPath) {
      url += `?path=${encodeURIComponent(this.currentProjectPath)}`;
    }
    return this.http.get<any>(url).pipe(
      map(response => {
        if (response.status === 'success' && response.sessions) {
          // Handle ProjectDB list format (array)
          if (Array.isArray(response.sessions)) {
            return response.sessions.map((s: any) => {
              // Handle timestamps: last_updated > created_at > Date.now()
              let timestamp = Date.now();
              if (s.last_updated) timestamp = s.last_updated * 1000;
              else if (s.created_at) timestamp = s.created_at * 1000;

              return {
                id: s.id,
                title: s.title || `Session ${s.id.substring(0, 8)}`,
                date: new Date(timestamp),
                active: false,
                metrics: s.metrics
              };
            }).sort((a: any, b: any) => b.date.getTime() - a.date.getTime());
          }

          // Handle Legacy format (dict)
          return Object.entries(response.sessions).map(([id, data]: [string, any]) => ({
            id: id,
            title: data.metadata?.title || `Session ${id}`,
            date: new Date(data.metadata?.created_at || Date.now()),
            active: false,
            metrics: data.metrics
          })).sort((a, b) => b.date.getTime() - a.date.getTime()); // Sort by date, newest first
        }
        return [];
      })
    );
  }

  getSession(sessionId: string): Observable<any> {
    let url = `${this.apiUrl}/sessions/${sessionId}`;
    if (this.currentProjectPath) {
      url += `?path=${encodeURIComponent(this.currentProjectPath)}`;
    }
    return this.http.get(url);
  }

  getSessionStatus(sessionId: string): Observable<any> {
    const url = `${this.apiUrl}/sessions/${sessionId}/status`;
    return this.http.get(url);
  }

  deleteSession(sessionId: string): Observable<any> {
    let url = `${this.apiUrl}/sessions/${sessionId}`;
    if (this.currentProjectPath) {
      url += `?path=${encodeURIComponent(this.currentProjectPath)}`;
    }
    return this.http.delete(url);
  }

  // Chat Interaction
  sendMessage(sessionId: string, message: string, mode: 'planning' | 'fast' = 'planning'): Observable<any> {
    let url = `${this.apiUrl}/sessions/${sessionId}/chat`;
    if (this.currentProjectPath) {
      url += `?path=${encodeURIComponent(this.currentProjectPath)}`;
    }
    return this.http.post(url, { message, mode });
  }

  stopSession(sessionId: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/sessions/${sessionId}/stop`, {});
  }

  async *sendMessageStream(sessionId: string, message: string, mode: 'planning' | 'fast' = 'planning', signal?: AbortSignal): AsyncGenerator<any> {
    let url = `${this.apiUrl}/sessions/${sessionId}/chat/stream`;
    if (this.currentProjectPath) {
      url += `?path=${encodeURIComponent(this.currentProjectPath)}`;
    }
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message, mode }),
      signal
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
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmedLine = line.trim();
          if (!trimmedLine) continue;

          if (trimmedLine.startsWith('data: ')) {
            const data = trimmedLine.slice(6).trim();
            if (data === '[DONE]') continue;

            try {
              yield JSON.parse(data);
            } catch {
              yield { type: 'error', error: 'Failed to parse server response', details: data };
            }
          }
        }
      }

      // Process remaining buffer
      if (buffer.trim()) {
        const trimmedBuffer = buffer.trim();
        if (trimmedBuffer.startsWith('data: ')) {
          const data = trimmedBuffer.slice(6).trim();
          if (data && data !== '[DONE]') {
            try {
              yield JSON.parse(data);
            } catch { /* ignore parse errors in final buffer */ }
          }
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        return; // User cancelled - exit cleanly
      }
      yield { type: 'error', error: error instanceof Error ? error.message : 'Stream error occurred', details: error };
      throw error;
    } finally {
      reader.releaseLock();
    }
  }

  // Configuration
  getAgentConfig(): Observable<any> {
    return this.http.get(`${this.apiUrl}/config`);
  }

  updateAgentConfig(config: { model_id?: string; openrouter_api_key?: string }): Observable<any> {
    return this.http.post(`${this.apiUrl}/config`, config);
  }

  // Session Title Management
  updateSessionTitle(sessionId: string, title: string): Observable<any> {
    const url = `${this.apiUrl}/sessions/${sessionId}/title`;
    return this.http.put(url, { title });
  }

  // Chat Readiness Check
  checkChatReady(): Observable<{ ready: boolean, godot_connected: boolean, api_key_configured: boolean, message: string }> {
    return this.http.get<{ ready: boolean, godot_connected: boolean, api_key_configured: boolean, message: string }>(`${this.apiUrl}/chat/ready`);
  }
}
