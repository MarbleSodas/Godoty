import { Injectable } from '@angular/core';
import { from, Observable, Subject } from 'rxjs';
import { HttpClient } from '@angular/common/http';

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
  private readonly API_BASE = 'http://localhost:8000/api';

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
    return this.http.get<GodotStatus>(`${this.API_BASE}/godot/status`);
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
    const sseUrl = `${this.API_BASE}/godot/status/stream`;
    console.log(`[SSE] Connecting to: ${sseUrl}`);

    try {
      this.eventSource = new EventSource(sseUrl);

      this.eventSource.onmessage = (event) => {
        try {
          console.log('[SSE] Received message:', event.data);
          const status = JSON.parse(event.data) as GodotStatus;
          console.log('[SSE] Parsed status:', status);
          this.godotStatusSubject.next(status);
          this.reconnectAttempts = 0; // Reset on successful message
        } catch (error) {
          console.error('[SSE] Error parsing message:', error, 'Raw data:', event.data);
        }
      };

      this.eventSource.onerror = (error) => {
        console.error('[SSE] Connection error:', error);
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
        this.reconnectAttempts = 0;
      };
    } catch (error) {
      console.error('[SSE] Error creating connection:', error);
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
