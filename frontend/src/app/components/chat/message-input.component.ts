import { Component, Input, Output, EventEmitter, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ConfigService } from '../../services/config.service';

@Component({
  selector: 'app-message-input',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="message-input-container">
      <!-- Mode Toggle -->
      <div class="mode-toggle-container">
        <div class="mode-toggle">
          <button
            type="button"
            class="mode-button"
            [class.active]="currentMode === 'planning'"
            [class.disabled]="disabled"
            (click)="setMode('planning')"
            [disabled]="disabled"
            title="Planning mode: Create detailed execution plans"
          >
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M3 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clip-rule="evenodd"/>
            </svg>
            <span class="mode-text">Planning</span>
          </button>
          <button
            type="button"
            class="mode-button"
            [class.active]="currentMode === 'fast'"
            [class.disabled]="disabled"
            (click)="setMode('fast')"
            [disabled]="disabled"
            title="Fast mode: Direct execution without detailed planning"
          >
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clip-rule="evenodd"/>
            </svg>
            <span class="mode-text">Fast</span>
          </button>
        </div>
        @if (modeDescription) {
          <div class="mode-description">{{ modeDescription }}</div>
        }
      </div>

      <!-- Input Form -->
      <form class="input-form" (ngSubmit)="onSubmit()">
        <div class="input-container">
          <div class="input-wrapper" [class.focused]="isFocused">
            <!-- File attachment button -->
            <button
              type="button"
              class="attachment-button"
              (click)="onAttachmentClick()"
              [disabled]="disabled || loading"
              title="Attach files"
            >
              <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM6.293 6.707a1 1 0 010-1.414l3-3a1 1 0 011.414 0l3 3a1 1 0 01-1.414 1.414L11 5.414V13a1 1 0 11-2 0V5.414L7.707 6.707a1 1 0 01-1.414 0z" clip-rule="evenodd"/>
              </svg>
            </button>

            <!-- Text input -->
            <textarea
              [(ngModel)]="message"
              (ngModelChange)="onInputChange()"
              (focus)="isFocused = true"
              (blur)="isFocused = false"
              (keydown)="onKeyDown($event)"
              (input)="adjustHeight()"
              #messageInput
              class="message-input"
              placeholder="Type your message..."
              [disabled]="disabled || loading"
              rows="1"
            ></textarea>

            <!-- Send button -->
            <button
              type="submit"
              class="send-button"
              [class.disabled]="!canSend || disabled"
              [disabled]="!canSend || disabled || loading"
              title="Send message (Enter)"
            >
              @if (loading) {
                <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
              } @else {
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z"/>
                </svg>
              }
            </button>
          </div>

          <!-- Character count -->
          @if (showCharacterCount && message.length > 0) {
            <div class="character-count" [class.warning]="message.length > characterCountWarning">
              {{ message.length }} / {{ maxCharacters }}
            </div>
          }
        </div>

        <!-- Keyboard shortcuts hint -->
        <div class="shortcuts-hint">
          <span class="shortcut-hint">
            <kbd class="kbd">Enter</kbd> to send
          </span>
          @if (!isMobile) {
            <span class="shortcut-hint">
              <kbd class="kbd">Shift</kbd> + <kbd class="kbd">Enter</kbd> for new line
            </span>
          }
        </div>
      </form>

      <!-- Attached files -->
      @if (attachedFiles.length > 0) {
        <div class="attached-files">
          <div class="files-header">
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM6.293 6.707a1 1 0 010-1.414l3-3a1 1 0 011.414 0l3 3a1 1 0 01-1.414 1.414L11 5.414V13a1 1 0 11-2 0V5.414L7.707 6.707a1 1 0 01-1.414 0z" clip-rule="evenodd"/>
            </svg>
            <span>{{ attachedFiles.length }} file(s) attached</span>
          </div>
          <div class="files-list">
            @for (file of attachedFiles; track file.name) {
              <div class="file-item">
                <span class="file-name">{{ file.name }}</span>
                <button
                  type="button"
                  class="remove-file"
                  (click)="removeFile(file)"
                  title="Remove file"
                >
                  <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
                  </svg>
                </button>
              </div>
            }
          </div>
        </div>
      }
    </div>
  `,
  styles: [`
    .message-input-container {
      @apply bg-white border border-gray-200 rounded-lg shadow-sm;
    }

    .mode-toggle-container {
      @apply p-3 border-b border-gray-200;
    }

    .mode-toggle {
      @apply flex bg-gray-100 rounded-lg p-1;
    }

    .mode-button {
      @apply flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 flex-1 justify-center;
    }

    .mode-button:hover:not(.disabled) {
      @apply bg-gray-200;
    }

    .mode-button.active {
      @apply bg-white text-blue-600 shadow-sm;
    }

    .mode-button.disabled {
      @apply opacity-50 cursor-not-allowed;
    }

    .mode-text {
      @apply text-sm;
    }

    .mode-description {
      @apply mt-2 text-xs text-gray-500;
    }

    .input-form {
      @apply p-3;
    }

    .input-container {
      @apply space-y-2;
    }

    .input-wrapper {
      @apply relative bg-gray-50 border border-gray-200 rounded-lg focus-within:bg-white focus-within:border-blue-500 transition-colors duration-200;
    }

    .input-wrapper.focused {
      @apply bg-white border-blue-500;
    }

    .attachment-button {
      @apply absolute left-3 top-1/2 transform -translate-y-1/2 p-2 text-gray-400 hover:text-gray-600 focus:outline-none focus:text-blue-600 transition-colors duration-200;
    }

    .attachment-button:disabled {
      @apply opacity-50 cursor-not-allowed;
    }

    .message-input {
      @apply w-full px-12 py-3 bg-transparent border-0 resize-none focus:outline-none focus:ring-0 text-gray-900 placeholder-gray-500;
      min-height: 24px;
      max-height: 200px;
      line-height: 1.5;
    }

    .message-input:disabled {
      @apply opacity-50 cursor-not-allowed;
    }

    .send-button {
      @apply absolute right-3 top-1/2 transform -translate-y-1/2 p-2 text-blue-600 hover:text-blue-700 focus:outline-none transition-colors duration-200;
    }

    .send-button.disabled {
      @apply text-gray-300 cursor-not-allowed;
    }

    .character-count {
      @apply text-xs text-gray-500 text-right;
    }

    .character-count.warning {
      @apply text-yellow-600;
    }

    .shortcuts-hint {
      @apply flex gap-4 text-xs text-gray-400;
    }

    .kbd {
      @apply px-1.5 py-0.5 bg-gray-100 border border-gray-300 rounded text-xs font-mono;
    }

    .attached-files {
      @apply px-3 pb-3 border-t border-gray-200;
    }

    .files-header {
      @apply flex items-center gap-2 text-sm font-medium text-gray-700 mb-2;
    }

    .files-list {
      @apply space-y-1;
    }

    .file-item {
      @apply flex items-center justify-between bg-gray-50 px-2 py-1 rounded text-sm;
    }

    .file-name {
      @apply text-gray-700 truncate flex-1;
    }

    .remove-file {
      @apply p-1 text-gray-400 hover:text-red-600 focus:outline-none transition-colors duration-200;
    }

    /* Mobile adjustments */
    @media (max-width: 640px) {
      .mode-text {
        @apply hidden;
      }

      .shortcuts-hint {
        @apply flex-col gap-1;
      }
    }
  `]
})
export class MessageInputComponent implements OnInit {
  @Input() disabled: boolean = false;
  @Input() loading: boolean = false;
  @Input() placeholder: string = 'Type your message...';
  @Input() showCharacterCount: boolean = false;
  @Input() maxCharacters: number = 4000;
  @Input() characterCountWarning: number = 3500;
  @Input() allowAttachments: boolean = true;

  @Output() sendMessage = new EventEmitter<{message: string, mode: 'planning' | 'fast', files?: File[]}>();
  @Output() attachmentClick = new EventEmitter<void>();

  message: string = '';
  currentMode: 'planning' | 'fast' = 'planning';
  isFocused: boolean = false;
  isMobile: boolean = false;
  attachedFiles: File[] = [];

  constructor(private configService: ConfigService) {}

  ngOnInit(): void {
    // Initialize mode from config service
    this.currentMode = this.configService.getMode();

    // Detect mobile
    this.isMobile = window.innerWidth <= 640;
  }

  get canSend(): boolean {
    return this.message.trim().length > 0 && !this.loading;
  }

  get modeDescription(): string {
    if (this.currentMode === 'planning') {
      return 'Create detailed execution plans before taking action';
    } else {
      return 'Execute tasks directly without detailed planning';
    }
  }

  setMode(mode: 'planning' | 'fast'): void {
    if (this.disabled || this.loading) return;
    this.currentMode = mode;
    this.configService.setMode(mode);
  }

  onSubmit(): void {
    if (this.canSend && !this.disabled) {
      const files = this.attachedFiles.length > 0 ? [...this.attachedFiles] : undefined;
      this.sendMessage.emit({
        message: this.message.trim(),
        mode: this.currentMode,
        files
      });
      this.message = '';
      this.attachedFiles = [];
      this.adjustHeight();
    }
  }

  onInputChange(): void {
    this.adjustHeight();
  }

  onKeyDown(event: KeyboardEvent): void {
    // Handle keyboard shortcuts
    if (event.key === 'Enter' && !event.shiftKey && !this.isMobile) {
      event.preventDefault();
      this.onSubmit();
    }
  }

  onAttachmentClick(): void {
    if (this.allowAttachments) {
      this.attachmentClick.emit();
    }
  }

  adjustHeight(): void {
    const textarea = event?.target as HTMLTextAreaElement;
    if (textarea) {
      // Reset height to auto to get correct scrollHeight
      textarea.style.height = 'auto';
      // Set height to scrollHeight, capped at max-height
      const newHeight = Math.min(textarea.scrollHeight, 200);
      textarea.style.height = `${newHeight}px`;
    }
  }

  addFiles(files: File[]): void {
    if (!this.allowAttachments) return;

    this.attachedFiles = [...this.attachedFiles, ...files];
  }

  removeFile(file: File): void {
    this.attachedFiles = this.attachedFiles.filter(f => f !== file);
  }

  clearFiles(): void {
    this.attachedFiles = [];
  }

  focus(): void {
    const textarea = document.querySelector('.message-input') as HTMLTextAreaElement;
    if (textarea) {
      textarea.focus();
    }
  }

  clear(): void {
    this.message = '';
    this.attachedFiles = [];
    this.adjustHeight();
  }
}