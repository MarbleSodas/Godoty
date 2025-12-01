import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, map, BehaviorSubject } from 'rxjs';
import { SessionService, Session, Message } from './session.service';
import { MetricsService, OpenRouterMetrics, ProjectMetrics } from './metrics.service';
import { ConfigService } from './config.service';
import { APP_CONFIG } from '../core/constants';
import { EnvironmentDetector, EnvironmentMode } from '../utils/environment';

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

export interface PlanStep extends ExecutionStep {
  progress?: number;
  startTime?: number;
  endTime?: number;
}

export interface MessageEvent {
  type: 'text' | 'tool_use' | 'tool_result' | 'plan_created' | 'execution_started' | 'metadata' | 'done' | 'error';
  timestamp: number;
  sequence: number;
  content?: string;
  toolCall?: ToolCall;
  plan?: ExecutionPlan;
  metadata?: any;
}

export interface WorkflowMetrics {
  totalTokens: number;
  totalCost: number;
  totalSteps?: number;
  completedSteps?: number;
  planningTime?: number;
  executionTime?: number;
}

export interface ApiResponse {
  status?: string;
  session?: any;
  [key: string]: any;
}

// Re-export types from other services for convenience
export type { Session, Message } from './session.service';
export type { ProjectMetrics } from './metrics.service';

@Injectable({
  providedIn: 'root'
})
export class ChatService {
  private messagesSubject = new BehaviorSubject<Message[]>([]);
  public messages$ = this.messagesSubject.asObservable();

  // Expose project metrics from MetricsService as an Observable
  public projectMetrics$: Observable<ProjectMetrics>;

  constructor(
    private http: HttpClient,
    private sessionService: SessionService,
    private metricsService: MetricsService,
    private configService: ConfigService
  ) {
    // Initialize project metrics observable
    this.projectMetrics$ = this.metricsService.projectMetrics.asObservable();
  }

  /**
   * Make backend API call using appropriate communication method
   */
  private async makeBackendCall<T>(endpoint: string, data?: any): Promise<T> {
    const environment = EnvironmentDetector.getCurrentMode();

    if (environment === EnvironmentMode.DESKTOP) {
      // Use PyWebView bridge for desktop mode
      const windowAny = window as any;

      // Remove leading slash for PyWebView API
      const apiEndpoint = endpoint.startsWith('/') ? endpoint.substring(1) : endpoint;

      if (!windowAny.pywebview?.api) {
        throw new Error('PyWebView API not available in desktop mode');
      }

      console.log(`[ChatService] Using PyWebView bridge for ${apiEndpoint}`);

      // Handle different endpoints for PyWebView
      if (apiEndpoint.startsWith('sessions/')) {
        if (apiEndpoint.includes('/chat/stream')) {
          return await windowAny.pywebview.api.sendMessageStream(data);
        } else if (apiEndpoint.includes('/title')) {
          return await windowAny.pywebview.api.updateSessionTitle(data);
        } else if (apiEndpoint.includes('/hide')) {
          return await windowAny.pywebview.api.hideSession(data);
        } else if (apiEndpoint.includes('/stop')) {
          return await windowAny.pywebview.api.stopSession(data);
        } else if (apiEndpoint.split('/').length === 2) {
          // Create session or get sessions
          return await windowAny.pywebview.api.manageSession(apiEndpoint, data);
        } else {
          throw new Error(`Unknown PyWebView session endpoint: ${apiEndpoint}`);
        }
      } else {
        throw new Error(`Unknown PyWebView endpoint: ${apiEndpoint}`);
      }
    } else {
      // Use HTTP requests for browser mode
      const url = `${APP_CONFIG.API_ENDPOINTS.CHAT}${endpoint}`;
      console.log(`[ChatService] Using HTTP for ${url}`);

      const options: RequestInit = {
        method: data ? 'POST' : 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      };

      if (data) {
        options.body = JSON.stringify(data);
      }

      const response = await fetch(url, options);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    }
  }

  /**
   * Set the current project path (delegates to SessionService)
   */
  setProjectPath(path: string): void {
    this.sessionService.setProjectPath(path);
    // Also update config service for consistency
    this.configService.setProjectPath(path);
  }

  // Session Management - Aligned with 6 Backend Endpoints

  /**
   * Create a new session
   * Endpoint: POST /api/agent/sessions
   */
  createSession(sessionId: string, title?: string): Observable<any> {
    const body: any = { session_id: sessionId };
    if (title) {
      body.title = title;
    }

    const projectPath = this.sessionService.getProjectPath();
    if (projectPath) {
      body.project_path = projectPath;
    }

    return this.http.post(`${APP_CONFIG.API_ENDPOINTS.CHAT}/sessions`, body).pipe(
      map(response => {
        // Update session service with created session
        this.sessionService.updateSessionsList([{
          id: sessionId,
          title: title || `Session ${sessionId.substring(0, 8)}`,
          date: new Date(),
          active: true,
          project_path: projectPath || undefined
        }]);
        return response;
      })
    );
  }

