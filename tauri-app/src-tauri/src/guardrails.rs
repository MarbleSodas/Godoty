use anyhow::{Result, anyhow};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::sync::Arc;
use tokio::sync::RwLock;
use std::time::{SystemTime, Duration};

/// Configuration for workflow guardrails
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GuardrailConfig {
    pub max_iterations: u32,
    pub max_tokens_per_request: u32,
    pub max_commands_per_request: u32,
    pub rate_limit_requests_per_min: u32,
    pub enable_command_validation: bool,
    pub allowed_command_types: Vec<String>,
    pub max_retry_attempts: u32,
}

impl Default for GuardrailConfig {
    fn default() -> Self {
        Self {
            max_iterations: 10,
            max_tokens_per_request: 10000,
            max_commands_per_request: 20,
            rate_limit_requests_per_min: 30,
            enable_command_validation: true,
            allowed_command_types: vec![
                "create_scene".to_string(),
                "create_node".to_string(),
                "modify_node".to_string(),
                "attach_script".to_string(),
                "create_script".to_string(),
                "delete_node".to_string(),
                "save_scene".to_string(),
                "open_scene".to_string(),
                "run_scene".to_string(),
            ],
            max_retry_attempts: 3,
        }
    }
}

/// Guardrail enforcement system
#[derive(Clone)]
pub struct Guardrails {
    pub config: GuardrailConfig,
    request_history: Arc<RwLock<Vec<RequestRecord>>>,
}

#[derive(Debug, Clone)]
struct RequestRecord {
    timestamp: SystemTime,
    tokens_used: u32,
}

impl Guardrails {
    pub fn new(config: GuardrailConfig) -> Self {
        Self {
            config,
            request_history: Arc::new(RwLock::new(Vec::new())),
        }
    }

    pub fn with_defaults() -> Self {
        Self::new(GuardrailConfig::default())
    }

    /// Check if request can proceed based on rate limits
    pub async fn check_rate_limit(&self) -> Result<()> {
        let mut history = self.request_history.write().await;
        
        // Remove records older than 1 minute
        let one_min_ago = SystemTime::now() - Duration::from_secs(60);
        history.retain(|record| record.timestamp > one_min_ago);
        
        // Check if we've exceeded the rate limit
        if history.len() >= self.config.rate_limit_requests_per_min as usize {
            return Err(anyhow!(
                "Rate limit exceeded: {} requests per minute",
                self.config.rate_limit_requests_per_min
            ));
        }
        
        Ok(())
    }

    /// Record a request for rate limiting
    pub async fn record_request(&self, tokens_used: u32) {
        let mut history = self.request_history.write().await;
        history.push(RequestRecord {
            timestamp: SystemTime::now(),
            tokens_used,
        });
    }

    /// Check if token budget is exceeded
    pub fn check_token_budget(&self, tokens_used: u32) -> Result<()> {
        if tokens_used > self.config.max_tokens_per_request {
            return Err(anyhow!(
                "Token budget exceeded: {} > {}",
                tokens_used,
                self.config.max_tokens_per_request
            ));
        }
        Ok(())
    }

    /// Check if iteration limit is exceeded
    pub fn check_iteration_limit(&self, current_iteration: u32) -> Result<()> {
        if current_iteration > self.config.max_iterations {
            return Err(anyhow!(
                "Iteration limit exceeded: {} > {}",
                current_iteration,
                self.config.max_iterations
            ));
        }
        Ok(())
    }

    /// Validate commands against allowed schema
    pub fn validate_commands(&self, commands: &[Value]) -> Result<ValidationResult> {
        if !self.config.enable_command_validation {
            return Ok(ValidationResult {
                valid: true,
                errors: Vec::new(),
                warnings: Vec::new(),
            });
        }

        let mut errors = Vec::new();
        let mut warnings = Vec::new();

        // Check command count
        if commands.len() > self.config.max_commands_per_request as usize {
            errors.push(format!(
                "Too many commands: {} > {}",
                commands.len(),
                self.config.max_commands_per_request
            ));
        }

        // Validate each command
        for (idx, cmd) in commands.iter().enumerate() {
            if let Some(cmd_type) = cmd.get("type").and_then(|v| v.as_str()) {
                // Check if command type is allowed
                if !self.config.allowed_command_types.contains(&cmd_type.to_string()) {
                    errors.push(format!(
                        "Command {}: Invalid command type '{}'",
                        idx + 1,
                        cmd_type
                    ));
                }

                // Validate command structure based on type
                match self.validate_command_structure(cmd_type, cmd) {
                    Ok(warns) => warnings.extend(warns),
                    Err(e) => errors.push(format!("Command {}: {}", idx + 1, e)),
                }
            } else {
                errors.push(format!("Command {}: Missing 'type' field", idx + 1));
            }
        }

        Ok(ValidationResult {
            valid: errors.is_empty(),
            errors,
            warnings,
        })
    }

    /// Validate command structure based on type
    fn validate_command_structure(&self, cmd_type: &str, cmd: &Value) -> Result<Vec<String>> {
        let warnings = Vec::new();

        match cmd_type {
            "create_node" | "modify_node" => {
                if cmd.get("node_name").is_none() {
                    return Err(anyhow!("Missing required field 'node_name'"));
                }
            }
            "attach_script" | "create_script" => {
                if cmd.get("script_path").is_none() {
                    return Err(anyhow!("Missing required field 'script_path'"));
                }
            }
            _ => {}
        }

        Ok(warnings)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ValidationResult {
    pub valid: bool,
    pub errors: Vec<String>,
    pub warnings: Vec<String>,
}

