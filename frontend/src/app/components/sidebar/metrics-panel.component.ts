import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MetricsService, SessionMetrics } from '../../services/metrics.service';

// Simple interface for project metrics since we removed the complex one
export interface SimpleProjectMetrics {
  totalSessions: number;
}

@Component({
  selector: 'app-metrics-panel',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="metrics-panel">
      <div class="metrics-header">
        <h3 class="metrics-title">
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zM8 7a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zM14 4a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z"/>
          </svg>
          Metrics
        </h3>
      </div>

      <!-- Session Metrics -->
      <div class="metrics-section">
        <h4 class="section-title">Current Session</h4>
        <div class="metrics-grid session-metrics">
          <div class="metric-item">
            <div class="metric-label">Tokens</div>
            <div class="metric-value tokens">{{ formatTokens(sessionMetrics.totalTokens) }}</div>
          </div>
          <div class="metric-item">
            <div class="metric-label">Cost</div>
            <div class="metric-value cost">{{ formatCost(sessionMetrics.sessionCost) }}</div>
          </div>
          <div class="metric-item">
            <div class="metric-label">Tool Calls</div>
            <div class="metric-value">{{ sessionMetrics.toolCalls }}</div>
          </div>
          @if (sessionMetrics.generationTimeMs) {
            <div class="metric-item">
              <div class="metric-label">Time</div>
              <div class="metric-value">{{ formatTime(sessionMetrics.generationTimeMs) }}</div>
            </div>
          }
        </div>
      </div>

      <!-- Model Information -->
      @if (sessionMetrics.modelName) {
        <div class="metrics-section">
          <h4 class="section-title">Active Model</h4>
          <div class="model-info">
            <div class="model-name">{{ getModelDisplayName(sessionMetrics.modelName) }}</div>
          </div>
        </div>
      }

      <!-- Project Metrics -->
      <div class="metrics-section">
        <h4 class="section-title">Project Total</h4>
        <div class="metrics-grid project-metrics">
          <div class="metric-item">
            <div class="metric-label">Sessions</div>
            <div class="metric-value">{{ projectMetrics.totalSessions }}</div>
          </div>
        </div>
      </div>

      <!-- Metrics Status -->
      <div class="metrics-footer">
        <div class="status-indicator success">
          <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
          </svg>
          Raw cost tracking active
        </div>
      </div>
    </div>
  `,
  styles: [`
    .metrics-panel {
      @apply bg-white border border-gray-200 rounded-lg p-4 space-y-4;
    }

    .metrics-header {
      @apply flex items-center justify-between mb-3;
    }

    .metrics-title {
      @apply flex items-center gap-2 text-sm font-semibold text-gray-900;
    }

    .metrics-section {
      @apply space-y-2;
    }

    .section-title {
      @apply text-xs font-semibold text-gray-700 uppercase tracking-wide;
    }

    .metrics-grid {
      @apply grid grid-cols-2 gap-2;
    }

    .session-metrics {
      @apply grid-cols-2;
    }

    .project-metrics {
      @apply grid-cols-1;
    }

    .metric-item {
      @apply text-center;
    }

    .metric-label {
      @apply text-xs text-gray-500 mb-1;
    }

    .metric-value {
      @apply text-sm font-medium text-gray-900;
    }

    .metric-value.tokens {
      @apply text-blue-600;
    }

    .metric-value.cost {
      @apply text-green-600;
    }

    .model-info {
      @apply bg-gray-50 rounded p-2;
    }

    .model-name {
      @apply font-medium text-sm text-gray-900;
    }

    .metrics-footer {
      @apply pt-2 border-t border-gray-100;
    }

    .status-indicator {
      @apply flex items-center gap-2 text-xs;
    }

    .status-indicator.success {
      @apply text-green-600;
    }

    /* Compact mode */
    @media (max-width: 640px) {
      .metrics-grid {
        @apply grid-cols-1;
      }

      .project-metrics {
        @apply grid-cols-1;
      }
    }
  `]
})
export class MetricsPanelComponent {
  @Input() sessionMetrics: SessionMetrics = {
    totalTokens: 0,
    sessionCost: 0,
    toolCalls: 0
  };
  @Input() projectMetrics: SimpleProjectMetrics = {
    totalSessions: 0
  };

  constructor(
    private metricsService: MetricsService
  ) {}

  formatTokens(tokens: number): string {
    return this.metricsService.formatTokens(tokens);
  }

  formatCost(cost: number): string {
    return this.metricsService.formatCost(cost);
  }

  formatTime(ms: number): string {
    if (ms < 1000) {
      return `${ms}ms`;
    } else if (ms < 60000) {
      return `${(ms / 1000).toFixed(1)}s`;
    } else {
      return `${(ms / 60000).toFixed(1)}m`;
    }
  }

  getModelDisplayName(modelId: string): string {
    const parts = modelId.split('/');
    return parts[parts.length - 1] || modelId;
  }
}