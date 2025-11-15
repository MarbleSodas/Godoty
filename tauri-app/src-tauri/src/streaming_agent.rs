use crate::strands_agent::{AgentExecutionContext, AgentOutput, OrchestratorThought};
use anyhow::Result;
use serde::{Deserialize, Serialize};
use tokio::sync::mpsc::UnboundedSender;

/// Represents a streaming chunk of agent response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamingAgentResponse {
    /// Unique session identifier
    pub session_id: String,
    /// Sequential chunk identifier
    pub chunk_id: usize,
    /// Partial content response
    pub content_chunk: Option<String>,
    /// Current thought process from the agent
    pub thought_process: Option<OrchestratorThought>,
    /// Tool execution progress and results
    pub tool_execution_result: Option<ToolExecutionResult>,
    /// Whether this is the final chunk
    pub is_complete: bool,
    /// Final complete response (only when is_complete=true)
    pub final_response: Option<AgentOutput>,
    /// Accumulated content so far (for frontend convenience)
    pub accumulated_content: Option<String>,
}

/// Tool execution progress and result information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolExecutionResult {
    /// Name of the tool being executed
    pub tool_name: String,
    /// Current execution status
    pub status: ToolExecutionStatus,
    /// Progress percentage (0.0 to 1.0)
    pub progress: f32,
    /// Detailed status message
    pub message: String,
    /// Execution results (when complete)
    pub result: Option<serde_json::Value>,
    /// Error information if execution failed
    pub error: Option<String>,
    /// Execution time in milliseconds
    pub execution_time_ms: Option<u64>,
}

/// Tool execution status
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ToolExecutionStatus {
    /// Tool is being validated
    Validating,
    /// Tool is actively executing
    Executing,
    /// Processing tool results
    Processing,
    /// Tool completed successfully
    Completed,
    /// Tool execution failed
    Failed,
    /// Tool was cancelled
    Cancelled,
}

#[allow(dead_code)] // Streaming infrastructure - enhancement plan Phase 1
impl ToolExecutionResult {
    pub fn new(tool_name: impl Into<String>) -> Self {
        Self {
            tool_name: tool_name.into(),
            status: ToolExecutionStatus::Validating,
            progress: 0.0,
            message: "Initializing tool execution...".to_string(),
            result: None,
            error: None,
            execution_time_ms: None,
        }
    }

    pub fn with_status(mut self, status: ToolExecutionStatus) -> Self {
        self.status = status;
        self
    }

    pub fn with_progress(mut self, progress: f32) -> Self {
        self.progress = progress.clamp(0.0, 1.0);
        self
    }

    pub fn with_message(mut self, message: impl Into<String>) -> Self {
        self.message = message.into();
        self
    }

    pub fn with_result(mut self, result: serde_json::Value) -> Self {
        self.result = Some(result);
        self.status = ToolExecutionStatus::Completed;
        self.progress = 1.0;
        self.message = "Tool execution completed successfully".to_string();
        self
    }

    pub fn with_error(mut self, error: impl Into<String>) -> Self {
        self.error = Some(error.into());
        self.status = ToolExecutionStatus::Failed;
        self.message = format!("Tool execution failed: {}", self.error.as_ref().unwrap());
        self
    }

    pub fn with_execution_time(mut self, time_ms: u64) -> Self {
        self.execution_time_ms = Some(time_ms);
        self
    }
}

/// Trait for streaming-capable agents
#[async_trait::async_trait]
#[allow(dead_code)] // Streaming agents - enhancement plan Phase 1
pub trait StreamingStrandsAgent: Send + Sync {
    /// Execute agent with streaming responses
    async fn execute_streaming(
        &self,
        context: &AgentExecutionContext,
        chunk_sender: UnboundedSender<StreamingAgentResponse>,
        session_id: String,
    ) -> Result<AgentOutput>;

    /// Check if this agent supports streaming
    fn supports_streaming(&self) -> bool {
        true
    }
}

/// Agent loop state for tracking execution progress
#[derive(Debug, Clone, Serialize, Deserialize)]
#[allow(dead_code)] // Streaming infrastructure - enhancement plan Phase 1
pub enum AgentLoopState {
    /// Agent is idle, waiting for input
    Idle,
    /// Processing user input and reasoning
    Processing,
    /// Executing tools to gather information
    ExecutingTools,
    /// Reasoning about tool results and planning next steps
    Reasoning,
    /// Generating final response
    Responding,
    /// Execution complete
    Complete,
    /// Error occurred during execution
    Error(String),
}

/// Agent execution context with streaming support
#[derive(Clone)]
#[allow(dead_code)] // Streaming infrastructure - enhancement plan Phase 1
pub struct StreamingAgentContext {
    /// Original execution context
    pub base_context: AgentExecutionContext,
    /// Session identifier for tracking
    pub session_id: String,
    /// Current loop state
    pub loop_state: AgentLoopState,
    /// Accumulated thoughts during execution
    pub accumulated_thoughts: Vec<OrchestratorThought>,
    /// Tools executed so far
    pub executed_tools: Vec<String>,
    /// Iteration count in the agent loop
    pub iteration_count: usize,
    /// Maximum allowed iterations
    pub max_iterations: usize,
    /// Confidence threshold for decision making
    pub confidence_threshold: f32,
}

#[allow(dead_code)] // Streaming infrastructure - enhancement plan Phase 1
impl StreamingAgentContext {
    pub fn new(base_context: AgentExecutionContext, session_id: String) -> Self {
        Self {
            base_context,
            session_id,
            loop_state: AgentLoopState::Idle,
            accumulated_thoughts: Vec::new(),
            executed_tools: Vec::new(),
            iteration_count: 0,
            max_iterations: 10,
            confidence_threshold: 0.8,
        }
    }

    pub fn add_thought(&mut self, thought: OrchestratorThought) {
        self.accumulated_thoughts.push(thought);
    }

    pub fn update_state(&mut self, state: AgentLoopState) {
        self.loop_state = state;
    }

    pub fn should_continue_loop(&self) -> bool {
        self.iteration_count < self.max_iterations && !matches!(self.loop_state, AgentLoopState::Complete | AgentLoopState::Error(_))
    }

    pub fn increment_iteration(&mut self) {
        self.iteration_count += 1;
    }
}

/// Helper functions for creating streaming responses
#[allow(dead_code)] // Streaming infrastructure - enhancement plan Phase 1
impl StreamingAgentResponse {
    pub fn new(session_id: String, chunk_id: usize) -> Self {
        Self {
            session_id,
            chunk_id,
            content_chunk: None,
            thought_process: None,
            tool_execution_result: None,
            is_complete: false,
            final_response: None,
            accumulated_content: None,
        }
    }

    pub fn with_content(mut self, content: impl Into<String>) -> Self {
        self.content_chunk = Some(content.into());
        self
    }

    pub fn with_thought(mut self, thought: OrchestratorThought) -> Self {
        self.thought_process = Some(thought);
        self
    }

    pub fn with_tool_result(mut self, result: ToolExecutionResult) -> Self {
        self.tool_execution_result = Some(result);
        self
    }

    pub fn with_accumulated(mut self, accumulated: impl Into<String>) -> Self {
        self.accumulated_content = Some(accumulated.into());
        self
    }

    pub fn as_complete(mut self, final_response: AgentOutput) -> Self {
        self.is_complete = true;
        self.final_response = Some(final_response);
        self
    }
}