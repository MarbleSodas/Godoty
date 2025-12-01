import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { APP_CONFIG } from '../core/constants';
import { EnvironmentDetector, EnvironmentMode } from '../utils/environment';

export interface AgentConfig {
  projectPath: string;
  agentModel: string; // Universal model for all agents (renamed from planningModel)
  openRouterKey: string;
  status: 'idle' | 'working';
  showSettings: boolean;
  showTaskSidebar: boolean;
  godotVersion: string;
  godotConnected: boolean;
  connectionState: 'connected' | 'disconnected' | 'connecting' | 'error';
  mode: 'planning' | 'fast'; // Keep this toggle
  showFullPath: boolean; // NEW: Control whether to show full project path
}

export interface AvailableModel {
  id: string;
  name: string;
  provider: string;
  description?: string;
  pricing?: {
    prompt: number;
    completion: number;
  };
}

@Injectable({
  providedIn: 'root'
})
export class ConfigService {
  public config: BehaviorSubject<AgentConfig> = new BehaviorSubject<AgentConfig>({
    projectPath: localStorage.getItem('godoty_project_path') || '',
    agentModel: localStorage.getItem('godoty_agent_model') || localStorage.getItem('godoty_planning_model') || APP_CONFIG.DEFAULT_PLANNING_MODEL,
    openRouterKey: localStorage.getItem('godoty_openrouter_key') || '',
    status: 'idle',
    showSettings: false,
    showTaskSidebar: false,
    godotVersion: 'Unknown',
    godotConnected: false,
    connectionState: 'disconnected',
    mode: 'planning',
    showFullPath: false // Default to abbreviated view
  });

  // Dynamic model list loaded from backend
  public availableModels: BehaviorSubject<AvailableModel[]> = new BehaviorSubject<AvailableModel[]>([]);

  // API key status from backend
  public apiKeyStatus: BehaviorSubject<{
    hasKey: boolean;
    source: 'environment' | 'user_override' | 'none';
    needsUserInput: boolean;
  } | null> = new BehaviorSubject<{
    hasKey: boolean;
    source: 'environment' | 'user_override' | 'none';
    needsUserInput: boolean;
  } | null>(null);

  constructor() {
    this.loadConfigFromStorage();
    this.loadAvailableModels(); // Fetch models from backend on init
  }

  /**
   * Make backend API call using appropriate communication method
   */
  private async makeBackendCall<T>(endpoint: string, data?: any): Promise<T> {
    const environment = EnvironmentDetector.getCurrentMode();

    if (environment === EnvironmentMode.DESKTOP) {
      // Use PyWebView bridge for desktop mode
      const windowAny = window as any;

      // Remove leading slash for PyWebView API
      const apiEndpoint = endpoint.startsWith('/') ? endpoint.substring(1) : endpoint;

      if (!windowAny.pywebview?.api) {
        throw new Error('PyWebView API not available in desktop mode');
      }

      console.log(`[ConfigService] Using PyWebView bridge for ${apiEndpoint}`);

      if (apiEndpoint === 'config') {
        if (data) {
          return await windowAny.pywebview.api.updateConfig(data);
        } else {
          return await windowAny.pywebview.api.getConfig();
        }
      } else {
        throw new Error(`Unknown PyWebView endpoint: ${apiEndpoint}`);
      }
    } else {
      // Use HTTP requests for browser mode
      const url = `${APP_CONFIG.API_ENDPOINTS.CHAT}${endpoint}`;
      console.log(`[ConfigService] Using HTTP for ${url}`);

      const options: RequestInit = {
        method: data ? 'POST' : 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      };

      if (data) {
        options.body = JSON.stringify(data);
      }

      const response = await fetch(url, options);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    }
  }

  /**
   * Load configuration from localStorage
   */
  private loadConfigFromStorage(): void {
    const storedConfig = localStorage.getItem('godoty_agent_config');
    if (storedConfig) {
      try {
        const parsed = JSON.parse(storedConfig);

        // Migration: Handle rename from planningModel to agentModel
        if (parsed.planningModel && !parsed.agentModel) {
          parsed.agentModel = parsed.planningModel;
          delete parsed.planningModel;
        }

        // Ensure showFullPath has a default value
        if (parsed.showFullPath === undefined) {
          parsed.showFullPath = false;
        }

        this.config.next({ ...this.config.value, ...parsed });
      } catch (error) {
        console.error('[ConfigService] Failed to parse stored config:', error);
      }
    }
  }

  /**
   * Save configuration to localStorage
   */
  private saveConfigToStorage(): void {
    const currentConfig = this.config.value;
    localStorage.setItem('godoty_agent_config', JSON.stringify(currentConfig));
  }

