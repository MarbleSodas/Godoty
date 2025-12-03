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

export interface ExecutionStep {
  id: string;
  title: string;
  description?: string;
  tool_calls?: Array<{ name: string; parameters: any }>;
  depends_on?: string[];
  status: 'pending' | 'running' | 'completed' | 'failed';
}

export interface ExecutionPlan {
  title: string;
  description?: string;
  steps: ExecutionStep[];
  status: 'pending' | 'running' | 'completed' | 'failed';
}

export interface WorkflowMetrics {
  workflowId: string;
  planningTokens: number;
  executionTokens: number;
  totalTokens: number;
  planningCost: number;
  executionCost: number;
  totalCost: number;
  agentTypes: string[];
  planningMetrics: any;
  executionMetrics: any;
  startTime: string;
  completionTime: string;
}

export interface MessageEvent {
  type: 'text' | 'tool_use' | 'tool_result';
  timestamp: number;
  sequence: number;
  content?: string;
  toolCall?: ToolCall;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  reasoning?: string;
  error?: string;
  tokens?: number;
  promptTokens?: number;
  completionTokens?: number;
  cost?: number;
  modelName?: string;
  generationTimeMs?: number;
  isStreaming?: boolean;

  // Extended fields for agentic flow
  toolCalls?: ToolCall[];
  plan?: ExecutionPlan;
  events?: MessageEvent[];
  workflowMetrics?: WorkflowMetrics;
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
  
  hideSession(sessionId: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/sessions/${sessionId}/hide`, {});
  }

  restoreSession(sessionId: string): Observable<any> {
    if (!this.currentProjectPath) throw new Error("Project path not set");
    return this.http.post(`${this.apiUrl}/sessions/${sessionId}/restore?path=${encodeURIComponent(this.currentProjectPath)}`, {});
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
                error: 'Failed to parse server response',
                details: data
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
      // Check if this is an abort error (user cancelled)
      if (error instanceof Error && error.name === 'AbortError') {
        console.log('[SSE] Stream aborted by user');
        // Don't yield error event for user-initiated cancellation
        // Just exit cleanly
        return;
      }

      console.error('[SSE] Stream error:', error);
      // Yield error event for real errors
      yield {
        type: 'error',
        error: error instanceof Error ? error.message : 'Stream error occurred',
        details: error
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
}
