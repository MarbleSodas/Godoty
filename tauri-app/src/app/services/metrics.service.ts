import { Injectable } from '@angular/core';
import { invoke } from '@tauri-apps/api/core';
import { BehaviorSubject, interval, Subscription } from 'rxjs';
import { MetricsSummary, WorkflowMetrics } from '../models/metrics.model';

@Injectable({ providedIn: 'root' })
export class MetricsService {
  private summary$ = new BehaviorSubject<MetricsSummary | null>(null);
  private all$ = new BehaviorSubject<WorkflowMetrics[] | null>(null);
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
      const summary = await invoke<MetricsSummary>('get_metrics_summary');
      this.summary$.next(summary);
    } catch (e) {
      // ignore
    }
    try {
      const all = await invoke<WorkflowMetrics[]>('get_workflow_metrics');
      this.all$.next(all);
    } catch (e) {
      // ignore
    }
  }

  getSummary() { return this.summary$.asObservable(); }
  getAll() { return this.all$.asObservable(); }

  async clear(): Promise<void> {
    await invoke('clear_metrics');
    await this.refresh();
  }
}
