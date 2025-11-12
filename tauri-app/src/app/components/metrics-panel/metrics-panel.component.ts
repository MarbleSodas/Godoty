import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MetricsService } from '../../services/metrics.service';
import { MetricsSummary, WorkflowMetrics } from '../../models/metrics.model';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-metrics-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './metrics-panel.component.html',
  styleUrls: ['./metrics-panel.component.css']
})
export class MetricsPanelComponent implements OnInit, OnDestroy {
  summary: MetricsSummary | null = null;
  recent: WorkflowMetrics[] = [];
  private subs: Subscription[] = [];

  constructor(private metrics: MetricsService) {}

  ngOnInit(): void {
    this.metrics.startPolling(4000);
    this.subs.push(this.metrics.getSummary().subscribe(s => this.summary = s));
    this.subs.push(this.metrics.getAll().subscribe(list => {
      this.recent = (list || []).slice(-5).reverse();
    }));
  }

  ngOnDestroy(): void {
    this.metrics.stopPolling();
    this.subs.forEach(s => { try { s.unsubscribe(); } catch {} });
  }

  async clear(): Promise<void> {
    await this.metrics.clear();
  }

  ms(ms: number | undefined | null): string {
    if (typeof ms !== 'number') return '-';
    if (ms < 1000) return `${ms} ms`;
    const s = (ms / 1000).toFixed(1);
    return `${s}s`;
  }
}

