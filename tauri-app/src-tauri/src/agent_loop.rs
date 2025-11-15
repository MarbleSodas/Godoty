use crate::streaming_agent::{StreamingAgentResponse, StreamingStrandsAgent, ToolExecutionResult, ToolExecutionStatus};
use crate::strands_agent::{AgentExecutionContext, OrchestratorThought};
use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::sync::Arc;
use tokio::sync::{mpsc, RwLock};
use uuid::Uuid;

/// Agent loop states for iterative reasoning cycle
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum AgentLoopState {
    /// Initial state, ready to start processing
    Idle,
    /// Analyzing the user input and planning
    Processing,
    /// Executing tools to gather information
    ExecutingTools,
    /// Reasoning about gathered information
    Reasoning,
    /// Formulating and sending response
    Responding,
    /// Execution completed successfully
    Complete,
    /// Error occurred during execution
    Error,
}

impl std::fmt::Display for AgentLoopState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            AgentLoopState::Idle => write!(f, "idle"),
            AgentLoopState::Processing => write!(f, "processing"),
            AgentLoopState::ExecutingTools => write!(f, "executing_tools"),
            AgentLoopState::Reasoning => write!(f, "reasoning"),
            AgentLoopState::Responding => write!(f, "responding"),
            AgentLoopState::Complete => write!(f, "complete"),
            AgentLoopState::Error => write!(f, "error"),
        }
    }
}

/// Internal state for the agent loop
#[derive(Debug)]
pub struct AgentLoopStateInternal {
    /// Current state in the loop
    pub current_state: AgentLoopState,
    /// Previous state for tracking transitions
    pub previous_state: Option<AgentLoopState>,
    /// Number of iterations through the loop
    pub iteration_count: usize,
    /// Maximum iterations allowed (to prevent infinite loops)
    pub max_iterations: usize,
    /// Error message if in error state
    pub error_message: Option<String>,
    /// Whether execution should continue
    pub should_continue: bool,
}

/// Represents an action to be taken in the next loop iteration
#[derive(Debug, Clone)]
pub enum LoopAction {
    /// Continue to the next state in the normal flow
    Continue,
    /// Jump to a specific state
    JumpToState(AgentLoopState),
    /// Repeat the current state
    #[allow(dead_code)] // Future loop control feature
    Repeat,
    /// Terminate execution
    Terminate,
}

/// Configuration for agent loop behavior
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentLoopConfig {
    /// Maximum number of iterations to prevent infinite loops
    pub max_iterations: usize,
    /// Whether to use adaptive reasoning (more iterations for complex tasks)
    pub adaptive_reasoning: bool,
    /// Minimum confidence threshold to consider a task complete
    pub min_confidence_threshold: f32,
    /// Whether to automatically execute tool suggestions
    pub auto_execute_tools: bool,
    /// Timeout per iteration in milliseconds
    pub iteration_timeout_ms: u64,
}

impl Default for AgentLoopConfig {
    fn default() -> Self {
        Self {
            max_iterations: 10,
            adaptive_reasoning: true,
            min_confidence_threshold: 0.8,
            auto_execute_tools: true,
            iteration_timeout_ms: 30000, // 30 seconds
        }
    }
}

/// Core agent loop implementation for iterative reasoning
pub struct AgentLoop {
    /// Unique identifier for this loop instance
    id: String,
    /// Current internal state
    state: Arc<RwLock<AgentLoopStateInternal>>,
    /// Configuration for the loop
    config: AgentLoopConfig,
    /// Execution context for the agent
    context: AgentExecutionContext,
    /// History of thoughts for tracking reasoning
    thought_history: VecDeque<OrchestratorThought>,
    /// History of tool executions
    tool_history: VecDeque<ToolExecutionResult>,
    /// Accumulated response content
    accumulated_content: String,
}

