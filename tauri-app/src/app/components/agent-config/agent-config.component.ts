import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { invoke } from '@tauri-apps/api/core';
import { ProjectIndexerStatusComponent } from '../project-indexer-status/project-indexer-status.component';
import { IndexingStatus, IndexingStatusResponse } from '../../models/indexing-status.model';

import {
  AgentConfigService,
  AgentLlmConfig,
  ApiKeyStore,
  LlmProvider,
  AgentType,
  ModelSelection,
  LlmPreset
} from '../../services/agent-config.service';

@Component({
  selector: 'app-agent-config',
  standalone: true,
  imports: [CommonModule, FormsModule, ProjectIndexerStatusComponent],
  templateUrl: './agent-config.component.html',
  styleUrls: ['./agent-config.component.css']
})
export class AgentConfigComponent implements OnInit {
  config: AgentLlmConfig | null = null;
  apiKeys: ApiKeyStore | null = null;
  availableModels: Record<LlmProvider, string[]> = {} as Record<LlmProvider, string[]>;

  // Expose enums to template
  LlmProvider = LlmProvider;
  AgentType = AgentType;

  // Get enum values as arrays for iteration
  providers = Object.values(LlmProvider);
  agentTypes = Object.values(AgentType);

  loading = true;
  saving = false;
  error: string | null = null;
  successMessage: string | null = null;

  // Presets
  presets: LlmPreset[] = [];
  selectedPresetKey: LlmPreset['key'] | '' = '';

  // Path configuration state
  projectPath: string = '';
  indexingStatus: IndexingStatus | null = null;
  godotExecPath: string = '';
  editingProjectPath = false;
  tempProjectPath: string = '';
  editingExecPath = false;
  tempExecPath: string = '';

  constructor(private agentConfigService: AgentConfigService, private router: Router) {}

  async ngOnInit() {
    // Load presets immediately (static)
    this.presets = this.agentConfigService.getPresets();

    await Promise.all([
      this.loadConfiguration(),
      this.loadPathStatus()
    ]);
  }

  async loadConfiguration() {
    try {
      this.loading = true;
      this.error = null;

      // Load configuration and API keys in parallel
      const [config, apiKeys, availableModels] = await Promise.all([
        this.agentConfigService.getAgentLlmConfig(),
        this.agentConfigService.getApiKeys(),
        this.agentConfigService.getAvailableModels()
      ]);

      this.config = config;
      this.apiKeys = apiKeys;
      this.availableModels = availableModels;

      // Hydrate any missing/invalid defaults to ensure selects show values
      this.ensureConfigHydrated();
    } catch (err) {
      this.error = `Failed to load configuration: ${err}`;
      console.error('Error loading configuration:', err);

      // Initialize with defaults on error
      this.config = this.agentConfigService.getDefaultConfig();
      this.apiKeys = this.agentConfigService.getEmptyApiKeyStore();

      // Ensure hydration even when falling back
      this.ensureConfigHydrated();
    } finally {
      this.loading = false;
    }
  }

  async saveConfiguration() {
    if (!this.config || !this.apiKeys) {
      return;
    }

    // Basic key validation for common mistakes (backend also validates)
    const invalidProvider = this.providers.find(p => {
      const key = this.apiKeys!.keys[p as LlmProvider] || '';
      const trimmed = key.trim();
      if (!trimmed) return false; // allow empty (user may not use provider)
      if (/\s/.test(trimmed)) return true;
      if (p === LlmProvider.Claude && trimmed.length < 20) return true;
      return false;
    });
    if (invalidProvider) {
      const displayName = this.getProviderDisplayName(invalidProvider as LlmProvider);
      this.error = `Invalid API key format for provider: ${displayName}`;
      return;
    }

    try {
      this.saving = true;
      this.error = null;
      this.successMessage = null;

      // Save both configuration and API keys
      await Promise.all([
        this.agentConfigService.saveAgentLlmConfig(this.config),
        this.agentConfigService.saveApiKeys(this.apiKeys)
      ]);

      this.successMessage = 'Configuration saved successfully!';
      setTimeout(() => this.successMessage = null, 3000);
    } catch (err) {
      this.error = `Failed to save configuration: ${err}`;
      console.error('Error saving configuration:', err);
    } finally {
      this.saving = false;
    }
  }

  async resetToDefaults() {
    if (confirm('Are you sure you want to reset to default configuration? This will not affect your API keys.')) {
      try {
        this.saving = true;
        this.error = null;
        this.successMessage = null;

        // Get default configuration (create a deep copy to ensure proper binding)
        const defaultConfig = this.agentConfigService.getDefaultConfig();
        const cloned: AgentLlmConfig = JSON.parse(JSON.stringify(defaultConfig));
        this.config = cloned;

        // Save it immediately
        await this.agentConfigService.saveAgentLlmConfig(cloned);

        this.successMessage = 'Configuration reset to defaults and saved successfully!';
        setTimeout(() => this.successMessage = null, 3000);
      } catch (err) {
        this.error = `Failed to reset configuration: ${err}`;
        console.error('Error resetting configuration:', err);
      } finally {
        this.saving = false;
      }
    }
  }
  goBack() {
    this.router.navigateByUrl('/');
  }

  async loadPathStatus() {
    try {
      const status = await invoke<IndexingStatusResponse>('get_indexing_status');
      this.projectPath = status.projectPath || '';
      this.indexingStatus = status.status;
    } catch (err) {
      console.error('Failed to load indexing status', err);
    }

    try {
      const exec = await invoke<string>('get_godot_executable_for_current_project');
      this.godotExecPath = exec || '';
    } catch {
      this.godotExecPath = '';
    }

    this.tempProjectPath = this.projectPath || '';
    this.tempExecPath = this.godotExecPath || '';
  }

