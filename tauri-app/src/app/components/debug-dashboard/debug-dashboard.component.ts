import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MetricsPanelComponent } from '../metrics-panel/metrics-panel.component';
import { ProcessLogsComponent } from '../process-logs/process-logs.component';

@Component({
  selector: 'app-debug-dashboard',
  standalone: true,
  imports: [CommonModule, MetricsPanelComponent, ProcessLogsComponent],
  templateUrl: './debug-dashboard.component.html',
  styleUrls: ['./debug-dashboard.component.css']
})
export class DebugDashboardComponent {}

