export interface WorkflowMetrics {
  // Token usage
  total_tokens: number;
  planning_tokens: number;
  generation_tokens: number;
  validation_tokens: number;
  documentation_tokens: number;

  // Execution time (milliseconds)
  total_time_ms: number;
  planning_time_ms: number;
  generation_time_ms: number;
  validation_time_ms: number;
  kb_search_time_ms: number;

  // Knowledge base metrics
  plugin_kb_queries: number;
  docs_kb_queries: number;
  total_docs_retrieved: number;
  avg_relevance_score: number;

  // Success metrics
  commands_generated: number;
  commands_validated: number;
  validation_errors: number;
  validation_warnings: number;
  reasoning_steps: number;
  retry_attempts: number;

  // Timestamps
  started_at: number;
  completed_at: number;

  // Request metadata
  request_id: string;
  user_input: string;
  success: boolean;
  error_message?: string | null;
}

export interface MetricsSummary {
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  success_rate: number; // 0-100
  total_tokens: number;
  avg_tokens_per_request: number;
  avg_time_ms: number;
  total_commands_generated: number;
}
