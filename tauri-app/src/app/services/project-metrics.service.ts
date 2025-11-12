import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, interval, Subscription } from 'rxjs';
import { invoke } from '@tauri-apps/api/core';
import { ProjectMetrics } from '../models/command.model';

@Injectable({ providedIn: 'root' })
export class ProjectMetricsService {
  private metrics$ = new BehaviorSubject<ProjectMetrics | null>(null);
  private pollSub?: Subscription;

  startPolling(intervalMs = 5000): void {
    this.stopPolling();
    // Immediately fetch once, then on interval
    this.refresh().catch(() => {});
    this.pollSub = interval(intervalMs).subscribe(() => this.refresh().catch(() => {}));
  }

  stopPolling(): void {
    if (this.pollSub) {
      try { this.pollSub.unsubscribe(); } catch {}
      this.pollSub = undefined;
    }
  }

  async refresh(): Promise<void> {
    try {
      // First update the metrics from current sessions
      await invoke('update_project_metrics');
      // Then fetch the updated metrics
      const metrics = await invoke<ProjectMetrics>('get_project_metrics');
      this.metrics$.next(metrics);
    } catch (e) {
      // If project path not set or other error, just ignore
      this.metrics$.next(null);
    }
  }

  getMetrics(): Observable<ProjectMetrics | null> {
    return this.metrics$.asObservable();
  }

  async updateMetrics(): Promise<void> {
    await invoke('update_project_metrics');
    await this.refresh();
  }
}

