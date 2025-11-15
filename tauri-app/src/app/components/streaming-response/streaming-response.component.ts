import { Component, Input, OnDestroy, OnInit, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ProgressBarModule } from 'primeng/progressbar';
import { CardModule } from 'primeng/card';
import { BadgeModule } from 'primeng/badge';
import { MessageModule } from 'primeng/message';
import { ButtonModule } from 'primeng/button';
import { TooltipModule } from 'primeng/tooltip';
import { ScrollPanelModule } from 'primeng/scrollpanel';
import {
  StreamingAgentService,
  StreamingAgentResponse,
  OrchestratorThought,
  ToolExecutionResult
} from '../../services/streaming-agent.service';

@Component({
  selector: 'app-streaming-response',
  standalone: true,
  imports: [
    CommonModule,
    ProgressBarModule,
    CardModule,
    BadgeModule,
    MessageModule,
    ButtonModule,
    TooltipModule,
    ScrollPanelModule
  ],
  templateUrl: './streaming-response.component.html',
  styleUrls: ['./streaming-response.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class StreamingResponseComponent implements OnInit, OnDestroy {
  @Input() sessionId: string | null = null;
  @Input() request: any = null;

  // Agent state
  isStreaming = false;
  isComplete = false;
  hasError = false;

  // Current data
  currentThought: OrchestratorThought | null = null;
  currentTool: ToolExecutionResult | null = null;
  accumulatedResponse = '';
  finalResponse: any = null;
  thoughts: OrchestratorThought[] = [];

  // Execution metrics
  executionTime = 0;
  tokensUsed = 0;
  commandsCount = 0;

  // Progress
  currentProgress = 0;
  progressMessage = '';

  // Expose Math to template
  protected readonly Math = Math;

  constructor(private streamingService: StreamingAgentService) {}

  ngOnInit(): void {
    if (this.request) {
      this.startStreaming();
    }
  }

  ngOnDestroy(): void {
    if (this.sessionId) {
      this.streamingService.unsubscribeFromStream(this.sessionId);
    }
  }

  private async startStreaming(): Promise<void> {
    if (!this.request) return;

    try {
      this.isStreaming = true;
      this.hasError = false;

      const response = await this.streamingService.startStreaming({
        user_input: this.request.user_input,
        project_context: this.request.project_context,
        chat_history: this.request.chat_history,
        use_streaming: true
      });

      this.sessionId = response.session_id;

      await this.streamingService.subscribeToStream(this.sessionId, (chunk) => {
        this.handleStreamChunk(chunk);
      });
    } catch (error) {
      console.error('Failed to start streaming:', error);
      this.hasError = true;
      this.isStreaming = false;
    }
  }

  private handleStreamChunk(chunk: StreamingAgentResponse): void {
    // Update accumulated content
    if (chunk.accumulated_content) {
      this.accumulatedResponse = chunk.accumulated_content;
    }

    // Handle thought process
    if (chunk.thought_process) {
      this.currentThought = chunk.thought_process;
      if (!this.thoughts.find(t => t.insight === chunk.thought_process!.insight)) {
        this.thoughts.push(chunk.thought_process);
      }
    }

    // Handle tool execution
    if (chunk.tool_execution_result) {
      this.currentTool = chunk.tool_execution_result;
      this.currentProgress = chunk.tool_execution_result.progress;
      this.progressMessage = chunk.tool_execution_result.message;
    }

    // Handle completion
    if (chunk.is_complete) {
      this.isStreaming = false;
      this.isComplete = true;

      if (chunk.final_response) {
        this.finalResponse = chunk.final_response;
        this.accumulatedResponse = chunk.final_response.content || this.accumulatedResponse;
        this.executionTime = chunk.final_response.execution_time_ms || 0;
        this.tokensUsed = chunk.final_response.tokens_used || 0;
        this.commandsCount = this.extractCommandsCount(this.finalResponse.content);
      }

      // Clean up stream
      if (this.sessionId) {
        this.streamingService.unsubscribeFromStream(this.sessionId);
      }
    }
  }

  private extractCommandsCount(content: string): number {
    try {
      const jsonMatch = content.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]);
        if (parsed.commands && Array.isArray(parsed.commands)) {
          return parsed.commands.length;
        }
      }
    } catch (e) {
      // Ignore parsing errors
    }
    return 0;
  }

  getPhaseBadgeSeverity(phase: string): 'success' | 'info' | 'warn' | 'danger' {
    switch (phase) {
      case 'streaming_init':
      case 'final_response':
        return 'success';
      case 'tool_calls_requested':
      case 'tool_executed':
        return 'info';
      case 'error':
      case 'max_iterations_reached':
        return 'danger';
      default:
        return 'info';
    }
  }

  getToolStatusSeverity(status: string): 'success' | 'info' | 'warn' | 'danger' {
    switch (status) {
      case 'Completed':
        return 'success';
      case 'Executing':
      case 'Processing':
        return 'info';
      case 'Failed':
        return 'danger';
      default:
        return 'warn';
    }
  }

  formatConfidence(confidence: number): string {
    return `${Math.round(confidence * 100)}%`;
  }

  formatExecutionTime(ms: number): string {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  }

  formatTokens(tokens: number): string {
    if (tokens < 1000) return tokens.toString();
    return `${(tokens / 1000).toFixed(1)}k`;
  }

  onExecuteCommands(): void {
    // Emit event to parent or service to execute commands
    console.log('Executing commands:', this.finalResponse);
    // This would be connected to the actual command execution logic
  }

  onRetry(): void {
    // Reset state and retry
    this.reset();
    this.startStreaming();
  }

  private reset(): void {
    this.isStreaming = false;
    this.isComplete = false;
    this.hasError = false;
    this.currentThought = null;
    this.currentTool = null;
    this.accumulatedResponse = '';
    this.finalResponse = null;
    this.thoughts = [];
    this.executionTime = 0;
    this.tokensUsed = 0;
    this.commandsCount = 0;
    this.currentProgress = 0;
    this.progressMessage = '';
  }

  public formatResponseContent(content: string): string {
    if (!content) return '';

    // Format JSON blocks
    let formatted = content.replace(
      /```json\s*([\s\S]*?)```/g,
      '<pre><code class="json">$1</code></pre>'
    );

    // Format code blocks
    formatted = formatted.replace(
      /```(\w+)?\s*([\s\S]*?)```/g,
      '<pre><code class="$1">$2</code></pre>'
    );

    // Convert newlines to HTML breaks
    formatted = formatted.replace(/\n/g, '<br>');

    // Format inline code
    formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');

    return formatted;
  }
}