import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

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

export interface ProjectMetrics {
  totalCost: number;
  totalTokens: number;
  totalSessions: number;
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

  private sessionState: Map<string, SessionState> = new Map();

  constructor() {
    // No pricing API calls - simplified service
  }

  /**
   * Update session cost based on message data from backend
   */
  updateSessionCost(sessionId: string, messageData: any): void {
    // Use actual_cost from backend (raw OpenRouter data)
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

    // Also update project totals (simplified approach)
    this.addSessionToProject({
      tokens: totalTokens,
      cost: actualCost
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
   * Update project metrics (simplified)
   */
  updateProjectMetrics(updates: Partial<ProjectMetrics>): void {
    const current = this.projectMetrics.value;
    this.projectMetrics.next({ ...current, ...updates });
  }

  /**
   * Add session data to project totals
   */
  addSessionToProject(sessionData: { tokens: number; cost: number }): void {
    const current = this.projectMetrics.value;
    this.projectMetrics.next({
      totalCost: current.totalCost + sessionData.cost,
      totalTokens: current.totalTokens + sessionData.tokens,
      totalSessions: current.totalSessions
    });
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
}