import { Injectable, NgZone } from '@angular/core';
import { invoke } from '@tauri-apps/api/core';
import { listen, UnlistenFn } from '@tauri-apps/api/event';

export interface StreamingAgentResponse {
  session_id: string;
  chunk_id: number;
  content_chunk?: string;
  thought_process?: OrchestratorThought;
  tool_execution_result?: ToolExecutionResult;
  is_complete: boolean;
  final_response?: AgentOutput;
  accumulated_content?: string;
}

export interface OrchestratorThought {
  phase: string;
  insight: string;
  confidence: number;
  timestamp?: number;
}

export interface ToolExecutionResult {
  tool_name: string;
  status: 'Validating' | 'Executing' | 'Processing' | 'Completed' | 'Failed' | 'Cancelled';
  progress: number;
  message: string;
  result?: any;
  error?: string;
  execution_time_ms?: number;
}

export interface AgentOutput {
  content: string;
  tokens_used: number;
  execution_time_ms: number;
  metadata: Record<string, any>;
  cost_usd?: number;
  thoughts: OrchestratorThought[];
}

export interface StreamingExecuteRequest {
  session_id?: string;
  user_input: string;
  project_context: string;
  chat_history?: string;
  use_streaming?: boolean;
}

export interface StreamingExecuteResponse {
  session_id: string;
  streaming_enabled: boolean;
  message: string;
}

@Injectable({
  providedIn: 'root'
})
export class StreamingAgentService {
  private activeStreams: Map<string, UnlistenFn[]> = new Map();

  constructor(private ngZone: NgZone) {}

  /**
   * Start a streaming agent execution
   */
  async startStreaming(request: StreamingExecuteRequest): Promise<StreamingExecuteResponse> {
    try {
      const response = await invoke<StreamingExecuteResponse>('start_agent_streaming', {
        request: {
          ...request,
          use_streaming: true // Force streaming for this service
        }
      });
      return response;
    } catch (error) {
      console.error('Failed to start streaming agent:', error);
      throw error;
    }
  }

  /**
   * Subscribe to streaming responses for a session
   */
  async subscribeToStream(
    sessionId: string,
    onChunk: (chunk: StreamingAgentResponse) => void
  ): Promise<void> {
    // Clean up any existing listeners for this session
    this.unsubscribeFromStream(sessionId);

    const listeners: UnlistenFn[] = [];

    try {
      // Listen for streaming chunks
      const chunkListener = await listen<StreamingAgentResponse>(
        `agent-stream-chunk-${sessionId}`,
        (event) => {
          this.ngZone.run(() => {
            onChunk(event.payload);
          });
        }
      );
      listeners.push(chunkListener);

      // Listen for stream completion
      const completionListener = await listen<AgentOutput>(
        `agent-stream-complete-${sessionId}`,
        (event) => {
          this.ngZone.run(() => {
            onChunk({
              session_id: sessionId,
              chunk_id: -1,
              is_complete: true,
              final_response: event.payload,
              accumulated_content: event.payload.content
            });
          });
        }
      );
      listeners.push(completionListener);

      // Listen for stream errors
      const errorListener = await listen<{ error: string }>(
        `agent-stream-error-${sessionId}`,
        (event) => {
          this.ngZone.run(() => {
            console.error('Stream error:', event.payload.error);
            onChunk({
              session_id: sessionId,
              chunk_id: -1,
              is_complete: true,
              tool_execution_result: {
                tool_name: 'Stream',
                status: 'Failed',
                progress: 1.0,
                message: event.payload.error,
                error: event.payload.error
              }
            });
          });
        }
      );
      listeners.push(errorListener);

      // Store listeners for cleanup
      this.activeStreams.set(sessionId, listeners);
    } catch (error) {
      console.error('Failed to subscribe to stream:', error);
      // Cleanup any partially created listeners
      listeners.forEach(l => l());
      throw error;
    }
  }

  /**
   * Unsubscribe from a stream
   */
  unsubscribeFromStream(sessionId: string): void {
    const listeners = this.activeStreams.get(sessionId);
    if (listeners) {
      listeners.forEach(listener => listener());
      this.activeStreams.delete(sessionId);
    }
  }

  /**
   * Check if a stream is active
   */
  isStreamActive(sessionId: string): boolean {
    return this.activeStreams.has(sessionId);
  }

  /**
   * Get all active stream IDs
   */
  getActiveStreamIds(): string[] {
    return Array.from(this.activeStreams.keys());
  }

  /**
   * Clean up all active streams
   */
  cleanupAllStreams(): void {
    for (const sessionId of this.activeStreams.keys()) {
      this.unsubscribeFromStream(sessionId);
    }
  }

  /**
   * Execute agent with streaming (convenience method that combines start and subscribe)
   */
  async executeWithStreaming(
    request: StreamingExecuteRequest,
    onChunk: (chunk: StreamingAgentResponse) => void
  ): Promise<StreamingExecuteResponse> {
    const response = await this.startStreaming(request);

    if (response.streaming_enabled) {
      await this.subscribeToStream(response.session_id, onChunk);
    }

    return response;
  }

  /**
   * Execute agent with streaming that returns a Promise with the final result
   */
  async executeWithStreamingPromise(
    request: StreamingExecuteRequest,
    onProgress?: (chunk: StreamingAgentResponse) => void
  ): Promise<AgentOutput> {
    return new Promise(async (resolve, reject) => {
      try {
        const response = await this.startStreaming(request);

        if (!response.streaming_enabled) {
          reject(new Error('Streaming is not enabled'));
          return;
        }

        await this.subscribeToStream(response.session_id, (chunk) => {
          if (onProgress) {
            onProgress(chunk);
          }

          if (chunk.is_complete && chunk.final_response) {
            resolve(chunk.final_response);
          }
        });
      } catch (error) {
        reject(error);
      }
    });
  }
}