  /**
   * List sessions
   * Endpoint: GET /api/agent/sessions
   */
  listSessions(projectPath?: string): Observable<Session[]> {
    let url = `${APP_CONFIG.API_ENDPOINTS.CHAT}/sessions`;
    if (projectPath) {
      url += `?path=${encodeURIComponent(projectPath)}`;
    }

    return this.http.get<any>(url).pipe(
      map(response => {
        if (response.status === 'success' && response.sessions) {
          // Handle ProjectDB list format (array)
          if (Array.isArray(response.sessions)) {
            const sessions = response.sessions.map((s: any) => {
              // Handle timestamps: last_updated > created_at > Date.now()
              let timestamp = Date.now();
              if (s.last_updated) timestamp = s.last_updated * 1000;
              else if (s.created_at) timestamp = s.created_at * 1000;

              return {
                id: s.id,
                title: s.title || `Session ${s.id.substring(0, 8)}`,
                date: new Date(timestamp),
                active: s.id === this.sessionService.getCurrentSessionId(),
                metrics: s.metrics,
                project_path: projectPath
              };
            }).sort((a: any, b: any) => b.date.getTime() - a.date.getTime());

            // Update session service
            this.sessionService.updateSessionsList(sessions);
            return sessions;
          }
        }
        return [];
      })
    );
  }

  /**
   * Get session details
   * Endpoint: GET /api/agent/sessions/{session_id}
   */
  getSession(sessionId: string, projectPath?: string): Observable<ApiResponse> {
    let url = `${APP_CONFIG.API_ENDPOINTS.CHAT}/sessions/${sessionId}`;
    if (projectPath) {
      url += `?path=${encodeURIComponent(projectPath)}`;
    }

    return this.http.get<ApiResponse>(url).pipe(
      map(response => {
        // Update session service with session metadata
        if (response.status === 'success' && response.session) {
          const sessionData = response.session;
          this.sessionService.updateSessionMetadata(sessionId, {
            title: sessionData.title,
            metrics: sessionData.metrics
          });
        }
        return response;
      })
    );
  }

  /**
   * Hide session (soft delete)
   * Endpoint: POST /api/agent/sessions/{session_id}/hide
   */
  hideSession(sessionId: string): Observable<any> {
    return this.http.post(`${APP_CONFIG.API_ENDPOINTS.CHAT}/sessions/${sessionId}/hide`, {}).pipe(
      map(response => {
        // Update session service
        this.sessionService.hideSession(sessionId);
        return response;
      })
    );
  }

  /**
   * Stop running session
   * Endpoint: POST /api/agent/sessions/{session_id}/stop
   */
  stopSession(sessionId: string): Observable<any> {
    return this.http.post(`${APP_CONFIG.API_ENDPOINTS.CHAT}/sessions/${sessionId}/stop`, {});
  }

  /**
   * Stream chat with agent
   * Endpoint: POST /api/agent/sessions/{session_id}/chat/stream
   */
  async *sendMessageStream(sessionId: string, message: string, mode: 'planning' | 'fast' = 'planning', signal?: AbortSignal): AsyncGenerator<any> {
    let url = `${APP_CONFIG.API_ENDPOINTS.CHAT}/sessions/${sessionId}/chat/stream`;
    const projectPath = this.sessionService.getProjectPath();
    if (projectPath) {
        url += `?path=${encodeURIComponent(projectPath)}`;
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

              // Update metrics for this session if metadata is present
              if (parsed.type === 'metadata' || parsed.metrics) {
                this.metricsService.updateSessionCost(sessionId, parsed);
              }

              // Update tool call count for tool events
              if (parsed.type === 'tool_use') {
                this.metricsService.updateToolCallCount(sessionId);
              }

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

  // Note: Configuration methods moved to ConfigService
// Note: Direct plan generation removed - use session-based approach

  /**
   * Update session title via backend API with enhanced validation and retry logic
   */
  async updateSessionTitle(sessionId: string, title: string): Promise<void> {
    // Validate session exists before attempting update
    if (!(await this.sessionExists(sessionId))) {
      throw new Error(`Session ${sessionId} does not exist`);
    }

    const url = `${APP_CONFIG.API_ENDPOINTS.CHAT}/sessions/${sessionId}/title`;

    let retryCount = 0;
    const maxRetries = 3;

    while (retryCount <= maxRetries) {
      try {
        await this.http.post(url, { title }).toPromise();
        console.log(`[ChatService] Updated session title: ${sessionId} -> ${title}`);
        return; // Success - exit retry loop
      } catch (error: any) {
        retryCount++;

        if (error?.status === 404) {
          console.error(`[ChatService] Session not found: ${sessionId}`);
          throw new Error(`Session ${sessionId} not found. Please try refreshing.`);
        }

        if (retryCount > maxRetries) {
          console.error('[ChatService] Failed to update session title after retries:', error);
          throw error;
        }

        // Exponential backoff for retries
        await new Promise(resolve => setTimeout(resolve, 1000 * retryCount));
      }
    }
  }

  /**
   * Check if session exists in backend
   */
  private async sessionExists(sessionId: string): Promise<boolean> {
    try {
      const url = `${APP_CONFIG.API_ENDPOINTS.CHAT}/sessions/${sessionId}`;
      await this.http.get(url).toPromise();
      return true;
    } catch (error: any) {
      if (error?.status === 404) {
        return false;
      }
      // For other errors, assume session might exist to avoid false negatives
      return true;
    }
  }
}
