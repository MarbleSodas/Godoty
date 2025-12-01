import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { APP_CONFIG } from '../core/constants';

export interface ModelPricing {
  prompt: number;      // Cost per input token
  completion: number; // Cost per output token
  request?: number;   // Per-request overhead (if any)
}

export interface OpenRouterMetrics {
  model: string;
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  actual_cost: number; // Direct from OpenRouter response
  generation_time: number;
}

export interface SessionMetrics {
  totalTokens: number;
  sessionCost: number;
  toolCalls: number;
  generationTimeMs?: number;
  modelName?: string;
}

export interface ProjectMetrics {
  totalCost: number;
  totalTokens: number;
  totalSessions: number;
}

export interface SessionState {
  totalCost: number;
  totalTokens: number;
  runHistory: Array<{
    timestamp: string;
    model: string;
    cost: number;
    tokens: number;
    duration: number;
  }>;
}

@Injectable({
  providedIn: 'root'
})
export class MetricsService {
  public sessionMetrics: BehaviorSubject<SessionMetrics> = new BehaviorSubject<SessionMetrics>({
    totalTokens: 0,
    sessionCost: 0,
    toolCalls: 0,
    generationTimeMs: 0,
    modelName: undefined
  });

  public projectMetrics: BehaviorSubject<ProjectMetrics> = new BehaviorSubject<ProjectMetrics>({
    totalCost: 0,
    totalTokens: 0,
    totalSessions: 0
  });

  private pricingCache: Map<string, ModelPricing> = new Map();
  private sessionState: Map<string, SessionState> = new Map();
  private pricingLoaded = false;

  constructor() {
    this.loadPricing();
  }

  /**
   * Load pricing data from OpenRouter API
   */
  async loadPricing(): Promise<void> {
    if (this.pricingLoaded) return;

    try {
      const response = await fetch(`${APP_CONFIG.OPENROUTER_API_BASE}/models`);
      if (!response.ok) {
        throw new Error(`Failed to fetch pricing: ${response.statusText}`);
      }

      const data = await response.json();

      // Cache model pricing data
      if (data.data && Array.isArray(data.data)) {
        for (const model of data.data) {
          if (model.id && model.pricing) {
            this.pricingCache.set(model.id, {
              prompt: parseFloat(model.pricing.prompt) || 0,
              completion: parseFloat(model.pricing.completion) || 0,
              request: parseFloat(model.pricing.request) || 0
            });
          }
        }
      }

      this.pricingLoaded = true;
      console.log(`[MetricsService] Loaded pricing for ${this.pricingCache.size} models`);
    } catch (error) {
      console.error('[MetricsService] Failed to load pricing:', error);
      // Set up fallback pricing for common models
      this.setupFallbackPricing();
    }
  }

  /**
   * Setup fallback pricing for common models
   */
  private setupFallbackPricing(): void {
    // Common model fallback pricing (prices per 1M tokens)
    const fallbackPricing: Record<string, ModelPricing> = {
      'openai/gpt-4-turbo': { prompt: 0.01, completion: 0.03 },
      'openai/gpt-4o': { prompt: 0.005, completion: 0.015 },
      'anthropic/claude-3.5-sonnet': { prompt: 0.003, completion: 0.015 },
      'google/gemini-pro': { prompt: 0.0005, completion: 0.0015 }
    };

    for (const [modelId, pricing] of Object.entries(fallbackPricing)) {
      this.pricingCache.set(modelId, pricing);
    }

    this.pricingLoaded = true;
    console.log('[MetricsService] Using fallback pricing for common models');
  }

  /**
   * Calculate cost based on model and token usage
   */
  calculateCost(modelId: string, inputTokens: number, outputTokens: number): number {
    const pricing = this.pricingCache.get(modelId);
    if (!pricing) {
      console.warn(`[MetricsService] No pricing found for model: ${modelId}`);
      return 0;
    }

    // Pricing is typically per 1M tokens, so we need to divide by 1,000,000
    const inputCost = (inputTokens / 1000000) * pricing.prompt;
    const outputCost = (outputTokens / 1000000) * pricing.completion;
    const requestCost = pricing.request || 0;

    return inputCost + outputCost + requestCost;
  }

