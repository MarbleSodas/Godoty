import { Component, Input, Output, EventEmitter, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ConfigService } from '../../services/config.service';
import { MetricsService } from '../../services/metrics.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="settings-panel">
      <div class="settings-header">
        <h3 class="settings-title">
          <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.942 2.106 0 .845.411 1.511 1.003 1.917-.704-.03-1.397.264-1.856.835-.575.72-.667 1.713-.27 2.52a1.532 1.532 0 01-.948 2.286c-1.56.38-1.56 2.6 0 2.98a1.532 1.532 0 01.948 2.286c-.397.807-.305 1.8.27 2.52.459.571 1.152.865 1.856.835-.592.406-1.003 1.072-1.003 1.917 0 1.372 1.57 2.942 2.942 2.106a1.532 1.532 0 012.286.948c.38 1.56 2.6 1.56 2.98 0a1.532 1.532 0 012.286-.948c1.372.836 2.942-.734 2.942-2.106 0-.845-.411-1.511-1.003-1.917.704.03 1.397-.264 1.856-.835.575-.72.667-1.713.27-2.52a1.532 1.532 0 01.948-2.286c1.56-.38 1.56-2.6 0-2.98a1.532 1.532 0 01-.948-2.286c.397-.807.305-1.8-.27-2.52-.459-.571-1.152-.865-1.856-.835.592-.406 1.003-1.072 1.003-1.917 0-1.372-1.57-2.942-2.942-2.106a1.532 1.532 0 01-2.286-.948zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"/>
          </svg>
          Settings
        </h3>
        <button
          class="close-button"
          (click)="onClose()"
          title="Close settings"
        >
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
          </svg>
        </button>
      </div>

      <div class="settings-content">
        <!-- Model Configuration -->
        <div class="settings-section">
          <h4 class="section-title">Model Configuration</h4>
          <div class="form-group">
            <label for="agent-model" class="form-label">Agent Model</label>
            <select
              id="agent-model"
              [(ngModel)]="config.agentModel"
              (ngModelChange)="onConfigChange()"
              class="form-select"
            >
              <option value="">Select a model</option>
              @for (model of availableModels; track model) {
                <option [value]="model">{{ model }}</option>
              }
            </select>
            <p class="help-text">This model will be used for all agents in the workflow</p>
          </div>
        </div>

        <!-- API Configuration -->
        <div class="settings-section">
          <h4 class="section-title">API Configuration</h4>
          <div class="form-group">
            <label for="api-key" class="form-label">OpenRouter API Key</label>
            <input
              id="api-key"
              type="password"
              [(ngModel)]="config.openRouterKey"
              (ngModelChange)="onConfigChange()"
              placeholder="Enter your OpenRouter API key"
              class="form-input"
            />
            @if (apiKeyStatus) {
              <div class="text-xs mt-2">
                @if (apiKeyStatus.hasKey && apiKeyStatus.source === 'environment') {
                  <span class="text-green-400 flex items-center gap-1">
                    <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                      <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                    </svg>
                    Using backend API key from environment
                  </span>
                } @else if (apiKeyStatus.hasKey && apiKeyStatus.source === 'user_override') {
                  <span class="text-blue-400 flex items-center gap-1">
                    <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                      <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                    </svg>
                    Using your custom API key
                  </span>
                } @else {
                  <span class="text-yellow-400 flex items-center gap-1">
                    <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                      <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
                    </svg>
                    No API key configured - please provide one
                  </span>
                }
              </div>
            }
          </div>
        </div>

  
        <!-- Actions -->
        <div class="settings-actions">
          <button
            class="action-button secondary"
            (click)="onResetConfig()"
            [disabled]="isResetting"
          >
            @if (isResetting) {
              <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Resetting...
            } @else {
              Reset to Defaults
            }
          </button>

          <button
            class="action-button primary"
            (click)="onSaveConfig()"
            [disabled]="isSaving || !hasChanges"
          >
            @if (isSaving) {
              <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Saving...
            } @else {
              Save Changes
            }
          </button>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .settings-panel {
      @apply bg-[#1a1e29] border border-[#2d3546] rounded-xl shadow-2xl p-6 max-w-2xl w-full mx-auto;
    }

    .settings-header {
      @apply flex items-center justify-between mb-6 pb-4 border-b border-[#2d3546];
    }

    .settings-title {
      @apply flex items-center gap-3 text-xl font-semibold text-gray-100;
    }

    .close-button {
      @apply p-2 text-gray-400 hover:text-gray-200 hover:bg-[#2d3546] rounded-lg transition-all duration-200;
    }

    .close-button:hover {
      @apply scale-110;
    }

    .settings-content {
      @apply space-y-6;
    }

    .settings-section {
      @apply space-y-4;
    }

    .section-title {
      @apply text-sm font-semibold text-[#478cbf] uppercase tracking-wider mb-3;
    }

    .form-group {
      @apply space-y-2;
    }

    .form-label {
      @apply block text-sm font-medium text-gray-300 mb-2;
    }

    .help-text {
      @apply text-xs text-gray-500 mt-2;
    }

    .form-input, .form-select {
      @apply w-full px-4 py-2.5 bg-[#1a1e29] border border-[#3b4458] rounded-lg text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-[#478cbf] focus:border-transparent transition-all duration-200;
    }

    .form-input:focus, .form-select:focus {
      @apply border-[#478cbf];
    }

    .form-checkbox {
      @apply h-4 w-4 bg-[#1a1e29] border-[#3b4458] rounded text-[#478cbf] focus:ring-[#478cbf] focus:ring-2 transition-colors;
    }

    .form-checkbox:checked {
      @apply bg-[#478cbf] border-[#478cbf];
    }

    .settings-actions {
      @apply flex gap-3 pt-6 border-t border-[#2d3546];
    }

    .action-button {
      @apply flex items-center justify-center gap-2 px-6 py-2.5 rounded-lg font-medium transition-all duration-200;
    }

    .action-button.primary {
      @apply bg-[#478cbf] text-white hover:bg-[#367fa9] disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-[#478cbf]/20 hover:shadow-xl hover:shadow-[#478cbf]/30;
    }

    .action-button.secondary {
      @apply bg-transparent text-gray-300 hover:bg-[#2d3546] disabled:opacity-50 disabled:cursor-not-allowed border border-[#3b4458] hover:border-[#478cbf]/50;
    }

    /* Canvas-style animations */
    .settings-panel {
      animation: fadeInUp 0.3s ease-out;
    }

    .form-input, .form-select {
      @apply hover:border-[#478cbf]/50;
    }

    /* Compact mode */
    @media (max-width: 640px) {
      .settings-panel {
        @apply p-4 mx-4;
      }

      .settings-actions {
        @apply flex-col gap-2;
      }

      .action-button {
        @apply justify-center;
      }
    }
  `]
})
export class SettingsComponent implements OnChanges {
  @Input() isVisible: boolean = false;
  @Output() close = new EventEmitter<void>();
  @Output() configChange = new EventEmitter<any>();

  config: any = {};
  originalConfig: any = {};
  availableModels: string[] = [];
  apiKeyStatus: { hasKey: boolean; source: string; needsUserInput: boolean } | null = null;
  isSaving: boolean = false;
  isResetting: boolean = false;

  constructor(
    private configService: ConfigService,
    private metricsService: MetricsService
  ) {
    this.loadConfig();
    this.loadAvailableModels();
    this.loadApiKeyStatus();
  }

  ngOnChanges(changes: SimpleChanges): void {
    // Refresh API key status when modal opens
    if (changes['isVisible'] && changes['isVisible'].currentValue === true) {
      this.refreshApiKeyStatus();
    }
  }

  get hasChanges(): boolean {
    return JSON.stringify(this.config) !== JSON.stringify(this.originalConfig);
  }

  private loadConfig(): void {
    this.config = { ...this.configService.getConfig() };
    this.originalConfig = { ...this.config };
  }

  private loadAvailableModels(): void {
    // Subscribe to available models from config service
    this.configService.availableModels.subscribe(models => {
      this.availableModels = models.map(model => model.id);
    });
  }

  private loadApiKeyStatus(): void {
    // Subscribe to API key status from config service
    this.configService.apiKeyStatus.subscribe(status => {
      this.apiKeyStatus = status;
    });
  }

  private async refreshApiKeyStatus(): Promise<void> {
    // Refresh API key status from backend
    try {
      await this.configService.refreshApiKeyStatus();
    } catch (error) {
      console.error('Failed to refresh API key status:', error);
    }
  }

  onConfigChange(): void {
    this.configChange.emit(this.config);
  }

  onClose(): void {
    this.close.emit();
  }

  async onSaveConfig(): Promise<void> {
    if (this.isSaving || !this.hasChanges) return;

    this.isSaving = true;
    try {
      // Update local config
      this.configService.updateConfigValues(this.config);

      // Sync to backend
      await this.configService.syncConfigToBackend(
        this.config.agentModel,
        this.config.openRouterKey
      );

      this.originalConfig = { ...this.config };
      this.isSaving = false;
      this.onClose();
    } catch (error) {
      console.error('Failed to save config:', error);
      this.isSaving = false;
      // TODO: Show error message to user
    }
  }

  onResetConfig(): void {
    if (this.isResetting) return;

    this.isResetting = true;
    try {
      this.configService.resetToDefaults();
      this.loadConfig();
      this.isResetting = false;
      this.onConfigChange();
    } catch (error) {
      console.error('Failed to reset config:', error);
      this.isResetting = false;
    }
  }
}