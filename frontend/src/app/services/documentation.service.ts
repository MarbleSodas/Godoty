import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, BehaviorSubject } from 'rxjs';

export interface DocumentationStatus {
  success: boolean;
  status: 'not_built' | 'building' | 'completed' | 'error';
  database_exists: boolean;
  db_path?: string;
  size_mb?: number;
  build_timestamp?: string;
  total_classes?: number;
  total_methods?: number;
  total_properties?: number;
  total_signals?: number;
  total_entries?: number;
  godot_version?: string;
  error?: string;
  error_message?: string;
  message?: string;
}

export interface RebuildProgress {
  stage: 'starting' | 'running' | 'downloading' | 'parsing' | 'building' | 'completed' | 'error';
  progress: number; // 0-100
  message: string;
  error?: string;
}

@Injectable({
  providedIn: 'root'
})
export class DocumentationService {
  private readonly baseUrl = 'http://127.0.0.1:8000/api/documentation';

  // Reactive state for documentation status
  public documentationStatus$ = new BehaviorSubject<DocumentationStatus | null>(null);
  public rebuildProgress$ = new BehaviorSubject<RebuildProgress | null>(null);
  public isRebuilding$ = new BehaviorSubject<boolean>(false);

  constructor(private http: HttpClient) {}

  /**
   * Get current documentation database status
   */
  getDocumentationStatus(): Observable<DocumentationStatus> {
    return this.http.get<DocumentationStatus>(`${this.baseUrl}/status`);
  }

  /**
   * Get current rebuild status
   */
  getRebuildStatus(): Observable<any> {
    return this.http.get(`${this.baseUrl}/rebuild/status`);
  }

  /**
   * Rebuild documentation database
   * If godotVersion is not provided, it will be auto-detected from the connected Godot editor
   */
  rebuildDocumentation(forceRebuild: boolean = true, godotVersion?: string): Observable<any> {
    this.isRebuilding$.next(true);
    this.rebuildProgress$.next({
      stage: 'downloading',
      progress: 0,
      message: 'Starting documentation rebuild...'
    });

    // Build query params
    let params = `force_rebuild=${forceRebuild}`;
    if (godotVersion) {
      params += `&godot_version=${godotVersion}`;
    }

    return this.http.post(`${this.baseUrl}/rebuild?${params}`, {});
  }

  /**
   * Update status in reactive store
   */
  updateStatus(status: DocumentationStatus) {
    this.documentationStatus$.next(status);
  }

  /**
   * Update rebuild progress
   */
  updateProgress(progress: RebuildProgress) {
    this.rebuildProgress$.next(progress);

    if (progress.stage === 'completed' || progress.stage === 'error') {
      this.isRebuilding$.next(false);
    }
  }

  /**
   * Reset rebuild state
   */
  resetRebuildState() {
    this.isRebuilding$.next(false);
    this.rebuildProgress$.next(null);
  }
}