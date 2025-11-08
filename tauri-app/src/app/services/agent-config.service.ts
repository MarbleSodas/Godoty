import { Injectable } from '@angular/core';
import { invoke } from '@tauri-apps/api/core';

export enum LlmProvider {
  OpenRouter = 'OpenRouter',
  Claude = 'Claude'
}

export enum AgentType {
  Planner = 'Planner',
  CodeGenerator = 'CodeGenerator',
  Vision = 'Vision',
  Researcher = 'Researcher',
  Validator = 'Validator',
  Documentation = 'Documentation'
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
  key: 'Mixed' | 'Claude';
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
        [AgentType.Planner]: {
          provider: LlmProvider.OpenRouter,
          model_name: 'minimax/minimax-m2:free'
        },
        [AgentType.CodeGenerator]: {
          provider: LlmProvider.OpenRouter,
          model_name: 'qwen/qwen3-coder:free'
        },
        [AgentType.Vision]: {
          provider: LlmProvider.OpenRouter,
          model_name: 'nvidia/nemotron-nano-12b-v2-vl:free'
        },
        [AgentType.Researcher]: {
          provider: LlmProvider.OpenRouter,
          model_name: 'qwen/qwen3-235b-a22b:free'
        },
        [AgentType.Validator]: {
          provider: LlmProvider.OpenRouter,
          model_name: 'qwen/qwen3-235b-a22b:free'
        },
        [AgentType.Documentation]: {
          provider: LlmProvider.OpenRouter,
          model_name: 'meta-llama/llama-3.3-70b-instruct:free'
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
        [LlmProvider.OpenRouter]: '',
        [LlmProvider.Claude]: ''
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

    const claude: LlmPreset = {
      key: 'Claude',
      label: 'Claude Preset',
      requiredProvider: LlmProvider.Claude,
      config: {
        agents: {
          [AgentType.Planner]: { provider: LlmProvider.Claude, model_name: 'claude-3-5-haiku-20241022' },
          [AgentType.CodeGenerator]: { provider: LlmProvider.Claude, model_name: 'claude-3-5-sonnet-20241022' },
          [AgentType.Vision]: { provider: LlmProvider.Claude, model_name: 'claude-3-5-sonnet-20241022' },
          [AgentType.Researcher]: { provider: LlmProvider.Claude, model_name: 'claude-3-5-sonnet-20241022' },
          [AgentType.Validator]: { provider: LlmProvider.Claude, model_name: 'claude-3-5-sonnet-20241022' },
          [AgentType.Documentation]: { provider: LlmProvider.Claude, model_name: 'claude-3-5-haiku-20241022' },
        }
      }
    };

    return [mixed, claude];
  }
}