  /**
   * Calculate real-time cost for a model and tokens
   */
  async calculateRealTimeCost(model: string, tokens: number): Promise<number> {
    if (!this.pricingLoaded) {
      await this.loadPricing();
    }

    // For a rough estimate, assume 70% input, 30% output tokens
    const inputTokens = Math.floor(tokens * 0.7);
    const outputTokens = Math.floor(tokens * 0.3);

    return this.calculateCost(model, inputTokens, outputTokens);
  }

  /**
   * Update session cost based on message data from backend
   */
  updateSessionCost(sessionId: string, messageData: any): void {
    // Use actual_cost from backend if available
    const actualCost = messageData.metrics?.actual_cost || 0;
    const totalTokens = messageData.metrics?.usage?.total_tokens || 0;
    const modelName = messageData.model || 'unknown';
    const generationTime = messageData.generation_time || 0;

    // Get or create session state
    let sessionState = this.sessionState.get(sessionId);
    if (!sessionState) {
      sessionState = {
        totalCost: 0,
        totalTokens: 0,
        runHistory: []
      };
      this.sessionState.set(sessionId, sessionState);
    }

    // Update session state
    sessionState.totalCost += actualCost;
    sessionState.totalTokens += totalTokens;
    sessionState.runHistory.push({
      timestamp: new Date().toISOString(),
      model: modelName,
      cost: actualCost,
      tokens: totalTokens,
      duration: generationTime
    });

    // Update reactive metrics
    const currentMetrics = this.sessionMetrics.value;
    this.sessionMetrics.next({
      totalTokens: sessionState.totalTokens,
      sessionCost: sessionState.totalCost,
      toolCalls: currentMetrics.toolCalls,
      generationTimeMs: generationTime,
      modelName: modelName
    });
  }

  /**
   * Update session metrics with tool call information
   */
  updateToolCallCount(sessionId: string, increment: number = 1): void {
    const currentMetrics = this.sessionMetrics.value;
    this.sessionMetrics.next({
      ...currentMetrics,
      toolCalls: currentMetrics.toolCalls + increment
    });
  }

  /**
   * Update project metrics from backend data
   */
  updateProjectMetrics(backendMetrics: any): void {
    if (backendMetrics.total_cost !== undefined || backendMetrics.total_tokens !== undefined) {
      this.projectMetrics.next({
        totalCost: backendMetrics.total_cost || 0,
        totalTokens: backendMetrics.total_tokens || 0,
        totalSessions: backendMetrics.total_sessions || 0
      });
    }
  }

  /**
   * Get session state for a specific session
   */
  getSessionState(sessionId: string): SessionState | undefined {
    return this.sessionState.get(sessionId);
  }

  /**
   * Get all session states
   */
  getAllSessionStates(): Map<string, SessionState> {
    return new Map(this.sessionState);
  }

  /**
   * Reset session metrics for a new session
   */
  resetSessionMetrics(): void {
    this.sessionMetrics.next({
      totalTokens: 0,
      sessionCost: 0,
      toolCalls: 0,
      generationTimeMs: 0,
      modelName: undefined
    });
  }

  /**
   * Get pricing information for a model
   */
  getModelPricing(modelId: string): ModelPricing | undefined {
    return this.pricingCache.get(modelId);
  }

  /**
   * Check if pricing data is loaded
   */
  isPricingLoaded(): boolean {
    return this.pricingLoaded;
  }

  /**
   * Force reload pricing data
   */
  async refreshPricing(): Promise<void> {
    this.pricingCache.clear();
    this.pricingLoaded = false;
    await this.loadPricing();
  }

  /**
   * Get cached pricing data for all models
   */
  getAllPricing(): Map<string, ModelPricing> {
    return new Map(this.pricingCache);
  }

  /**
   * Format cost for display
   */
  formatCost(cost: number): string {
    return `$${cost.toFixed(6)}`;
  }

  /**
   * Format tokens for display
   */
  formatTokens(tokens: number): string {
    if (tokens < 1000) {
      return tokens.toString();
    } else if (tokens < 1000000) {
      return `${(tokens / 1000).toFixed(1)}K`;
    } else {
      return `${(tokens / 1000000).toFixed(2)}M`;
    }
  }

  /**
   * Calculate cost efficiency (cost per 1K tokens)
   */
  calculateCostEfficiency(cost: number, tokens: number): number {
    if (tokens === 0) return 0;
    return (cost / tokens) * 1000;
  }
}