import { Injectable } from '@angular/core';
import { invoke } from '@tauri-apps/api/core';

export enum LlmProvider {
  OpenRouter = 'OpenRouter',
  ZaiGlm = 'ZaiGlm'
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
          model_name: 'z-ai/glm-4.5-air:free'
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
        [LlmProvider.ZaiGlm]: ''
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

    const zaiglm: LlmPreset = {
      key: 'ZaiGlm',
      label: 'Z.ai Preset',
      requiredProvider: LlmProvider.ZaiGlm,
      config: {
        agents: {
          [AgentType.Planner]: { provider: LlmProvider.ZaiGlm, model_name: 'glm-4.5' },
          [AgentType.CodeGenerator]: { provider: LlmProvider.ZaiGlm, model_name: 'glm-4.5' },
          [AgentType.Vision]: { provider: LlmProvider.ZaiGlm, model_name: 'glm-4v' },
          [AgentType.Researcher]: { provider: LlmProvider.ZaiGlm, model_name: 'glm-4-long' },
          [AgentType.Validator]: { provider: LlmProvider.ZaiGlm, model_name: 'glm-4-air' },
          [AgentType.Documentation]: { provider: LlmProvider.ZaiGlm, model_name: 'glm-4-plus' },
        }
      }
    };

    return [mixed, zaiglm];
  }
}

