import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-tool-call',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="tool-call" [class]="getStatusClass()">
      <div class="tool-header">
        <div class="tool-info">
          <div class="tool-icon">
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clip-rule="evenodd"/>
            </svg>
          </div>
          <span class="tool-name">{{ toolCall.name }}</span>
        </div>
        <div class="tool-status">
          <span class="status-badge" [class]="getStatusClass()">
            {{ getStatusText() }}
          </span>
        </div>
      </div>

      <!-- Tool Input Parameters -->
      @if (hasToolInput()) {
        <div class="tool-input">
          <div class="section-title">Input:</div>
          <div class="tool-params">
            @for (param of getToolParams(toolCall.input); track param.key) {
              <div class="param-item">
                <span class="param-key">{{ param.key }}:</span>
                <span class="param-value" [innerHTML]="formatValue(param.value)"></span>
              </div>
            }
          </div>
        </div>
      }

      <!-- Tool Result -->
      @if (toolCall.status === 'completed' && toolCall.result) {
        <div class="tool-result">
          <div class="section-title">Result:</div>
          <div class="result-content" [innerHTML]="formatResult(toolCall.result)"></div>
        </div>
      }

      <!-- Tool Error -->
      @if (toolCall.status === 'failed' && toolCall.error) {
        <div class="tool-error">
          <div class="section-title">Error:</div>
          <div class="error-content">{{ toolCall.error }}</div>
        </div>
      }

      <!-- Running Animation -->
      @if (toolCall.status === 'running') {
        <div class="tool-running">
          <div class="loading-animation">
            <div class="loading-dot"></div>
            <div class="loading-dot"></div>
            <div class="loading-dot"></div>
          </div>
          <span class="running-text">Executing tool...</span>
        </div>
      }
    </div>
  `,
  styles: [`
    .tool-call {
      @apply border rounded-lg p-3 mb-2;
    }

    .tool-call.running {
      @apply bg-yellow-50 border-yellow-200;
    }

    .tool-call.completed {
      @apply bg-green-50 border-green-200;
    }

    .tool-call.failed {
      @apply bg-red-50 border-red-200;
    }

    .tool-header {
      @apply flex items-center justify-between mb-3;
    }

    .tool-info {
      @apply flex items-center gap-2;
    }

    .tool-icon {
      @apply text-yellow-600;
    }

    .tool-name {
      @apply font-medium text-sm;
    }

    .tool-status {
      @apply flex items-center;
    }

    .status-badge {
      @apply px-2 py-1 text-xs font-medium rounded;
    }

    .running .status-badge {
      @apply bg-yellow-100 text-yellow-800;
    }

    .completed .status-badge {
      @apply bg-green-100 text-green-800;
    }

    .failed .status-badge {
      @apply bg-red-100 text-red-800;
    }

    .tool-input, .tool-result, .tool-error {
      @apply mb-3;
    }

    .tool-input:last-child,
    .tool-result:last-child,
    .tool-error:last-child {
      @apply mb-0;
    }

    .section-title {
      @apply text-xs font-semibold text-gray-700 mb-2;
    }

    .tool-params {
      @apply space-y-1;
    }

    .param-item {
      @apply text-sm;
    }

    .param-key {
      @apply font-medium text-gray-700;
    }

    .param-value {
      @apply ml-2 text-gray-600 break-all;
    }

    .result-content {
      @apply text-sm text-gray-700 bg-white p-2 border border-green-200 rounded;
    }

    .error-content {
      @apply text-sm text-red-700 bg-red-100 p-2 border border-red-200 rounded;
    }

    .tool-running {
      @apply flex items-center gap-2;
    }

    .loading-animation {
      @apply flex gap-1;
    }

    .loading-dot {
      @apply w-2 h-2 bg-yellow-500 rounded-full animate-bounce;
    }

    .loading-dot:nth-child(1) {
      animation-delay: 0ms;
    }

    .loading-dot:nth-child(2) {
      animation-delay: 150ms;
    }

    .loading-dot:nth-child(3) {
      animation-delay: 300ms;
    }

    .running-text {
      @apply text-xs text-gray-500 italic;
    }

    /* Code formatting for results */
    .result-content pre {
      @apply bg-gray-100 p-2 rounded text-xs overflow-x-auto;
    }

    .result-content code {
      @apply bg-gray-100 px-1 py-0.5 rounded text-xs;
    }
  `]
})
export class ToolCallComponent {
  @Input() toolCall: any;

  hasToolInput(): boolean {
    return this.toolCall?.input &&
           typeof this.toolCall.input === 'object' &&
           this.toolCall.input !== null &&
           Object.keys(this.toolCall.input).length > 0;
  }

  getStatusClass(): string {
    return this.toolCall.status || 'running';
  }

  getStatusText(): string {
    const status = this.toolCall.status || 'running';
    return status.charAt(0).toUpperCase() + status.slice(1);
  }

  getToolParams(input: any): Array<{key: string, value: any}> {
    const params: Array<{key: string, value: any}> = [];

    if (typeof input === 'object' && input !== null) {
      for (const [key, value] of Object.entries(input)) {
        params.push({ key, value });
      }
    } else {
      // If input is not an object, treat it as a single parameter
      params.push({ key: 'input', value: input });
    }

    return params;
  }

  formatValue(value: any): string {
    if (value === null) {
      return '<span class="text-gray-400">null</span>';
    }
    if (value === undefined) {
      return '<span class="text-gray-400">undefined</span>';
    }
    if (typeof value === 'string') {
      // Check if it looks like JSON
      if (value.trim().startsWith('{') || value.trim().startsWith('[')) {
        return `<code class="json-value">${this.escapeHtml(value)}</code>`;
      }
      return this.escapeHtml(value);
    }
    if (typeof value === 'object') {
      return `<code class="json-value">${this.escapeHtml(JSON.stringify(value, null, 2))}</code>`;
    }
    return String(value);
  }

  formatResult(result: any): string {
    if (typeof result === 'string') {
      // Handle markdown-like formatting
      return result
        .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre class="language-$1"><code>$2</code></pre>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');
    }

    if (typeof result === 'object') {
      return `<code class="json-value">${this.escapeHtml(JSON.stringify(result, null, 2))}</code>`;
    }

    return this.escapeHtml(String(result));
  }

  private escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}