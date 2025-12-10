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
  index_status?: {
    status: 'not_started' | 'scanning' | 'building_graph' | 'building_vectors' | 'complete' | 'failed';
    phase: string;
    current_step: number;
    total_steps: number;
    current_file: string;
    error?: string;
    started_at?: string;
    completed_at?: string;
    progress_percent: number;
  };
  chat_ready?: {
    ready: boolean;
    godot_connected: boolean;
    api_key_configured: boolean;
    message: string;
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
  private readonly API_BASE = 'api';

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
   * Open a URL in the default system browser via the backend
   */
  async openUrl(url: string): Promise<void> {
    console.log('[DesktopService] openUrl called:', url);
    console.log('[DesktopService] isReady:', this.isReady);
    console.log('[DesktopService] window.pywebview:', !!window.pywebview);

    if (this.isReady && window.pywebview?.api?.['open_url']) {
      try {
        console.log('[DesktopService] Calling python open_url...');
        const result = await window.pywebview.api['open_url'](url);
        console.log('[DesktopService] Python open_url result:', result);
      } catch (error) {
        console.error('[DesktopService] Failed to open URL via backend:', error);
        // Fallback or error handling
        window.open(url, '_blank');
      }
    } else {
      console.warn('[DesktopService] pywebview not ready, using fallback window.open');
      // Fallback for web browser environment
      window.open(url, '_blank');
    }
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
