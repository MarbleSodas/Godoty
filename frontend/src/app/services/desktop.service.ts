import { Injectable } from '@angular/core';
import { from, Observable, Subject } from 'rxjs';
import { map } from 'rxjs/operators';
import { HttpClient } from '@angular/common/http';
import { APP_CONFIG } from '../core/constants';

declare global {
  interface Window {
    pywebview: {
      api: {
        [key: string]: (...args: any[]) => Promise<any>;
      };
    };
  }
}

export interface GodotStatus {
  state: string;
  timestamp?: string;
  error?: string;
  project_path?: string;
  project_name?: string;
  godot_version?: string;
  plugin_version?: string;
  project_settings?: {
    name?: string;
    main_scene?: string;
    viewport_width?: number;
    viewport_height?: number;
    renderer?: string;
  };
}

export interface DetailedConnectionStatus {
  monitor: {
    running: boolean;
    state: string;
    last_attempt?: string;
    current_backoff?: number;
    project_path?: string;
    godot_version?: string;
    plugin_version?: string;
    project_settings?: any;
    error?: string;
  };
  agent: {
    connected: boolean;
    state: string;
    project_info?: {
      project_path?: string;
      godot_version?: string;
      plugin_version?: string;
      connected_at?: string;
    };
    has_bridge: boolean;
    bridge_project_info?: {
      project_path?: string;
      project_name?: string;
      godot_version?: string;
      plugin_version?: string;
      is_ready?: boolean;
    };
  };
  timestamp: string;
  integration_available: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class DesktopService {
  private isReady = false;
  private eventSource?: EventSource;
  private godotStatusSubject = new Subject<GodotStatus>();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 1000; // Start with 1 second

  constructor(private http: HttpClient) {
    window.addEventListener('pywebviewready', () => {
      this.isReady = true;
      console.log('PyWebView ready!');
    });
  }

  /**
   * Call a Python method exposed via pywebview API
   * @param method The name of the Python method to call
   * @param args Arguments to pass to the Python method
   * @returns Observable that emits the result from Python
   */
  callPythonMethod(method: string, ...args: any[]): Observable<any> {
    if (!this.isReady) {
      return new Observable(observer => {
        observer.error('PyWebView not ready');
      });
    }

    return from(window.pywebview.api[method](...args));
  }

  /**
   * Get system information from Python
   */
  getSystemInfo(): Observable<any> {
    return this.callPythonMethod('get_system_info');
  }

  /**
   * Get Godot connection status and project info (one-time HTTP request)
   */
  getGodotStatus(): Observable<GodotStatus> {
    return this.http.get<GodotStatus>(`${APP_CONFIG.API_ENDPOINTS.STATUS}`);
  }

  /**
   * Get detailed connection status from both monitor and agent
   */
  getDetailedConnectionStatus(): Observable<DetailedConnectionStatus> {
    return this.http.get<DetailedConnectionStatus>(`${APP_CONFIG.API_ENDPOINTS.CONNECTION_STATUS}`);
  }

  /**
   * Get enhanced health check with connection information
   */
  getHealthStatus(): Observable<any> {
    return this.http.get<any>(`${APP_CONFIG.API_ENDPOINTS.HEALTH}`);
  }

  /**
   * Start polling for connection status updates
   * @param intervalMs Polling interval in milliseconds (default: 5000)
   * @returns Observable that emits connection status updates
   */
  pollConnectionStatus(intervalMs: number = 5000): Observable<DetailedConnectionStatus> {
    return new Observable<DetailedConnectionStatus>(observer => {
      console.log(`[DesktopService] Starting connection status polling every ${intervalMs}ms`);

      const poll = () => {
        this.getDetailedConnectionStatus().subscribe({
          next: (status) => {
            console.log('[DesktopService] Connection status update:', status);
            observer.next(status);
          },
          error: (error) => {
            console.error('[DesktopService] Error polling connection status:', error);
            // Don't emit error state for polling errors - just log and continue
            // Only emit actual status information
            observer.next({
              monitor: { running: false, state: 'disconnected', error: undefined },
              agent: { connected: false, state: 'DISCONNECTED', has_bridge: false },
              timestamp: new Date().toISOString(),
              integration_available: false,
              godot_tools_available: false,
              mcp_tools_available: false
            } as DetailedConnectionStatus);
          }
        });
      };

      // Initial poll
      poll();

      // Set up recurring polling
      const interval = setInterval(poll, intervalMs);

      // Cleanup on unsubscribe
      return () => {
        clearInterval(interval);
        console.log('[DesktopService] Stopped connection status polling');
      };
    });
  }

  /**
   * Check if Godot integration is fully available
   * @returns Observable<boolean> that emits true when integration is ready
   */
  isGodotIntegrationReady(): Observable<boolean> {
    return this.pollConnectionStatus(2000).pipe(
      // Map to boolean based on integration availability
      map((status: DetailedConnectionStatus) => status.integration_available)
    );
  }

  /**
   * Save a file using Python backend
   */
  saveFile(data: any): Observable<any> {
    return this.callPythonMethod('save_file', data);
  }

  /**
   * Check if pywebview is ready
   */
  get ready(): boolean {
    return this.isReady;
  }

  /**
   * Connect to the Godot status SSE stream for real-time updates
   * @returns Observable that emits Godot status updates
   */
  streamGodotStatus(): Observable<GodotStatus> {
    if (!this.eventSource) {
      this.connectToSSE();
    }
    return this.godotStatusSubject.asObservable();
  }

  /**
   * Establish SSE connection to backend
   */
  private connectToSSE(): void {
    const sseUrl = `${APP_CONFIG.API_ENDPOINTS.SSE}/godot/status/stream`;
    console.log(`[SSE] Connecting to: ${sseUrl}`);
    console.log(`[SSE] APP_CONFIG.SSE endpoint: ${APP_CONFIG.API_ENDPOINTS.SSE}`);

    try {
      this.eventSource = new EventSource(sseUrl);
      console.log('[SSE] EventSource created successfully');

      this.eventSource.onmessage = (event) => {
        try {
          console.log('[SSE] Raw message received:', event.data);
          console.log('[SSE] Message type:', typeof event.data);
          console.log('[SSE] Message length:', event.data.length);

          const status = JSON.parse(event.data) as GodotStatus;
          console.log('[SSE] Parsed status:', status);
          console.log('[SSE] Project name:', status.project_name);
          console.log('[SSE] Connection state:', status.state);
          console.log('[SSE] Godot version:', status.godot_version);
          console.log('[SSE] Project path:', status.project_path);

          // Emit to subject
          this.godotStatusSubject.next(status);
          console.log('[SSE] Status emitted to subject, current observers count:', this.godotStatusSubject.observers.length);

          this.reconnectAttempts = 0; // Reset on successful message
        } catch (error) {
          console.error('[SSE] Error parsing message:', error);
          console.error('[SSE] Raw data that failed to parse:', event.data);
          console.error('[SSE] Data type:', typeof event.data);
        }
      };

      this.eventSource.onerror = (error) => {
        console.error('[SSE] Connection error:', error);
        console.error('[SSE] EventSource readyState:', this.eventSource?.readyState);
        console.error('[SSE] Reconnect attempts:', this.reconnectAttempts);

        this.eventSource?.close();
        this.eventSource = undefined;

        // Attempt reconnection with exponential backoff
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
          console.log(`[SSE] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

          setTimeout(() => {
            this.connectToSSE();
          }, delay);
        } else {
          console.error('[SSE] Max reconnection attempts reached');
          // Emit disconnected state
          this.godotStatusSubject.next({ state: 'disconnected' });
        }
      };

      this.eventSource.onopen = () => {
        console.log('[SSE] Connection established successfully');
        console.log('[SSE] EventSource readyState on open:', this.eventSource?.readyState);
        this.reconnectAttempts = 0;
      };
    } catch (error) {
      console.error('[SSE] Error creating connection:', error);
      console.error('[SSE] SSE URL that failed:', sseUrl);
    }
  }

  /**
   * Disconnect from SSE stream
   */
  disconnectFromSSE(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = undefined;
      console.log('SSE connection closed');
    }
  }

  /**
   * Cleanup on service destroy
   */
  ngOnDestroy(): void {
    this.disconnectFromSSE();
    this.godotStatusSubject.complete();
  }
}