  async saveProjectPath() {
    try {
      await invoke('set_godot_project_path', { path: this.tempProjectPath });
      this.projectPath = this.tempProjectPath;
      this.editingProjectPath = false;
      await this.loadPathStatus();
    } catch (err) {
      console.error('Failed to save project path', err);
    }
  }

  cancelProjectPath() {
    this.tempProjectPath = this.projectPath || '';
    this.editingProjectPath = false;
  }

  async saveExecPath() {
    if (!this.projectPath) return;
    try {
      await invoke('set_godot_executable_path', {
        projectPath: this.projectPath,
        executablePath: this.tempExecPath
      });
      this.godotExecPath = this.tempExecPath;
      this.editingExecPath = false;
    } catch (err) {
      console.error('Failed to save executable path', err);
    }
  }

  async removeExecPath() {
    if (!this.projectPath) return;
    try {
      await invoke('remove_godot_executable_path', {
        projectPath: this.projectPath
      });
      this.godotExecPath = '';
    } catch (err) {
      console.error('Failed to remove executable path', err);
    }
  }

  hasApiKey(provider: LlmProvider): boolean {
    const key = (this.apiKeys?.keys[provider] || '').trim();
    if (!key) return false;
    if (/\s/.test(key)) return false;
    if (provider === LlmProvider.Claude && key.length < 20) return false;
    return true;
  }

  getProviderDisplayName(provider: LlmProvider): string {
    const displayNames: Record<LlmProvider, string> = {
      [LlmProvider.OpenRouter]: 'OpenRouter',
      [LlmProvider.Claude]: 'Claude'
    };
    return displayNames[provider] || provider;
  }

  displayProviderLabel(provider: LlmProvider): string {
    const displayName = this.getProviderDisplayName(provider);
    return this.hasApiKey(provider) ? displayName : `${displayName} (no key)`;
  }

  isPresetEnabled(key: LlmPreset['key']): boolean {
    const preset = this.presets.find(p => p.key === key);
    if (!preset) return false;
    return preset.requiredProvider ? this.hasApiKey(preset.requiredProvider) : true;
  }

  applySelectedPreset() {
    if (!this.selectedPresetKey) return;
    this.applyPresetByKey(this.selectedPresetKey);
  }

  applyPresetByKey(key: LlmPreset['key']) {
    const preset = this.presets.find(p => p.key === key);
    if (!preset) return;
    if (preset.requiredProvider && !this.hasApiKey(preset.requiredProvider)) return;

    // Deep clone to avoid binding issues
    this.config = JSON.parse(JSON.stringify(preset.config));
    this.ensureConfigHydrated();
    this.successMessage = `${preset.label} applied. Remember to Save to persist.`;
    setTimeout(() => this.successMessage = null, 3000);
  }

  getCurrentPresetLabel(): string {
    if (!this.config) return 'Customized';
    for (const p of this.presets) {
      if (this.configsEqual(this.config, p.config)) return p.label;
    }
    return 'Customized';
  }

  private configsEqual(a: AgentLlmConfig, b: AgentLlmConfig): boolean {
    const types = this.agentTypes as AgentType[];
    return types.every(t => {
      const x = a.agents[t];
      const y = b.agents[t];
      return x && y && x.provider === y.provider && x.model_name === y.model_name;
    });
  }

  getModelsForProvider(provider: LlmProvider): string[] {
    if (!this.hasApiKey(provider)) return [];
    return this.availableModels[provider] || [];
  }

  getAgentConfig(agentType: AgentType): ModelSelection | undefined {
    return this.config?.agents[agentType];
  }

  updateAgentProvider(agentType: AgentType, provider: LlmProvider) {
    if (!this.config) return;

    const models = this.getModelsForProvider(provider);
    const defaultModel = models.length > 0 ? models[0] : '';

    this.config.agents[agentType] = {
      provider,
      model_name: defaultModel
    };
  }

  updateAgentModel(agentType: AgentType, modelName: string) {
    if (!this.config) return;

    this.config.agents[agentType].model_name = modelName;
  }

  getApiKey(provider: LlmProvider): string {
    return this.apiKeys?.keys[provider] || '';
  }

  setApiKey(provider: LlmProvider, key: string) {
    if (!this.apiKeys) return;

    this.apiKeys.keys[provider] = key;
  }

  getAgentTypeLabel(agentType: AgentType): string {
    const labels: Record<AgentType, string> = {
      [AgentType.Planner]: 'Planner Agent',
      [AgentType.CodeGenerator]: 'Code Generator Agent',
      [AgentType.Vision]: 'Vision Agent',
      [AgentType.Researcher]: 'Researcher Agent',
      [AgentType.Validator]: 'Validator Agent',
      [AgentType.Documentation]: 'Documentation Agent'
    };
    return labels[agentType];
  }

  // Ensure each agent has a valid provider and model populated
  private ensureConfigHydrated() {
    if (!this.config) return;

    for (const agent of this.agentTypes) {
      const current = this.config.agents[agent];
      const provider: LlmProvider = current?.provider && this.providers.includes(current.provider)
        ? current.provider
        : this.LlmProvider.OpenRouter;

      const models = this.getModelsForProvider(provider);
      const modelName = current?.model_name?.trim();
      const validModel = modelName && models.includes(modelName) ? modelName : (models[0] || '');

      if (!current || current.provider !== provider || current.model_name !== validModel) {
        this.config.agents[agent] = {
          provider,
          model_name: validModel
        };
      }
    }
  }
}