impl AgentLoop {
    /// Create a new agent loop instance
    pub fn new(
        context: AgentExecutionContext,
        config: Option<AgentLoopConfig>,
    ) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            state: Arc::new(RwLock::new(AgentLoopStateInternal {
                current_state: AgentLoopState::Idle,
                previous_state: None,
                iteration_count: 0,
                max_iterations: config.as_ref().map_or(10, |c| c.max_iterations),
                error_message: None,
                should_continue: true,
            })),
            config: config.unwrap_or_default(),
            context,
            thought_history: VecDeque::new(),
            tool_history: VecDeque::new(),
            accumulated_content: String::new(),
        }
    }

    /// Get the current state
    pub async fn get_state(&self) -> AgentLoopState {
        self.state.read().await.current_state.clone()
    }

    /// Get the iteration count
    #[allow(dead_code)] // Loop monitoring and debugging
    pub async fn get_iteration_count(&self) -> usize {
        self.state.read().await.iteration_count
    }

    /// Get the thought history
    #[allow(dead_code)] // Loop monitoring and debugging
    pub fn get_thought_history(&self) -> &VecDeque<OrchestratorThought> {
        &self.thought_history
    }

    /// Get the tool execution history
    #[allow(dead_code)] // Loop monitoring and debugging
    pub fn get_tool_history(&self) -> &VecDeque<ToolExecutionResult> {
        &self.tool_history
    }

    /// Execute the agent loop with streaming support
    pub async fn execute_streaming<T>(
        &mut self,
        agent: &T,
        chunk_sender: mpsc::UnboundedSender<StreamingAgentResponse>,
        session_id: String,
    ) -> Result<crate::strands_agent::AgentOutput>
    where
        T: StreamingStrandsAgent + ?Sized,
    {
        // Transition to Processing state
        self.transition_to_state(AgentLoopState::Processing).await?;
        self.send_state_update(&session_id, &chunk_sender).await?;

        // Main execution loop
        while self.should_continue().await {
            // Check iteration limit
            if self.has_exceeded_iterations().await {
                self.set_error("Maximum iterations exceeded".to_string()).await;
                break;
            }

            // Get current action based on state
            let action = self.determine_next_action().await?;

            // Execute action
            match action {
                LoopAction::Continue => {
                    self.execute_current_state(agent, &session_id, &chunk_sender)
                        .await?;
                }
                LoopAction::JumpToState(state) => {
                    self.transition_to_state(state).await?;
                    self.send_state_update(&session_id, &chunk_sender).await?;
                }
                LoopAction::Repeat => {
                    // Stay in current state and re-execute
                    self.execute_current_state(agent, &session_id, &chunk_sender)
                        .await?;
                }
                LoopAction::Terminate => {
                    break;
                }
            }

            // Increment iteration count
            self.increment_iteration().await;
        }

        // Generate final response
        self.transition_to_state(AgentLoopState::Complete).await?;
        let final_output = self.generate_final_output().await?;

        // Send completion
        self.send_completion(&session_id, &chunk_sender, &final_output).await?;

        Ok(final_output)
    }

    /// Execute the logic for the current state
    async fn execute_current_state<T>(
        &mut self,
        agent: &T,
        session_id: &str,
        chunk_sender: &mpsc::UnboundedSender<StreamingAgentResponse>,
    ) -> Result<()>
    where
        T: StreamingStrandsAgent + ?Sized,
    {
        let current_state = self.get_state().await;

        match current_state {
            AgentLoopState::Processing => {
                // Analyze input and create plan
                let thought = OrchestratorThought {
                    phase: "processing".to_string(),
                    insight: "Analyzing user request and planning execution".to_string(),
                    confidence: 0.9,
                    timestamp: std::time::SystemTime::now(),
                };
                self.add_thought(thought.clone()).await;
                self.send_thought_update(session_id, chunk_sender, thought).await?;

                // Transition to tool execution or reasoning based on complexity
                if self.requires_tool_execution().await {
                    self.transition_to_state(AgentLoopState::ExecutingTools).await?;
                } else {
                    self.transition_to_state(AgentLoopState::Reasoning).await?;
                }
            }
            AgentLoopState::ExecutingTools => {
                // Execute tools to gather information
                self.execute_tools(agent, session_id, chunk_sender).await?;
                self.transition_to_state(AgentLoopState::Reasoning).await?;
            }
            AgentLoopState::Reasoning => {
                // Process gathered information and reason
                let thought = OrchestratorThought {
                    phase: "reasoning".to_string(),
                    insight: "Processing gathered information and formulating response".to_string(),
                    confidence: 0.85,
                    timestamp: std::time::SystemTime::now(),
                };
                self.add_thought(thought.clone()).await;
                self.send_thought_update(session_id, chunk_sender, thought).await?;

                // Check if we need more information
                if self.needs_more_information().await {
                    self.transition_to_state(AgentLoopState::ExecutingTools).await?;
                } else {
                    self.transition_to_state(AgentLoopState::Responding).await?;
                }
            }
            AgentLoopState::Responding => {
                // Generate and stream response
                let thought = OrchestratorThought {
                    phase: "responding".to_string(),
                    insight: "Generating final response".to_string(),
                    confidence: 0.95,
                    timestamp: std::time::SystemTime::now(),
                };
                self.add_thought(thought.clone()).await;
                self.send_thought_update(session_id, chunk_sender, thought).await?;

                self.generate_response_content(agent, session_id, chunk_sender)
                    .await?;
            }
            _ => {
                // Should not reach here in normal flow
                self.transition_to_state(AgentLoopState::Complete).await?;
            }
        }

        Ok(())
    }

    /// Transition to a new state
    async fn transition_to_state(&self, new_state: AgentLoopState) -> Result<()> {
        let mut state = self.state.write().await;
        state.previous_state = Some(state.current_state.clone());
        state.current_state = new_state;
        Ok(())
    }

    /// Determine the next action based on current state
    async fn determine_next_action(&self) -> Result<LoopAction> {
        let state = self.state.read().await;

        match state.current_state {
            AgentLoopState::Error => Ok(LoopAction::Terminate),
            AgentLoopState::Complete => Ok(LoopAction::Terminate),
            AgentLoopState::Idle => Ok(LoopAction::JumpToState(AgentLoopState::Processing)),
            _ => Ok(LoopAction::Continue),
        }
    }

    /// Check if execution should continue
    async fn should_continue(&self) -> bool {
        let state = self.state.read().await;
        state.should_continue && state.current_state != AgentLoopState::Complete
    }

    /// Check if maximum iterations exceeded
    async fn has_exceeded_iterations(&self) -> bool {
        let state = self.state.read().await;
        state.iteration_count >= state.max_iterations
    }

    /// Set error state
    async fn set_error(&self, message: String) {
        let mut state = self.state.write().await;
        state.current_state = AgentLoopState::Error;
        state.error_message = Some(message);
        state.should_continue = false;
    }

    /// Increment iteration count
    async fn increment_iteration(&self) {
        let mut state = self.state.write().await;
        state.iteration_count += 1;
    }

    /// Add a thought to the history
    async fn add_thought(&mut self, thought: OrchestratorThought) {
        self.thought_history.push_back(thought);
        // Keep only recent thoughts
        if self.thought_history.len() > 20 {
            self.thought_history.pop_front();
        }
    }

    /// Add a tool execution result to history
    async fn add_tool_result(&mut self, result: ToolExecutionResult) {
        self.tool_history.push_back(result);
        // Keep only recent results
        if self.tool_history.len() > 10 {
            self.tool_history.pop_front();
        }
    }

    /// Check if tool execution is required
    async fn requires_tool_execution(&self) -> bool {
        // Simple heuristic: if user input contains keywords suggesting tool use
        let input = self.context.user_input.to_lowercase();
        input.contains("create") || input.contains("modify") ||
        input.contains("search") || input.contains("find") ||
        input.contains("analyze") || input.contains("list")
    }

    /// Check if more information is needed
    async fn needs_more_information(&self) -> bool {
        // Check if confidence is below threshold
        if let Some(last_thought) = self.thought_history.back() {
            last_thought.confidence < self.config.min_confidence_threshold
        } else {
            true
        }
    }

    /// Execute tools using the agent
    async fn execute_tools<T>(
        &mut self,
        _agent: &T,
        session_id: &str,
        chunk_sender: &mpsc::UnboundedSender<StreamingAgentResponse>,
    ) -> Result<()>
    where
        T: StreamingStrandsAgent + ?Sized,
    {
        // This would integrate with the MCP tools
        let tool_result = ToolExecutionResult {
            tool_name: "ProjectSearch".to_string(),
            status: ToolExecutionStatus::Executing,
            progress: 0.5,
            message: "Searching project files...".to_string(),
            result: None,
            error: None,
            execution_time_ms: None,
        };

        self.send_tool_update(session_id, chunk_sender, tool_result.clone()).await?;

        // Simulate tool execution
        let completed_tool = ToolExecutionResult {
            status: ToolExecutionStatus::Completed,
            progress: 1.0,
            message: "Found 5 relevant files".to_string(),
            execution_time_ms: Some(1500),
            ..tool_result
        };

        self.add_tool_result(completed_tool.clone()).await;
        self.send_tool_update(session_id, chunk_sender, completed_tool).await?;

        Ok(())
    }

    /// Generate response content
    async fn generate_response_content<T>(
        &mut self,
        _agent: &T,
        session_id: &str,
        chunk_sender: &mpsc::UnboundedSender<StreamingAgentResponse>,
    ) -> Result<()>
    where
        T: StreamingStrandsAgent + ?Sized,
    {
        // Generate streaming response content
        let content = format!(
            "Based on my analysis of your request '{}', I've processed the information and am ready to provide assistance.",
            self.context.user_input
        );

        // Send content chunks
        for (i, chunk) in content.split_whitespace().enumerate() {
            if i > 0 {
                self.accumulated_content.push(' ');
            }
            self.accumulated_content.push_str(chunk);

            let _ = chunk_sender.send(StreamingAgentResponse {
                session_id: session_id.to_string(),
                chunk_id: i,
                content_chunk: Some(format!("{} ", chunk)),
                thought_process: None,
                tool_execution_result: None,
                is_complete: false,
                final_response: None,
                accumulated_content: Some(self.accumulated_content.clone()),
            });
        }

        Ok(())
    }

    /// Generate final output
    async fn generate_final_output(&self) -> Result<crate::strands_agent::AgentOutput> {
        Ok(crate::strands_agent::AgentOutput {
            content: self.accumulated_content.clone(),
            tokens_used: 150,
            execution_time_ms: 5000,
            metadata: serde_json::Map::from_iter([
                ("loop_id".to_string(), serde_json::Value::String(self.id.clone())),
                ("iterations".to_string(), serde_json::Value::Number(
                    serde_json::Number::from(self.state.read().await.iteration_count)
                )),
                ("thoughts_count".to_string(), serde_json::Value::Number(
                    serde_json::Number::from(self.thought_history.len())
                )),
                ("tools_executed".to_string(), serde_json::Value::Number(
                    serde_json::Number::from(self.tool_history.len())
                )),
            ]),
            cost_usd: Some(0.01),
            thoughts: self.thought_history.iter().cloned().collect(),
        })
    }

    /// Send state update to client
    async fn send_state_update(
        &self,
        session_id: &str,
        chunk_sender: &mpsc::UnboundedSender<StreamingAgentResponse>,
    ) -> Result<()> {
        let thought = OrchestratorThought {
            phase: format!("state_{}", self.get_state().await),
            insight: format!("Transitioned to {:?}", self.get_state().await),
            confidence: 1.0,
            timestamp: std::time::SystemTime::now(),
        };

        let _ = chunk_sender.send(StreamingAgentResponse {
            session_id: session_id.to_string(),
            chunk_id: 0,
            content_chunk: None,
            thought_process: Some(thought),
            tool_execution_result: None,
            is_complete: false,
            final_response: None,
            accumulated_content: None,
        });

        Ok(())
    }

    /// Send thought update to client
    async fn send_thought_update(
        &self,
        session_id: &str,
        chunk_sender: &mpsc::UnboundedSender<StreamingAgentResponse>,
        thought: OrchestratorThought,
    ) -> Result<()> {
        let _ = chunk_sender.send(StreamingAgentResponse {
            session_id: session_id.to_string(),
            chunk_id: 0,
            content_chunk: None,
            thought_process: Some(thought),
            tool_execution_result: None,
            is_complete: false,
            final_response: None,
            accumulated_content: None,
        });

        Ok(())
    }

    /// Send tool update to client
    async fn send_tool_update(
        &self,
        session_id: &str,
        chunk_sender: &mpsc::UnboundedSender<StreamingAgentResponse>,
        tool_result: ToolExecutionResult,
    ) -> Result<()> {
        let _ = chunk_sender.send(StreamingAgentResponse {
            session_id: session_id.to_string(),
            chunk_id: 0,
            content_chunk: None,
            thought_process: None,
            tool_execution_result: Some(tool_result),
            is_complete: false,
            final_response: None,
            accumulated_content: None,
        });

        Ok(())
    }

    /// Send completion message
    async fn send_completion(
        &self,
        session_id: &str,
        chunk_sender: &mpsc::UnboundedSender<StreamingAgentResponse>,
        final_output: &crate::strands_agent::AgentOutput,
    ) -> Result<()> {
        let _ = chunk_sender.send(StreamingAgentResponse {
            session_id: session_id.to_string(),
            chunk_id: 999,
            content_chunk: None,
            thought_process: None,
            tool_execution_result: None,
            is_complete: true,
            final_response: Some(final_output.clone()),
            accumulated_content: Some(final_output.content.clone()),
        });

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_agent_loop_state_transitions() {
        let context = AgentExecutionContext {
            user_input: "test input".to_string(),
            project_context: "test context".to_string(),
            previous_output: None,
            dynamic_context_provider: None,
            project_path: None,
        };

        let mut loop_agent = AgentLoop::new(context, None);

        assert_eq!(loop_agent.get_state().await, AgentLoopState::Idle);

        loop_agent.transition_to_state(AgentLoopState::Processing).await.unwrap();
        assert_eq!(loop_agent.get_state().await, AgentLoopState::Processing);

        assert_eq!(loop_agent.get_iteration_count().await, 0);
        loop_agent.increment_iteration().await;
        assert_eq!(loop_agent.get_iteration_count().await, 1);
    }

    #[test]
    fn test_agent_loop_config() {
        let config = AgentLoopConfig {
            max_iterations: 20,
            adaptive_reasoning: false,
            min_confidence_threshold: 0.9,
            auto_execute_tools: false,
            iteration_timeout_ms: 60000,
        };

        assert_eq!(config.max_iterations, 20);
        assert!(!config.adaptive_reasoning);
        assert_eq!(config.min_confidence_threshold, 0.9);
    }
}