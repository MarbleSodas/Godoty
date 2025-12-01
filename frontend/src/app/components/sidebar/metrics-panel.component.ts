import { Component, Input, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MetricsService, ProjectMetrics, SessionMetrics } from '../../services/metrics.service';
import { SessionService } from '../../services/session.service';

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
        @if (showRefresh) {
          <button
            class="refresh-button"
            (click)="refreshMetrics()"
            [disabled]="refreshing"
            title="Refresh metrics"
          >
            <svg class="w-4 h-4" [class]="refreshing ? 'animate-spin' : ''" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"/>
            </svg>
          </button>
        }
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

        <!-- Session Efficiency -->
        @if (sessionMetrics.totalTokens > 0 && sessionMetrics.sessionCost > 0) {
          <div class="efficiency-indicator">
            <div class="efficiency-label">Cost Efficiency</div>
            <div class="efficiency-bar">
              <div
                class="efficiency-fill"
                [style.width.%]="getEfficiencyPercentage(sessionMetrics.sessionCost, sessionMetrics.totalTokens)"
                [class]="getEfficiencyClass(sessionMetrics.sessionCost, sessionMetrics.totalTokens)"
              ></div>
            </div>
            <div class="efficiency-text">
              {{ getCostEfficiencyText(sessionMetrics.sessionCost, sessionMetrics.totalTokens) }}
            </div>
          </div>
        }
      </div>

      <!-- Project Metrics -->
      <div class="metrics-section">
        <h4 class="section-title">Project Total</h4>
        <div class="metrics-grid project-metrics">
          <div class="metric-item">
            <div class="metric-label">Sessions</div>
            <div class="metric-value">{{ projectMetrics.totalSessions }}</div>
          </div>
          <div class="metric-item">
            <div class="metric-label">Total Cost</div>
            <div class="metric-value cost">{{ formatCost(projectMetrics.totalCost) }}</div>
          </div>
          <div class="metric-item">
            <div class="metric-label">Total Tokens</div>
            <div class="metric-value tokens">{{ formatTokens(projectMetrics.totalTokens) }}</div>
          </div>
        </div>
      </div>

      <!-- Model Information -->
      @if (sessionMetrics.modelName) {
        <div class="metrics-section">
          <h4 class="section-title">Active Model</h4>
          <div class="model-info">
            <div class="model-name">{{ getModelDisplayName(sessionMetrics.modelName) }}</div>
            <div class="model-details">
              @if (modelPricing) {
                <div class="pricing-info">
                  <span class="pricing-label">Prompt:</span>
                  <span class="pricing-value">{{ modelPricing.prompt.toFixed(6) }}/token</span>
                </div>
                <div class="pricing-info">
                  <span class="pricing-label">Completion:</span>
                  <span class="pricing-value">{{ modelPricing.completion.toFixed(6) }}/token</span>
                </div>
              } @else {
                <div class="pricing-info">
                  <span class="pricing-label">Pricing not available</span>
                </div>
              }
            </div>
          </div>
        </div>
      }

      <!-- Cost Warning -->
      @if (projectMetrics.totalCost > 1.0) {
        <div class="cost-warning">
          <div class="warning-icon">
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
            </svg>
          </div>
          <div class="warning-text">
            Project cost exceeds $1.00
          </div>
        </div>
      }

      <!-- Metrics Status -->
      <div class="metrics-footer">
        @if (!isPricingLoaded()) {
          <div class="status-indicator loading">
            <svg class="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Loading pricing data...
          </div>
        } @else {
          <div class="status-indicator success">
            <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
            </svg>
            Real-time tracking active
          </div>
        }
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

    .refresh-button {
      @apply p-1 text-gray-400 hover:text-gray-600 rounded transition-colors duration-200;
    }

    .refresh-button:disabled {
      @apply opacity-50 cursor-not-allowed;
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
      @apply grid-cols-3;
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

    .efficiency-indicator {
      @apply space-y-1;
    }

    .efficiency-label {
      @apply text-xs text-gray-600;
    }

    .efficiency-bar {
      @apply w-full bg-gray-200 rounded-full h-2 overflow-hidden;
    }

    .efficiency-fill {
      @apply h-full transition-all duration-300;
    }

    .efficiency-fill.excellent {
      @apply bg-green-500;
    }

    .efficiency-fill.good {
      @apply bg-blue-500;
    }

    .efficiency-fill.warning {
      @apply bg-yellow-500;
    }

    .efficiency-fill.poor {
      @apply bg-red-500;
    }

    .efficiency-text {
      @apply text-xs text-gray-600;
    }

    .model-info {
      @apply bg-gray-50 rounded p-2 space-y-1;
    }

    .model-name {
      @apply font-medium text-sm text-gray-900;
    }

    .model-details {
      @apply space-y-1;
    }

    .pricing-info {
      @apply flex justify-between text-xs;
    }

    .pricing-label {
      @apply text-gray-500;
    }

    .pricing-value {
      @apply text-gray-700 font-mono;
    }

    .cost-warning {
      @apply flex items-center gap-2 p-2 bg-yellow-50 border border-yellow-200 rounded;
    }

    .warning-icon {
      @apply text-yellow-600 flex-shrink-0;
    }

    .warning-text {
      @apply text-xs text-yellow-800 font-medium;
    }

    .metrics-footer {
      @apply pt-2 border-t border-gray-100;
    }

    .status-indicator {
      @apply flex items-center gap-2 text-xs;
    }

    .status-indicator.loading {
      @apply text-blue-600;
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
export class MetricsPanelComponent implements OnInit {
  @Input() sessionMetrics: SessionMetrics = {
    totalTokens: 0,
    sessionCost: 0,
    toolCalls: 0
  };
  @Input() projectMetrics: ProjectMetrics = {
    totalCost: 0,
    totalTokens: 0,
    totalSessions: 0
  };
  @Input() showRefresh: boolean = true;

  refreshing: boolean = false;
  modelPricing: any = null;

  constructor(
    private metricsService: MetricsService,
    private sessionService: SessionService
  ) {}

  ngOnInit(): void {
    this.updateModelPricing();
  }

  isPricingLoaded(): boolean {
    return this.metricsService.isPricingLoaded();
  }

  refreshMetrics(): void {
    this.refreshing = true;
    this.metricsService.refreshPricing().finally(() => {
      this.refreshing = false;
      this.updateModelPricing();
    });
  }

  updateModelPricing(): void {
    if (this.sessionMetrics.modelName) {
      this.modelPricing = this.metricsService.getModelPricing(this.sessionMetrics.modelName);
    }
  }

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

  getCostEfficiencyText(cost: number, tokens: number): string {
    const efficiency = this.metricsService.calculateCostEfficiency(cost, tokens);
    return `${efficiency.toFixed(6)}$/1K tokens`;
  }

  getEfficiencyPercentage(cost: number, tokens: number): number {
    const efficiency = this.metricsService.calculateCostEfficiency(cost, tokens);
    // Map efficiency to percentage (0.001 is excellent, 0.01 is poor)
    const percentage = Math.max(0, Math.min(100, 100 - (efficiency * 10000)));
    return percentage;
  }

  getEfficiencyClass(cost: number, tokens: number): string {
    const efficiency = this.metricsService.calculateCostEfficiency(cost, tokens);

    if (efficiency < 0.002) return 'excellent';
    if (efficiency < 0.005) return 'good';
    if (efficiency < 0.01) return 'warning';
    return 'poor';
  }
}