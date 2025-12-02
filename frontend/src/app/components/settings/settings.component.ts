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
          <div class="flex items-center justify-between mb-3">
            <h4 class="section-title">Model Configuration</h4>
            <button
              (click)="refreshModelList()"
              [disabled]="isLoadingModels"
              class="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
              title="Refresh model list"
            >
              @if (isLoadingModels) {
                <svg class="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Refreshing...
              } @else {
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
                </svg>
                Refresh
              }
            </button>
          </div>

          <div class="form-group">
            <label for="agent-model" class="form-label">Agent Model</label>
            <select
              id="agent-model"
              [(ngModel)]="config.agentModel"
              (ngModelChange)="onModelChange($event)"
              [disabled]="isLoadingModels"
              class="form-select"
            >
              <option value="">Select a model</option>
              @for (model of availableModels; track model.id) {
                <option [value]="model.id">{{ model.name }}</option>
              }
            </select>

            @if (config.agentModel) {
              <div class="text-xs text-gray-400 mt-1">
                {{ getModelDescription(config.agentModel) }}
              </div>
            }

            @if (modelLoadError) {
              <div class="text-xs text-yellow-400 mt-1">
                ⚠️ {{ modelLoadError }}
              </div>
            }

            <p class="help-text">This model will be used for all agents in the workflow</p>
          </div>
        </div>

        <!-- API Configuration -->
        <div class="settings-section">
          <h4 class="section-title">API Configuration</h4>
          <div class="form-group">
            <!-- Show API key input only when backend doesn't have a key OR user override is allowed -->
            @if (!apiKeyStatus?.hasBackendKey || (apiKeyStatus?.allowUserOverride && showCustomKeyInput)) {
              <label for="api-key" class="form-label">
                @if (apiKeyStatus?.hasBackendKey) {
                  Custom OpenRouter API Key (Override)
                } @else {
                  OpenRouter API Key
                }
              </label>
              <input
                id="api-key"
                type="password"
                [(ngModel)]="config.openRouterKey"
                (ngModelChange)="onConfigChange()"
                placeholder="Enter your OpenRouter API key"
                class="form-input"
              />
            }

            <!-- Backend key status display -->
            @if (apiKeyStatus?.hasBackendKey) {
              <div class="text-xs mt-2 p-2 bg-green-900 bg-opacity-20 border border-green-700 rounded">
                <div class="text-green-400 flex items-center gap-1 mb-1">
                  <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                  </svg>
                  Using backend API key
                </div>
                <div class="text-gray-400 text-xs">
                  Key: {{ apiKeyStatus?.apiKeyPrefix || 'sk-or-v1-***' }}
                  @if (apiKeyStatus?.allowUserOverride) {
                    <div class="mt-1">
                      <button
                        (click)="toggleCustomKeyInput()"
                        class="text-blue-400 hover:text-blue-300 underline text-xs"
                      >
                        Use Custom Key Instead
                      </button>
                    </div>
                  }
                </div>
              </div>
            }

            <!-- User override status -->
            @if (apiKeyStatus?.source === 'user_override') {
              <div class="text-xs mt-2 p-2 bg-blue-900 bg-opacity-20 border border-blue-700 rounded">
                <div class="text-blue-400 flex items-center gap-1 mb-1">
                  <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                  </svg>
                  Using custom API key
                </div>
                @if (apiKeyStatus?.hasBackendKey) {
                  <div class="text-gray-400 text-xs">
                    <button
                      (click)="revertToBackendKey()"
                      class="text-green-400 hover:text-green-300 underline text-xs"
                    >
                      Revert to Backend Key
                    </button>
                  </div>
                }
              </div>
            }

            <!-- No API key configured -->
            @if (apiKeyStatus && !apiKeyStatus.hasKey) {
              <div class="text-xs mt-2">
                <span class="text-yellow-400 flex items-center gap-1">
                  <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
                  </svg>
                  Please configure OpenRouter API key in settings or .env file
                </span>
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
  availableModels: any[] = [];
  apiKeyStatus: {
    hasKey: boolean;
    source: 'environment' | 'user_override' | 'none';
    needsUserInput: boolean;
    hasBackendKey: boolean;
    apiKeyPrefix?: string;
    allowUserOverride: boolean;
  } | null = null;
  isSaving: boolean = false;
  isResetting: boolean = false;
  showCustomKeyInput: boolean = false;
  isLoadingModels: boolean = false;
  modelLoadError: string | null = null;

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
      this.availableModels = models;
    });

    // Load fresh models from backend
    this.refreshModels();
  }

  private async refreshModels(): Promise<void> {
    this.isLoadingModels = true;
    this.modelLoadError = null;

    try {
      const models = await this.configService.fetchAvailableModels();
      this.configService.availableModels.next(models);
      console.log(`[SettingsComponent] Loaded ${models.length} models from backend`);
    } catch (error) {
      console.error('[SettingsComponent] Failed to load models:', error);
      this.modelLoadError = 'Failed to load models from backend';

      // Fallback to existing models
      const fallbackModels = this.configService.getFallbackModels();
      this.configService.availableModels.next(fallbackModels);
    } finally {
      this.isLoadingModels = false;
    }
  }

  private loadApiKeyStatus(): void {
    // Subscribe to API key status from config service
    this.configService.apiKeyStatus.subscribe(status => {
      this.apiKeyStatus = status;
    });
  }

  private async refreshApiKeyStatus(): Promise<void> {
    // Refresh API key status from backend using dedicated endpoint
    try {
      const apiKeyStatus = await this.configService.checkApiKeyStatus();
      // Update the service's BehaviorSubject with the fresh status
      this.configService.apiKeyStatus.next(apiKeyStatus);
    } catch (error) {
      console.error('Failed to refresh API key status:', error);
      // Fallback to connection status check
      try {
        await this.configService.checkConnectionStatus();
      } catch (fallbackError) {
        console.error('Fallback API key status check also failed:', fallbackError);
      }
    }
  }

  toggleCustomKeyInput(): void {
    this.showCustomKeyInput = !this.showCustomKeyInput;
  }

  revertToBackendKey(): void {
    // Clear user API key and revert to backend key
    this.configService.clearUserApiKey();
    this.showCustomKeyInput = false;

    // Update config to remove the API key from the form
    this.config = {
      ...this.config,
      openRouterKey: ''
    };
  }

  onConfigChange(): void {
    // Handle API key changes
    if (this.config.openRouterKey && this.apiKeyStatus?.hasBackendKey) {
      // User is overriding backend key
      this.configService.setUserApiKey(this.config.openRouterKey);
    }

    this.configChange.emit(this.config);
  }

  async onModelChange(newModelId: string): Promise<void> {
    this.config.agentModel = newModelId;
    await this.configService.setAgentModel(newModelId);

    // Optionally update backend default
    if (newModelId) {
      try {
        const success = await this.configService.setDefaultModel(newModelId);
        if (success) {
          console.log(`[SettingsComponent] Default model set to: ${newModelId}`);
        } else {
          console.warn(`[SettingsComponent] Failed to set default model: ${newModelId}`);
        }
      } catch (error) {
        console.error('[SettingsComponent] Error setting default model:', error);
      }
    }

    this.onConfigChange();
  }

  async refreshModelList(): Promise<void> {
    try {
      // Clear cache first to force fresh fetch
      await this.configService.clearModelCache();
      await this.refreshModels();
    } catch (error) {
      console.error('[SettingsComponent] Failed to refresh model list:', error);
    }
  }

  getModelDescription(modelId: string): string {
    const model = this.availableModels.find(m => m.id === modelId);
    if (model?.description) {
      return model.description;
    }

    if (model?.contextLength) {
      return `Context: ${model.contextLength.toLocaleString()} tokens`;
    }

    return '';
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