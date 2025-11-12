import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';
import { ProjectMetricsService } from '../../services/project-metrics.service';
import { ProjectMetrics } from '../../models/command.model';

@Component({
  selector: 'app-project-metrics-panel',
  imports: [CommonModule],
  templateUrl: './project-metrics-panel.component.html',
  styleUrl: './project-metrics-panel.component.css'
})
export class ProjectMetricsPanelComponent implements OnInit, OnDestroy {
  metrics: ProjectMetrics | null = null;
  private sub?: Subscription;

  constructor(private projectMetricsService: ProjectMetricsService) {}

  ngOnInit(): void {
    this.projectMetricsService.startPolling(5000);
    this.sub = this.projectMetricsService.getMetrics().subscribe(m => this.metrics = m);
  }

  ngOnDestroy(): void {
    this.projectMetricsService.stopPolling();
    if (this.sub) {
      try { this.sub.unsubscribe(); } catch {}
    }
  }

  formatCost(cost: number): string {
    return cost.toFixed(4);
  }

  formatNumber(num: number): string {
    return num.toLocaleString();
  }
}
