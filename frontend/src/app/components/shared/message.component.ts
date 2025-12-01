import { Component, Input, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ToolCallComponent } from './tool-call.component';

// Import heroicons
import { NgIconComponent, provideIcons } from '@ng-icons/core';
import {
  heroUser,
  heroChatBubbleLeftRight,
  heroDocumentText,
  heroCurrencyDollar,
  heroClock,
  heroBolt
} from '@ng-icons/heroicons/outline';

@Component({
  selector: 'app-message',
  standalone: true,
  imports: [CommonModule, FormsModule, ToolCallComponent, NgIconComponent],
  providers: [
    provideIcons({
      heroUser,
      heroChatBubbleLeftRight,
      heroDocumentText,
      heroCurrencyDollar,
      heroClock,
      heroBolt
    })
  ],
  template: `
    <div class="message-container" [class.user-message]="message.role === 'user'" [class.assistant-message]="message.role === 'assistant'">
      <!-- Message Header -->
      <div class="message-header">
        <div class="message-role">
          <span class="role-badge" [class]="message.role === 'user' ? 'user-badge' : 'assistant-badge'">
            @if (message.role === 'user') {
              <ng-icon name="heroUser" class="w-4 h-4" />
              User
            } @else {
              <ng-icon name="heroChatBubbleLeftRight" class="w-4 h-4" />
              Assistant
            }
          </span>
        </div>
        <div class="message-timestamp">
          {{ formatTimestamp(message.timestamp) }}
        </div>
        @if (message.modelName) {
          <div class="message-model">
            {{ message.modelName }}
          </div>
        }
      </div>

      <!-- Message Content -->
      <div class="message-content">
        <div class="prose prose-sm max-w-none" [innerHTML]="formatMessageContent(message.content)"></div>
      </div>

      <!-- Execution Plan -->
      @if (message.plan) {
        <div class="execution-plan">
          <h4 class="plan-title">
            <ng-icon name="heroDocumentText" class="w-4 h-4 inline mr-1" />
            {{ message.plan.title }}
          </h4>
          @if (message.plan.description) {
            <p class="plan-description">{{ message.plan.description }}</p>
          }
          <div class="plan-steps">
            @for (step of message.plan.steps; track step.id) {
              <div class="plan-step" [class]="getStepClass(step.status)">
                <div class="step-header">
                  <span class="step-icon">{{ getStepIcon(step.status) }}</span>
                  <span class="step-title">{{ step.title }}</span>
                </div>
                @if (step.description) {
                  <p class="step-description">{{ step.description }}</p>
                }
                @if (step.tool_calls && step.tool_calls.length > 0) {
                  <div class="step-tools">
                    @for (tool of step.tool_calls; track tool.name) {
                      <span class="tool-badge">{{ tool.name }}</span>
                    }
                  </div>
                }
              </div>
            }
          </div>
        </div>
      }

      <!-- Tool Calls -->
      @if (message.toolCalls && message.toolCalls.length > 0) {
        <div class="tool-calls">
          <h4 class="tool-calls-title">
            <ng-icon name="heroBolt" class="w-4 h-4 inline mr-1" />
            Tool Calls
          </h4>
          @for (toolCall of message.toolCalls; track toolCall.name) {
            <app-tool-call [toolCall]="toolCall"></app-tool-call>
          }
        </div>
      }

      <!-- Message Metrics -->
      @if (showMetrics && (message.tokens || message.cost)) {
        <div class="message-metrics">
          <div class="metrics-row">
            @if (message.tokens) {
              <span class="metric">
                <ng-icon name="heroDocumentText" class="w-3 h-3" />
                {{ formatTokens(message.tokens) }} tokens
              </span>
            }
            @if (message.promptTokens && message.completionTokens) {
              <span class="metric">
                <ng-icon name="heroDocumentText" class="w-3 h-3" />
                {{ message.promptTokens }} → {{ message.completionTokens }}
              </span>
            }
            @if (message.cost) {
              <span class="metric cost">
                <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M8.433 7.418c.155-.103.346-.196.567-.267v1.698a2.305 2.305 0 01-.567-.267C8.07 8.34 8 8.114 8 8c0-.114.07-.34.433-.582zM11 12.849v-1.698c.22.071.412.164.567.267.364.243.433.468.433.582 0 .114-.07.34-.433.582a2.305 2.305 0 01-.567.267z"/>
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-13a1 1 0 10-2 0v.092a4.535 4.535 0 00-1.676.662C6.602 6.234 6 7.009 6 8c0 .99.602 1.765 1.324 2.246.48.32 1.054.545 1.676.662v1.941c-.391-.127-.68-.317-.843-.504a1 1 0 10-1.51 1.31c.562.649 1.413 1.076 2.353 1.253V15a1 1 0 102 0v-.092a4.535 4.535 0 001.676-.662C13.398 13.766 14 12.991 14 12c0-.99-.602-1.765-1.324-2.246A4.535 4.535 0 0011 9.092V7.151c.391.127.68.317.843.504a1 1 0 101.511-1.31c-.563-.649-1.413-1.076-2.354-1.253V5z" clip-rule="evenodd"/>
                </svg>
                {{ formatCost(message.cost) }}
              </span>
            }
            @if (message.generationTimeMs) {
              <span class="metric">
                <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clip-rule="evenodd"/>
                </svg>
                {{ formatTime(message.generationTimeMs) }}
              </span>
            }
          </div>
        </div>
      }

      <!-- Streaming Indicator -->
      @if (message.isStreaming) {
        <div class="streaming-indicator">
          <span class="streaming-dot"></span>
          <span class="streaming-text">Generating response...</span>
        </div>
      }
    </div>
  `,
  styles: [`
    .message-container {
      @apply mb-4 p-4 rounded-lg border;
    }

    .user-message {
      @apply bg-blue-50 border-blue-200 ml-auto max-w-3xl;
    }

    .assistant-message {
      @apply bg-gray-50 border-gray-200 mr-auto max-w-4xl;
    }

    .message-header {
      @apply flex items-center justify-between mb-2;
    }

    .message-role {
      @apply flex items-center gap-2;
    }

    .role-badge {
      @apply flex items-center gap-1 px-2 py-1 rounded text-xs font-medium;
    }

    .user-badge {
      @apply bg-blue-100 text-blue-800;
    }

    .assistant-badge {
      @apply bg-green-100 text-green-800;
    }

    .message-timestamp, .message-model {
      @apply text-xs text-gray-500;
    }

    .message-content {
      @apply text-sm leading-relaxed;
    }

    .execution-plan {
      @apply mt-3 p-3 bg-blue-50 border border-blue-200 rounded-lg;
    }

    .plan-title {
      @apply font-semibold text-sm mb-2 flex items-center;
    }

    .plan-description {
      @apply text-sm text-gray-600 mb-3;
    }

    .plan-steps {
      @apply space-y-2;
    }

    .plan-step {
      @apply p-2 border rounded;
    }

    .plan-step.pending {
      @apply bg-gray-50 border-gray-200;
    }

    .plan-step.running {
      @apply bg-yellow-50 border-yellow-200;
    }

    .plan-step.completed {
      @apply bg-green-50 border-green-200;
    }

    .plan-step.failed {
      @apply bg-red-50 border-red-200;
    }

    .step-header {
      @apply flex items-center gap-2;
    }

    .step-icon {
      @apply text-xs;
    }

    .step-title {
      @apply font-medium text-sm;
    }

    .step-description {
      @apply text-sm text-gray-600 mt-1;
    }

    .step-tools {
      @apply flex gap-1 mt-2;
    }

    .tool-badge {
      @apply px-2 py-1 bg-purple-100 text-purple-700 text-xs rounded;
    }

    .tool-calls {
      @apply mt-3;
    }

    .tool-calls-title {
      @apply font-semibold text-sm mb-2 flex items-center;
    }

    .message-metrics {
      @apply mt-3 pt-3 border-t border-gray-200;
    }

    .metrics-row {
      @apply flex flex-wrap gap-3;
    }

    .metric {
      @apply flex items-center gap-1 text-xs text-gray-500;
    }

    .metric.cost {
      @apply text-green-600 font-medium;
    }

    .streaming-indicator {
      @apply flex items-center gap-2 mt-2;
    }

    .streaming-dot {
      @apply w-2 h-2 bg-green-500 rounded-full animate-pulse;
    }

    .streaming-text {
      @apply text-xs text-gray-500 italic;
    }

    .prose {
      @apply text-gray-700;
    }

    .prose p {
      @apply mb-2;
    }

    .prose p:last-child {
      @apply mb-0;
    }

    .prose pre {
      @apply bg-gray-100 p-2 rounded text-xs overflow-x-auto;
    }

    .prose code {
      @apply bg-gray-100 px-1 py-0.5 rounded text-xs;
    }
  `]
})
export class MessageComponent implements OnChanges {
  @Input() message: any;
  @Input() showMetrics: boolean = true;

  ngOnChanges(changes: SimpleChanges): void {
    // Handle message changes if needed
  }

  formatTimestamp(timestamp: Date): string {
    return new Date(timestamp).toLocaleTimeString();
  }

  formatMessageContent(content: string): string {
    // Basic markdown-like formatting for display
    return content
      .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre class="language-$1"><code>$2</code></pre>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/\n/g, '<br>');
  }

  formatTokens(tokens: number): string {
    if (tokens < 1000) {
      return tokens.toString();
    } else if (tokens < 1000000) {
      return `${(tokens / 1000).toFixed(1)}K`;
    } else {
      return `${(tokens / 1000000).toFixed(2)}M`;
    }
  }

  formatCost(cost: number): string {
    return `$${cost.toFixed(6)}`;
  }

  formatTime(ms: number): string {
    if (ms < 1000) {
      return `${ms}ms`;
    } else {
      return `${(ms / 1000).toFixed(1)}s`;
    }
  }

  getStepClass(status: string): string {
    return status || 'pending';
  }

  getStepIcon(status: string): string {
    switch (status) {
      case 'completed':
        return '✓';
      case 'failed':
        return '✗';
      case 'running':
        return '⟳';
      default:
        return '○';
    }
  }
}