  /**
   * Update a single configuration value
   */
  updateConfig<K extends keyof AgentConfig>(key: K, value: AgentConfig[K]): void {
    const currentConfig = this.config.value;
    const newConfig = { ...currentConfig, [key]: value };
    this.config.next(newConfig);
    this.saveConfigToStorage();

    // Also save specific items to individual localStorage keys for compatibility
    switch (key) {
      case 'projectPath':
        localStorage.setItem('godoty_project_path', value as string);
        break;
      case 'agentModel':
        localStorage.setItem('godoty_agent_model', value as string);
        break;
      case 'showFullPath':
        localStorage.setItem('godoty_show_full_path', String(value));
        break;
      case 'openRouterKey':
        if (value) {
          localStorage.setItem('godoty_openrouter_key', value as string);
        } else {
          localStorage.removeItem('godoty_openrouter_key');
        }
        break;
    }
  }

  /**
   * Update multiple configuration values
   */
  updateConfigValues(updates: Partial<AgentConfig>): void {
    const currentConfig = this.config.value;
    const newConfig = { ...currentConfig, ...updates };
    this.config.next(newConfig);
    this.saveConfigToStorage();

    // Update individual localStorage keys
    if (updates.projectPath !== undefined) {
      localStorage.setItem('godoty_project_path', updates.projectPath);
    }
    if (updates.agentModel !== undefined) {
      localStorage.setItem('godoty_agent_model', updates.agentModel);
    }
    if (updates.showFullPath !== undefined) {
      localStorage.setItem('godoty_show_full_path', String(updates.showFullPath));
    }
    if (updates.openRouterKey !== undefined) {
      if (updates.openRouterKey) {
        localStorage.setItem('godoty_openrouter_key', updates.openRouterKey);
      } else {
        localStorage.removeItem('godoty_openrouter_key');
      }
    }
  }

  /**
   * Get current configuration
   */
  getConfig(): AgentConfig {
    return this.config.value;
  }

  /**
   * Get current project path
   */
  getProjectPath(): string {
    return this.config.value.projectPath;
  }

  /**
   * Set project path
   */
  setProjectPath(path: string): void {
    this.updateConfig('projectPath', path);
  }

  /**
   * Get current agent model
   */
  getAgentModel(): string {
    return this.config.value.agentModel;
  }

  /**
   * Set agent model
   */
  setAgentModel(model: string): void {
    this.updateConfig('agentModel', model);
  }

  /**
   * Toggle show full path setting
   */
  toggleShowFullPath(): void {
    this.updateConfig('showFullPath', !this.config.value.showFullPath);
  }

  /**
   * Get show full path setting
   */
  getShowFullPath(): boolean {
    return this.config.value.showFullPath;
  }

  /**
   * Set show full path setting
   */
  setShowFullPath(show: boolean): void {
    this.updateConfig('showFullPath', show);
  }

  /**
   * Get OpenRouter API key
   */
  getOpenRouterKey(): string {
    return this.config.value.openRouterKey;
  }

  /**
   * Set OpenRouter API key
   */
  setOpenRouterKey(key: string): void {
    this.updateConfig('openRouterKey', key);
  }

  /**
   * Get current mode (planning or fast)
   */
  getMode(): 'planning' | 'fast' {
    return this.config.value.mode;
  }

  /**
   * Set mode
   */
  setMode(mode: 'planning' | 'fast'): void {
    this.updateConfig('mode', mode);
  }

  /**
   * Toggle mode
   */
  toggleMode(): void {
    const currentMode = this.config.value.mode;
    const newMode = currentMode === 'planning' ? 'fast' : 'planning';
    this.setMode(newMode);
  }

  /**
   * Get agent status
   */
  getStatus(): 'idle' | 'working' {
    return this.config.value.status;
  }

  /**
   * Set agent status
   */
  setStatus(status: 'idle' | 'working'): void {
    this.updateConfig('status', status);
  }

  /**
   * Toggle settings visibility
   */
  toggleSettings(): void {
    this.updateConfig('showSettings', !this.config.value.showSettings);
  }

  /**
   * Show settings
   */
  showSettingsPanel(): void {
    this.updateConfig('showSettings', true);
  }

  /**
   * Hide settings
   */
  hideSettingsPanel(): void {
    this.updateConfig('showSettings', false);
  }

  /**
   * Toggle task sidebar visibility
   */
  toggleTaskSidebar(): void {
    this.updateConfig('showTaskSidebar', !this.config.value.showTaskSidebar);
  }

  /**
   * Show task sidebar
   */
  showTaskSidebarPanel(): void {
    this.updateConfig('showTaskSidebar', true);
  }

  /**
   * Hide task sidebar
   */
  hideTaskSidebarPanel(): void {
    this.updateConfig('showTaskSidebar', false);
  }

  /**
   * Update Godot connection status
   */
  setGodotConnection(connected: boolean, version: string = 'Unknown'): void {
    this.updateConfigValues({
      godotConnected: connected,
      godotVersion: version,
      connectionState: connected ? 'connected' : 'disconnected'
    });
  }

  /**
   * Set Godot connection state
   */
  setConnectionState(state: 'connected' | 'disconnected' | 'connecting' | 'error'): void {
    this.updateConfig('connectionState', state);
    this.updateConfig('godotConnected', state === 'connected');
  }

  /**
   * Check if configuration is valid
   */
  isConfigValid(): boolean {
    const config = this.config.value;
    return !!(
      config.projectPath.trim() &&
      config.agentModel.trim() &&
      config.openRouterKey.trim()
    );
  }

