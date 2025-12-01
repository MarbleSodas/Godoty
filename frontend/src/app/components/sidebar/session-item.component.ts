import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Session } from '../../services/session.service';
import { MetricsService } from '../../services/metrics.service';

@Component({
  selector: 'app-session-item',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div
      class="session-item"
      [class.active]="isActive"
      [class.clickable]="!isActive"
      (click)="onSessionClick()"
    >
      <div class="session-main">
        <div class="session-title-container">
          <h3 class="session-title" [title]="session.title">{{ session.title }}</h3>
          @if (isActive) {
            <div class="active-indicator">
              <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <circle cx="10" cy="10" r="6"/>
              </svg>
            </div>
          }
        </div>

        <div class="session-meta">
          <span class="session-date">{{ formatDate(session.date) }}</span>
          @if (session.metrics) {
            <span class="session-tokens" title="{{ session.metrics.session_tokens }} tokens">
              {{ formatTokens(session.metrics.session_tokens || 0) }}
            </span>
          }
        </div>
      </div>

      <!-- Session Metrics -->
      @if (showMetrics && session.metrics && (session.metrics.session_cost > 0 || session.metrics.session_tokens > 0)) {
        <div class="session-metrics">
          @if (session.metrics.session_cost > 0) {
            <div class="metric cost">
              <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path d="M8.433 7.418c.155-.103.346-.196.567-.267v1.698a2.305 2.305 0 01-.567-.267C8.07 8.34 8 8.114 8 8c0-.114.07-.34.433-.582zM11 12.849v-1.698c.22.071.412.164.567.267.364.243.433.468.433.582 0 .114-.07.34-.433.582a2.305 2.305 0 01-.567.267z"/>
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-13a1 1 0 10-2 0v.092a4.535 4.535 0 00-1.676.662C6.602 6.234 6 7.009 6 8c0 .99.602 1.765 1.324 2.246.48.32 1.054.545 1.676.662v1.941c-.391-.127-.68-.317-.843-.504a1 1 0 10-1.51 1.31c.562.649 1.413 1.076 2.353 1.253V15a1 1 0 102 0v-.092a4.535 4.535 0 001.676-.662C13.398 13.766 14 12.991 14 12c0-.99-.602-1.765-1.324-2.246A4.535 4.535 0 0011 9.092V7.151c.391.127.68.317.843.504a1 1 0 101.511-1.31c-.563-.649-1.413-1.076-2.354-1.253V5z" clip-rule="evenodd"/>
              </svg>
              <span class="metric-value">{{ formatCost(session.metrics.session_cost) }}</span>
            </div>
          }

          @if (session.metrics.session_tokens > 0) {
            <div class="metric tokens">
              <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z"/>
                <path fill-rule="evenodd" d="M4 5a2 2 0 012-2h8a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 1h6v8H7V6z" clip-rule="evenodd"/>
              </svg>
              <span class="metric-value">{{ formatTokens(session.metrics.session_tokens) }}</span>
            </div>
          }
        </div>
      }

      <!-- Actions -->
      @if (showActions && !isActive) {
        <div class="session-actions">
          <button
            class="action-button select"
            (click)="onSelectSession($event)"
            title="Select session"
          >
            <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
            </svg>
          </button>

          <button
            class="action-button delete"
            (click)="onDeleteSession($event)"
            title="Hide session"
          >
            <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 011-1z" clip-rule="evenodd"/>
            </svg>
          </button>
        </div>
      }

      <!-- Active Session Streaming Indicator -->
      @if (isActive && isStreaming) {
        <div class="streaming-indicator">
          <div class="streaming-dots">
            <div class="dot"></div>
            <div class="dot"></div>
            <div class="dot"></div>
          </div>
          <span class="streaming-text">Active</span>
        </div>
      }
    </div>
  `,
  styles: [`
    .session-item {
      @apply p-3 mb-2 border rounded-lg transition-all duration-200;
    }

    .session-item.clickable {
      @apply cursor-pointer hover:shadow-md hover:border-blue-300;
    }

    .session-item.active {
      @apply bg-blue-50 border-blue-500 shadow-md;
    }

    .session-item:not(.active) {
      @apply bg-white border-gray-200;
    }

    .session-main {
      @apply flex items-start justify-between mb-2;
    }

    .session-title-container {
      @apply flex items-start gap-2 flex-1 min-w-0;
    }

    .session-title {
      @apply text-sm font-medium text-gray-900 truncate flex-1;
    }

    .active-indicator {
      @apply text-blue-600 flex-shrink-0 mt-0.5;
    }

    .session-meta {
      @apply flex items-center gap-2 text-xs text-gray-500;
    }

    .session-date {
      @apply whitespace-nowrap;
    }

    .session-tokens {
      @apply bg-gray-100 px-2 py-0.5 rounded;
    }

    .session-metrics {
      @apply flex items-center gap-3 text-xs;
    }

    .metric {
      @apply flex items-center gap-1;
    }

    .metric.cost {
      @apply text-green-600;
    }

    .metric.tokens {
      @apply text-blue-600;
    }

    .metric-value {
      @apply font-medium;
    }

    .session-actions {
      @apply flex items-center gap-1 mt-2;
    }

    .action-button {
      @apply p-1.5 text-gray-400 hover:text-gray-600 rounded transition-colors duration-200;
    }

    .action-button.select:hover {
      @apply text-blue-600 bg-blue-50;
    }

    .action-button.delete:hover {
      @apply text-red-600 bg-red-50;
    }

    .streaming-indicator {
      @apply flex items-center gap-2 mt-2;
    }

    .streaming-dots {
      @apply flex gap-1;
    }

    .dot {
      @apply w-1.5 h-1.5 bg-blue-600 rounded-full animate-pulse;
    }

    .dot:nth-child(1) {
      animation-delay: 0ms;
    }

    .dot:nth-child(2) {
      animation-delay: 200ms;
    }

    .dot:nth-child(3) {
      animation-delay: 400ms;
    }

    .streaming-text {
      @apply text-xs text-blue-600 font-medium;
    }

    /* Compact mode for smaller screens */
    @media (max-width: 640px) {
      .session-item {
        @apply p-2;
      }

      .session-title {
        @apply text-xs;
      }

      .session-meta {
        @apply text-xs;
      }

      .session-metrics {
        @apply gap-2;
      }

      .metric-value {
        @apply hidden;
      }
    }
  `]
})
export class SessionItemComponent {
  @Input() session!: Session;
  @Input() isActive: boolean = false;
  @Input() showMetrics: boolean = true;
  @Input() showActions: boolean = true;
  @Input() isStreaming: boolean = false;

  @Output() sessionSelect = new EventEmitter<Session>();
  @Output() sessionDelete = new EventEmitter<Session>();

  constructor(private metricsService: MetricsService) {}

  onSessionClick(): void {
    if (this.isActive) return; // Don't emit if already active
    this.sessionSelect.emit(this.session);
  }

  onSelectSession(event: Event): void {
    event.stopPropagation();
    this.sessionSelect.emit(this.session);
  }

  onDeleteSession(event: Event): void {
    event.stopPropagation();
    this.sessionDelete.emit(this.session);
  }

  formatDate(date: Date): string {
    const now = new Date();
    const sessionDate = new Date(date);
    const diffMs = now.getTime() - sessionDate.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) {
      return 'Just now';
    } else if (diffMins < 60) {
      return `${diffMins}m ago`;
    } else if (diffHours < 24) {
      return `${diffHours}h ago`;
    } else if (diffDays < 7) {
      return `${diffDays}d ago`;
    } else {
      return sessionDate.toLocaleDateString();
    }
  }

  formatTokens(tokens: number): string {
    return this.metricsService.formatTokens(tokens);
  }

  formatCost(cost: number): string {
    return this.metricsService.formatCost(cost);
  }
}