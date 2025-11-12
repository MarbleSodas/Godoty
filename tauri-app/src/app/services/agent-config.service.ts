import { Injectable } from '@angular/core';
import { invoke } from '@tauri-apps/api/core';

export enum LlmProvider {
  OpenRouter = 'OpenRouter'
}

export enum AgentType {
  Orchestrator = 'Orchestrator',
  Researcher = 'Researcher'
}

export interface ModelSelection {
  provider: LlmProvider;
  model_name: string;
}

export interface AgentLlmConfig {
  agents: Record<AgentType, ModelSelection>;
}

export interface ApiKeyStore {
  keys: Record<LlmProvider, string>;
}


export interface LlmPreset {
  key: 'Mixed' | 'ZaiGlm';
  label: string;
  // If set, this preset should only be enabled when this provider has a configured API key
  requiredProvider: LlmProvider | null;
  config: AgentLlmConfig;
}

@Injectable({
  providedIn: 'root'
})
export class AgentConfigService {

  constructor() { }

  /**
   * Get the current agent LLM configuration
   */
  async getAgentLlmConfig(): Promise<AgentLlmConfig> {
    return await invoke<AgentLlmConfig>('get_agent_llm_config');
  }

  /**
   * Save agent LLM configuration
   */
  async saveAgentLlmConfig(config: AgentLlmConfig): Promise<void> {
    await invoke('save_agent_llm_config', { config });
  }

  /**
   * Get API keys
   */
  async getApiKeys(): Promise<ApiKeyStore> {
    return await invoke<ApiKeyStore>('get_api_keys');
  }

  /**
   * Save API keys
   */
  async saveApiKeys(keys: ApiKeyStore): Promise<void> {
    await invoke('save_api_keys', { keys });
  }

  /**
   * Get available models for each provider
   */
  async getAvailableModels(): Promise<Record<LlmProvider, string[]>> {
    return await invoke<Record<LlmProvider, string[]>>('get_available_models');
  }

  /**
   * Get default configuration
   */
  getDefaultConfig(): AgentLlmConfig {
    return {
      agents: {
        [AgentType.Orchestrator]: {
          provider: LlmProvider.OpenRouter,
          model_name: 'x-ai/grok-4-fast'
        },
        [AgentType.Researcher]: {
          provider: LlmProvider.OpenRouter,
          model_name: 'deepseek/deepseek-v3.2-exp'
        }
      }
    };
  }

  /**
   * Get empty API key store
   */
  getEmptyApiKeyStore(): ApiKeyStore {
    return {
      keys: {
        [LlmProvider.OpenRouter]: ''
      }
    };
  }

  /**
   * Provider-specific presets for all agents
   */
  getPresets(): LlmPreset[] {
    const mixed: LlmPreset = {
      key: 'Mixed',
      label: 'Mixed/Optimal Preset',
      requiredProvider: null,
      config: this.getDefaultConfig()
    };

    return [mixed];
  }
}

