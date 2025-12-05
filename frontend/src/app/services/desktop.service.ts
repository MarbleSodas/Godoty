import { Injectable } from '@angular/core';
import { Observable, Subject } from 'rxjs';
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
    });
  }

  /**
   * Get Godot connection status and project info (one-time HTTP request)
   */
  getGodotStatus(): Observable<GodotStatus> {
    return this.http.get<GodotStatus>(`${this.API_BASE}/godot/status`);
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

    try {
      this.eventSource = new EventSource(sseUrl);

      this.eventSource.onmessage = (event) => {
        try {
          const status = JSON.parse(event.data) as GodotStatus;
          this.godotStatusSubject.next(status);
          this.reconnectAttempts = 0;
        } catch { /* ignore parse errors */ }
      };

      this.eventSource.onerror = () => {
        this.eventSource?.close();
        this.eventSource = undefined;

        // Attempt reconnection with exponential backoff
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
          setTimeout(() => this.connectToSSE(), delay);
        } else {
          this.godotStatusSubject.next({ state: 'disconnected' });
        }
      };

      this.eventSource.onopen = () => {
        this.reconnectAttempts = 0;
      };
    } catch { /* ignore connection errors */ }
  }

  /**
   * Disconnect from SSE stream
   */
  disconnectFromSSE(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = undefined;
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
