import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ExecutionPlan, PlanStep } from '../../services/chat.service';

// Import heroicons
import { NgIconComponent, provideIcons } from '@ng-icons/core';
import {
  heroDocumentText,
  heroXMark,
  heroCodeBracket,
  heroClipboardDocumentList
} from '@ng-icons/heroicons/outline';

@Component({
  selector: 'app-execution-plan',
  standalone: true,
  imports: [CommonModule, NgIconComponent],
  providers: [
    provideIcons({
      heroDocumentText,
      heroXMark,
      heroCodeBracket,
      heroClipboardDocumentList
    })
  ],
  template: `
    <!-- Backdrop (mobile only) -->
    @if (isOpen && isMobile) {
      <div
        class="fixed inset-0 bg-black/50 z-40"
        (click)="onClose.emit()"
      ></div>
    }

    <!-- Sidebar -->
    <aside
      class="execution-plan-sidebar"
      [class.mobile]="isMobile"
      [class.desktop]="!isMobile"
    >
      <!-- Sidebar Header -->
      <div class="sidebar-header">
        <div class="header-left">
          <ng-icon name="heroClipboardDocumentList" class="w-4 h-4 text-[#478cbf]" />
          <h2 class="sidebar-title">Execution Plan</h2>
        </div>
        <button
          (click)="onClose.emit()"
          class="close-button"
          title="Close Tasks"
        >
          <ng-icon name="heroXMark" class="w-4 h-4" />
        </button>
      </div>

      <!-- Plan Title & Description -->
      @if (plan) {
        <div class="plan-info">
          <h3 class="plan-title">{{ plan.title }}</h3>
          @if (plan.description) {
            <p class="plan-description">{{ plan.description }}</p>
          }
          <div class="plan-meta">
            <span class="plan-steps">{{ plan.steps.length }} steps</span>
            <span class="status-badge" [class]="plan.status">{{ plan.status }}</span>
          </div>
        </div>

        <!-- Steps List -->
        <div class="steps-container">
          <div class="steps-list">
            @for (step of plan.steps; track step.id; let idx = $index) {
              <div
                class="step-item"
                [class]="step.status"
              >
                <!-- Step Header -->
                <div class="step-header">
                  <!-- Status Icon -->
                  <div class="step-status">
                    @if (step.status === 'completed') {
                      <svg class="w-4 h-4 status-icon completed" viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
                      </svg>
                    } @else if (step.status === 'running') {
                      <div class="status-spinner"></div>
                    } @else if (step.status === 'failed') {
                      <svg class="w-4 h-4 status-icon failed" viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
                      </svg>
                    } @else {
                      <div class="status-dot"></div>
                    }
                  </div>

                  <!-- Step Number & Title -->
                  <div class="step-content">
                    <div class="step-title">
                      <span class="step-number">{{ idx + 1 }}.</span>
                      <span class="step-name">{{ step.title }}</span>
                    </div>
                  </div>
                </div>

                <!-- Step Description -->
                @if (step.description) {
                  <p class="step-description">{{ step.description }}</p>
                }

                <!-- Tool Calls (if any) -->
                @if (step.tool_calls && step.tool_calls.length > 0) {
                  <div class="step-tools">
                    @for (tool of step.tool_calls; track tool.name + $index) {
                      <div class="tool-item">
                        <ng-icon name="heroCodeBracket" class="w-3 h-3 tool-icon" />
                        <span class="tool-name">{{ tool.name }}</span>
                      </div>
                    }
                  </div>
                }
              </div>
            }
          </div>
        </div>

        <!-- Progress Footer -->
        <div class="progress-footer">
          <div class="progress-info">
            <span class="progress-text">Progress</span>
            <span class="progress-count">{{ getCompletedStepsCount() }} / {{ plan.steps.length }}</span>
          </div>
          <div class="progress-bar">
            <div
              class="progress-fill"
              [style.width.%]="getProgressPercentage()"
            ></div>
          </div>
        </div>
      } @else {
        <div class="empty-state">
          <ng-icon name="heroDocumentText" class="w-8 h-8 empty-icon" />
          <p class="empty-text">No execution plan available</p>
          <p class="empty-subtext">Plans will appear here when agents generate them</p>
        </div>
      }
    </aside>
  `,
  styles: [`
    .execution-plan-sidebar {
      @apply w-80 border-l border-[#363d4a] bg-[#212529] flex flex-col overflow-hidden;
    }

    .execution-plan-sidebar.mobile {
      @apply fixed md:relative right-0 top-0 h-full z-50 md:z-auto md:flex-shrink-0;
    }

    .execution-plan-sidebar.desktop {
      @apply relative;
    }

    .sidebar-header {
      @apply h-14 border-b border-[#363d4a] flex items-center justify-between px-4 bg-[#212529]/50 backdrop-blur;
    }

    .header-left {
      @apply flex items-center gap-2;
    }

    .sidebar-title {
      @apply text-sm font-semibold text-white;
    }

    .close-button {
      @apply p-1 rounded hover:bg-[#363d4a] text-slate-400 hover:text-white transition-colors;
    }

    .plan-info {
      @apply px-4 py-3 border-b border-[#363d4a] bg-[#1a1d21];
    }

    .plan-title {
      @apply text-sm font-medium text-white mb-1;
    }

    .plan-description {
      @apply text-xs text-slate-400 leading-relaxed mb-2;
    }

    .plan-meta {
      @apply flex items-center gap-2 text-[10px] text-slate-500;
    }

    .plan-steps {
      @apply font-medium;
    }

    .status-badge {
      @apply uppercase px-1.5 py-0.5 rounded font-medium;
    }

    .status-badge.pending {
      @apply bg-blue-500/20 text-blue-400;
    }

    .status-badge.running {
      @apply bg-yellow-500/20 text-yellow-400;
    }

    .status-badge.completed {
      @apply bg-green-500/20 text-green-400;
    }

    .status-badge.failed {
      @apply bg-red-500/20 text-red-400;
    }

    .steps-container {
      @apply flex-1 overflow-y-auto p-2;
    }

    .steps-list {
      @apply space-y-1;
    }

    .step-item {
      @apply p-3 rounded-lg border transition-all duration-200;
    }

    .step-item.pending {
      @apply border-[#363d4a] bg-transparent;
    }

    .step-item.running {
      @apply border-[#478cbf]/30 bg-[#478cbf]/5;
    }

    .step-item.completed {
      @apply border-green-500/30 bg-green-500/5;
    }

    .step-item.failed {
      @apply border-red-500/30 bg-red-500/5;
    }

    .step-header {
      @apply flex items-start gap-2 mb-2;
    }

    .step-status {
      @apply flex-shrink-0 mt-0.5;
    }

    .status-icon {
      @apply text-current;
    }

    .status-icon.completed {
      @apply text-green-500;
    }

    .status-icon.failed {
      @apply text-red-500;
    }

    .status-spinner {
      @apply w-4 h-4 border-2 border-[#478cbf] border-t-transparent rounded-full animate-spin;
    }

    .status-dot {
      @apply w-4 h-4 rounded-full border-2 border-slate-600;
    }

    .step-content {
      @apply flex-1 min-w-0;
    }

    .step-title {
      @apply flex items-baseline gap-1.5;
    }

    .step-number {
      @apply text-[10px] font-mono text-slate-500 font-semibold;
    }

    .step-name {
      @apply text-xs font-medium text-white truncate;
    }

    .step-description {
      @apply text-[11px] text-slate-400 leading-relaxed ml-6 mb-2;
    }

    .step-tools {
      @apply ml-6 mt-2 space-y-1;
    }

    .tool-item {
      @apply flex items-center gap-1.5 text-[10px];
    }

    .tool-icon {
      @apply text-slate-500;
    }

    .tool-name {
      @apply font-mono text-slate-500;
    }

    .progress-footer {
      @apply border-t border-[#363d4a] px-4 py-2 bg-[#1a1d21];
    }

    .progress-info {
      @apply flex justify-between text-[10px] text-slate-500 mb-1;
    }

    .progress-text {
      @apply font-medium;
    }

    .progress-count {
      @apply font-mono;
    }

    .progress-bar {
      @apply w-full bg-[#2b303b] h-1 rounded-full overflow-hidden;
    }

    .progress-fill {
      @apply bg-green-500 h-full rounded-full transition-all duration-300;
    }

    .empty-state {
      @apply flex flex-col items-center justify-center py-8 text-center;
    }

    .empty-icon {
      @apply text-slate-600 mb-3;
    }

    .empty-text {
      @apply text-sm text-slate-400 mb-1;
    }

    .empty-subtext {
      @apply text-xs text-slate-500;
    }

    /* Animation for slide-in */
    .execution-plan-sidebar.mobile {
      animation: slideInRight 0.2s ease-out;
    }

    @keyframes slideInRight {
      from {
        transform: translateX(100%);
      }
      to {
        transform: translateX(0);
      }
    }
  `]
})
export class ExecutionPlanComponent {
  @Input() plan: ExecutionPlan | null = null;
  @Input() isOpen: boolean = false;
  @Input() isMobile: boolean = false;
  @Output() onClose = new EventEmitter<void>();

  getCompletedStepsCount(): number {
    if (!this.plan) return 0;
    return this.plan.steps.filter(s => s.status === 'completed').length;
  }

  getProgressPercentage(): number {
    if (!this.plan || this.plan.steps.length === 0) return 0;
    return (this.getCompletedStepsCount() / this.plan.steps.length) * 100;
  }
}