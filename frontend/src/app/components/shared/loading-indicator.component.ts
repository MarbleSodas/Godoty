import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-loading-indicator',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="loading-container" [class]="getSizeClass()">
      @if (type === 'spinner') {
        <div class="loading-spinner">
          <svg class="animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
        </div>
      } @else if (type === 'dots') {
        <div class="loading-dots">
          <div class="dot"></div>
          <div class="dot"></div>
          <div class="dot"></div>
        </div>
      } @else if (type === 'pulse') {
        <div class="loading-pulse">
          <div class="pulse-dot"></div>
        </div>
      } @else if (type === 'text') {
        <div class="loading-text">
          @for (i of [].constructor(dots || 3); track i) {
            <span class="text-dot">.</span>
          }
        </div>
      }

      @if (message) {
        <p class="loading-message">{{ message }}</p>
      }

      @if (showProgress && progress !== undefined) {
        <div class="progress-container">
          <div class="progress-bar">
            <div class="progress-fill" [style.width.%]="progress"></div>
          </div>
          @if (showProgressText) {
            <span class="progress-text">{{ progress }}%</span>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .loading-container {
      @apply flex flex-col items-center justify-center p-4;
    }

    .loading-container.small {
      @apply p-2;
    }

    .loading-container.large {
      @apply p-8;
    }

    /* Spinner Styles */
    .loading-spinner {
      @apply flex items-center justify-center;
    }

    .loading-spinner svg {
      @apply w-6 h-6 text-blue-600;
    }

    .small .loading-spinner svg {
      @apply w-4 h-4;
    }

    .large .loading-spinner svg {
      @apply w-8 h-8;
    }

    /* Dots Styles */
    .loading-dots {
      @apply flex gap-1;
    }

    .dot {
      @apply w-2 h-2 bg-blue-600 rounded-full animate-bounce;
    }

    .dot:nth-child(1) {
      animation-delay: 0ms;
    }

    .dot:nth-child(2) {
      animation-delay: 150ms;
    }

    .dot:nth-child(3) {
      animation-delay: 300ms;
    }

    .small .dot {
      @apply w-1.5 h-1.5;
    }

    .large .dot {
      @apply w-3 h-3;
    }

    /* Pulse Styles */
    .loading-pulse {
      @apply flex items-center justify-center;
    }

    .pulse-dot {
      @apply w-4 h-4 bg-blue-600 rounded-full animate-ping;
    }

    .small .pulse-dot {
      @apply w-3 h-3;
    }

    .large .pulse-dot {
      @apply w-6 h-6;
    }

    /* Text Styles */
    .loading-text {
      @apply flex items-center text-blue-600 font-mono text-lg;
    }

    .small .loading-text {
      @apply text-sm;
    }

    .large .loading-text {
      @apply text-xl;
    }

    .text-dot {
      @apply inline-block animate-bounce;
    }

    .text-dot:nth-child(1) {
      animation-delay: 0ms;
    }

    .text-dot:nth-child(2) {
      animation-delay: 150ms;
    }

    .text-dot:nth-child(3) {
      animation-delay: 300ms;
    }

    .text-dot:nth-child(4) {
      animation-delay: 450ms;
    }

    .text-dot:nth-child(5) {
      animation-delay: 600ms;
    }

    /* Message Styles */
    .loading-message {
      @apply mt-2 text-sm text-gray-600 text-center;
    }

    .small .loading-message {
      @apply text-xs;
    }

    .large .loading-message {
      @apply text-base;
    }

    /* Progress Styles */
    .progress-container {
      @apply w-full mt-3 flex items-center gap-2;
    }

    .progress-bar {
      @apply flex-1 bg-gray-200 rounded-full h-2 overflow-hidden;
    }

    .progress-fill {
      @apply bg-blue-600 h-full transition-all duration-300 ease-out;
    }

    .progress-text {
      @apply text-xs text-gray-600 font-medium min-w-[3rem] text-right;
    }

    /* Color Variants */
    .loading-container.secondary .loading-spinner svg,
    .loading-container.secondary .dot,
    .loading-container.secondary .pulse-dot,
    .loading-container.secondary .loading-text {
      @apply text-gray-600 bg-gray-600;
    }

    .loading-container.success .loading-spinner svg,
    .loading-container.success .dot,
    .loading-container.success .pulse-dot,
    .loading-container.success .loading-text {
      @apply text-green-600 bg-green-600;
    }

    .loading-container.warning .loading-spinner svg,
    .loading-container.warning .dot,
    .loading-container.warning .pulse-dot,
    .loading-container.warning .loading-text {
      @apply text-yellow-600 bg-yellow-600;
    }

    .loading-container.error .loading-spinner svg,
    .loading-container.error .dot,
    .loading-container.error .pulse-dot,
    .loading-container.error .loading-text {
      @apply text-red-600 bg-red-600;
    }

    /* Inline Mode */
    .loading-container.inline {
      @apply flex-row p-0;
    }

    .loading-container.inline .loading-spinner {
      @apply mr-2;
    }

    .loading-container.inline .loading-message {
      @apply mt-0;
    }
  `]
})
export class LoadingIndicatorComponent {
  @Input() type: 'spinner' | 'dots' | 'pulse' | 'text' = 'spinner';
  @Input() message: string = '';
  @Input() size: 'small' | 'medium' | 'large' = 'medium';
  @Input() showProgress: boolean = false;
  @Input() progress: number | undefined;
  @Input() showProgressText: boolean = true;
  @Input() dots: number = 3;
  @Input() color: 'primary' | 'secondary' | 'success' | 'warning' | 'error' = 'primary';
  @Input() inline: boolean = false;

  getSizeClass(): string {
    const classes: string[] = [this.size];

    if (this.color !== 'primary') {
      classes.push(this.color);
    }

    if (this.inline) {
      classes.push('inline');
    }

    return classes.join(' ');
  }
}