  /**
   * Check if OpenRouter API key is set
   */
  hasOpenRouterKey(): boolean {
    return !!this.config.value.openRouterKey.trim();
  }

  /**
   * Check if project path is set
   */
  hasProjectPath(): boolean {
    return !!this.config.value.projectPath.trim();
  }

  /**
   * Get available models
   */
  getAvailableModels(): AvailableModel[] {
    return this.availableModels.value;
  }

  /**
   * Get model by ID
   */
  getModelById(modelId: string): AvailableModel | undefined {
    return this.availableModels.value.find(model => model.id === modelId);
  }

  /**
   * Load available models from backend
   */
  private async loadAvailableModels(): Promise<void> {
    let retryCount = 0;
    const maxRetries = 2;

    while (retryCount <= maxRetries) {
      try {
        const data = await this.makeBackendCall('/config');

        if (data && typeof data === 'object' && 'available_models' in data && Array.isArray((data as any).available_models)) {
          this.availableModels.next((data as any).available_models);
        }

        // Update API key status - this is critical for chat functionality
        if (data && typeof data === 'object' && 'has_api_key' in data && (data as any).has_api_key !== undefined) {
          this.apiKeyStatus.next({
            hasKey: (data as any).has_api_key,
            source: (data as any).api_key_source || 'none',
            needsUserInput: !(data as any).has_api_key
          });

          // Log only critical status for desktop mode
          if (EnvironmentDetector.isDesktopMode() && !(data as any).has_api_key) {
            console.error('[ConfigService] Critical: API key validation failed in desktop mode');
          }
          return; // Success - exit the retry loop
        } else {
          throw new Error('API key status not returned from backend');
        }
      } catch (error) {
        retryCount++;
        console.error(`[ConfigService] Load attempt ${retryCount} failed:`, error);

        if (retryCount > maxRetries) {
          console.error('[ConfigService] All retries exhausted, using fallback configuration');
          // Fallback: Use minimal default list
          this.availableModels.next([
            { id: 'x-ai/grok-4.1-fast', name: 'Grok 4.1 Fast', provider: 'xAI' },
            { id: 'anthropic/claude-sonnet-4.5', name: 'Sonnet 4.5', provider: 'Anthropic' }
          ]);
          this.apiKeyStatus.next({
            hasKey: false,
            source: 'none',
            needsUserInput: true
          });
        } else {
          // Brief delay before retry
          await new Promise(resolve => setTimeout(resolve, 1000 * retryCount));
        }
      }
    }
  }

  /**
   * Fetch complete backend configuration
   */
  async fetchBackendConfig(): Promise<any> {
    return await this.makeBackendCall('/config');
  }

  /**
   * Sync configuration changes to backend
   */
  async syncConfigToBackend(model?: string, apiKey?: string): Promise<void> {
    try {
      const body: any = {};

      if (model) {
        body.model = model;
      }

      if (apiKey !== undefined) {
        body.api_key = apiKey;
      }

      const result = await this.makeBackendCall('/config', body);
      console.log('[ConfigService] Config synced to backend:', result);

      // Refresh API key status after sync
      await this.loadAvailableModels();
    } catch (error) {
      console.error('[ConfigService] Failed to sync config to backend:', error);
      throw error;
    }
  }

  /**
   * Get API key status from backend
   */
  async refreshApiKeyStatus(): Promise<void> {
    try {
      const config = await this.fetchBackendConfig();

      this.apiKeyStatus.next({
        hasKey: config.has_api_key || false,
        source: config.api_key_source || 'none',
        needsUserInput: !config.has_api_key
      });
    } catch (error) {
      console.error('[ConfigService] Failed to refresh API key status:', error);
      this.apiKeyStatus.next({
        hasKey: false,
        source: 'none',
        needsUserInput: true
      });
    }
  }

  /**
   * Reset configuration to defaults
   */
  resetToDefaults(): void {
    this.config.next({
      projectPath: '',
      agentModel: APP_CONFIG.DEFAULT_PLANNING_MODEL,
      openRouterKey: '',
      status: 'idle',
      showSettings: false,
      showTaskSidebar: false,
      godotVersion: 'Unknown',
      godotConnected: false,
      connectionState: 'disconnected',
      mode: 'planning',
      showFullPath: false
    });

    // Clear localStorage
    localStorage.removeItem('godoty_project_path');
    localStorage.removeItem('godoty_agent_model');
    localStorage.removeItem('godoty_planning_model'); // Clean up old key
    localStorage.removeItem('godoty_show_full_path');
    localStorage.removeItem('godoty_openrouter_key');
    localStorage.removeItem('godoty_agent_config');
  }

  /**
   * Export configuration
   */
  exportConfig(): string {
    return JSON.stringify(this.config.value, null, 2);
  }

  /**
   * Import configuration
   */
  importConfig(configJson: string): boolean {
    try {
      const importedConfig = JSON.parse(configJson);
      this.config.next({ ...this.config.value, ...importedConfig });
      this.saveConfigToStorage();
      return true;
    } catch (error) {
      console.error('[ConfigService] Failed to import config:', error);
      return false;
    }
  }
}