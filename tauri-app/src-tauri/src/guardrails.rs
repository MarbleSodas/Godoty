use anyhow::{anyhow, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::sync::Arc;
use std::time::{Duration, SystemTime};
use tokio::sync::RwLock;

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
            max_commands_per_request: 1, // Changed to 1 for iterative execution
            rate_limit_requests_per_min: 30,
            enable_command_validation: true,
            allowed_command_types: vec![
                // Editor/scene manipulation
                "create_node".to_string(),
                "delete_node".to_string(),
                "modify_node".to_string(),
                "attach_script".to_string(),
                "capture_screenshot".to_string(),
                "create_scene".to_string(),
                "open_scene".to_string(),
                "get_scene_info".to_string(),
                "inspect_scene_file".to_string(),
                "get_current_scene_detailed".to_string(),
                // Visual context and debugging
                "capture_visual_context".to_string(),
                "get_visual_snapshot".to_string(),
                "enable_auto_visual_capture".to_string(),
                "disable_auto_visual_capture".to_string(),
                "start_debug_capture".to_string(),
                "stop_debug_capture".to_string(),
                "clear_debug_output".to_string(),
                "get_debug_output".to_string(),
                // Editor UI / palette and selection
                "select_nodes".to_string(),
                "focus_node".to_string(),
                "play".to_string(),
                "add_command_palette_command".to_string(),
                // Search
                "search_nodes_by_type".to_string(),
                "search_nodes_by_name".to_string(),
                "search_nodes_by_group".to_string(),
                "search_nodes_by_script".to_string(),
                // Structure editing
                "duplicate_node".to_string(),
                "reparent_node".to_string(),
                "rename_node".to_string(),
                "add_to_group".to_string(),
                "remove_from_group".to_string(),
                // MCP Desktop Commander: filesystem/code editing via MCP server
                "desktop_commander".to_string(),

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
    _tokens_used: u32,
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
            _tokens_used: tokens_used,
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

        // Check command count - now just a warning since we execute iteratively
        // max_commands_per_request is set to 1 for iterative execution
        if commands.len() > self.config.max_commands_per_request as usize {
            warnings.push(format!(
                "Note: {} commands provided, but iterative execution processes one at a time",
                commands.len()
            ));
        }

        // Validate each command
        for (idx, cmd) in commands.iter().enumerate() {
            if let Some(action) = cmd.get("action").and_then(|v| v.as_str()) {
                // Check if action is allowed
                if !self
                    .config
                    .allowed_command_types
                    .contains(&action.to_string())
                {
                    errors.push(format!("Command {}: Invalid action '{}'", idx + 1, action));
                }

                // Validate command structure based on action
                match self.validate_command_structure(action, cmd) {
                    Ok(warns) => warnings.extend(warns),
                    Err(e) => errors.push(format!("Command {}: {}", idx + 1, e)),
                }
            } else {
                errors.push(format!("Command {}: Missing 'action' field", idx + 1));
            }
        }

        Ok(ValidationResult {
            valid: errors.is_empty(),
            errors,
            warnings,
        })
    }

    /// Validate command structure based on action
    fn validate_command_structure(&self, action: &str, cmd: &Value) -> Result<Vec<String>> {
        let warnings = Vec::new();

        match action {
            // Scene/node creation
            "create_node" => {
                if cmd.get("type").is_none() {
                    return Err(anyhow!("Missing required field 'type'"));
                }
                if cmd.get("name").is_none() {
                    return Err(anyhow!("Missing required field 'name'"));
                }
            }
            "create_scene" => {
                if cmd.get("name").is_none() {
                    return Err(anyhow!("Missing required field 'name'"));
                }
                if cmd.get("root_type").is_none() {
                    return Err(anyhow!("Missing required field 'root_type'"));
                }
            }
            // Modification/deletion
            "modify_node" => {
                if cmd.get("path").is_none() {
                    return Err(anyhow!("Missing required field 'path'"));
                }
                if cmd.get("properties").is_none() {
                    return Err(anyhow!("Missing required field 'properties'"));
                }
            }
            "delete_node" => {
                if cmd.get("path").is_none() {
                    return Err(anyhow!("Missing required field 'path'"));
                }
            }
            // Scripts
            "attach_script" => {
                if cmd.get("path").is_none() {
                    return Err(anyhow!("Missing required field 'path'"));
                }
                if cmd.get("script_content").is_none() {
                    return Err(anyhow!("Missing required field 'script_content'"));
                }
            }
            // Editor actions / selection
            "open_scene" => {
                if cmd.get("path").is_none() {
                    return Err(anyhow!("Missing required field 'path'"));
                }
            }
            "select_nodes" => {
                if cmd.get("paths").is_none() {
                    return Err(anyhow!("Missing required field 'paths'"));
                }
            }
            "focus_node" => {
                if cmd.get("path").is_none() {
                    return Err(anyhow!("Missing required field 'path'"));
                }
            }
            // Structure editing
            "duplicate_node" => {
                if cmd.get("path").is_none() {
                    return Err(anyhow!("Missing required field 'path'"));
                }
            }
            "reparent_node" => {
                if cmd.get("path").is_none() {
                    return Err(anyhow!("Missing required field 'path'"));
                }
                if cmd.get("new_parent").is_none() {
                    return Err(anyhow!("Missing required field 'new_parent'"));
                }
            }
            "rename_node" => {
                if cmd.get("path").is_none() {
                    return Err(anyhow!("Missing required field 'path'"));
                }
                if cmd.get("new_name").is_none() {
                    return Err(anyhow!("Missing required field 'new_name'"));
                }
            }
            // Search
            "search_nodes_by_type" => {
                if cmd.get("type").is_none() {
                    return Err(anyhow!("Missing required field 'type'"));
                }
            }
            "search_nodes_by_name" => {
                if cmd.get("name").is_none() {
                    return Err(anyhow!("Missing required field 'name'"));
                }
            }
            "search_nodes_by_group" => {
                if cmd.get("group").is_none() {
                    return Err(anyhow!("Missing required field 'group'"));
                }
            }
            // Desktop Commander MCP
            "desktop_commander" => {
                let tool = cmd
                    .get("tool")
                    .and_then(|v| v.as_str())
                    .ok_or_else(|| anyhow!("Missing required field 'tool'"))?;
                // Whitelist tools for phase 1 integration
                let allowed_tools = [
                    "read_file",
                    "write_file",
                    "edit_block",
                    "create_directory",
                    "list_directory",
                    "move_file",
                    "start_search",
                    "get_more_search_results",
                    "stop_search",
                    "get_file_info",
                ];
                if !allowed_tools.contains(&tool) {
                    return Err(anyhow!(format!(
                        "Unsupported desktop_commander tool '{}'",
                        tool
                    )));
                }
                if !cmd.get("args").map(|v| v.is_object()).unwrap_or(false) {
                    return Err(anyhow!("Missing required object field 'args'"));
                }
            }
            // Others either have no additional required fields beyond 'action' or are lenient
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

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn validate_create_node_ok() {
        let guard = Guardrails::with_defaults();
        let cmds = vec![json!({
            "action": "create_node",
            "type": "Panel",
            "name": "Root",
            "parent": null
        })];
        let res = guard.validate_commands(&cmds).unwrap();
        assert!(res.valid, "expected valid, got errors: {:?}", res.errors);
    }

    #[test]
    fn validate_missing_action_fails() {
        let guard = Guardrails::with_defaults();
        let cmds = vec![json!({
            "type": "Panel",
            "name": "Root"
        })];
        let res = guard.validate_commands(&cmds).unwrap();
        assert!(!res.valid);
        assert!(res.errors.iter().any(|e| e.contains("Missing 'action'")));
    }

    #[test]
    fn validate_attach_script_ok() {
        let guard = Guardrails::with_defaults();
        let cmds = vec![json!({
            "action": "attach_script",
            "path": "/Root/Node",
            "script_content": "extends Node\nfunc _ready():\n    pass",
        })];
        let res = guard.validate_commands(&cmds).unwrap();
        assert!(res.valid, "expected valid, got errors: {:?}", res.errors);
    }

    // Desktop Commander tests
    #[test]
    fn validate_desktop_commander_write_file_ok() {
        let guard = Guardrails::with_defaults();
        let cmds = vec![json!({
            "action": "desktop_commander",
            "tool": "write_file",
            "args": {"path": "godot-plugin/addons/godoty/new_script.gd", "content": "extends Node"}
        })];
        let res = guard.validate_commands(&cmds).unwrap();
        assert!(res.valid, "expected valid, got errors: {:?}", res.errors);
    }

    #[test]
    fn validate_desktop_commander_unknown_tool_fails() {
        let guard = Guardrails::with_defaults();
        let cmds = vec![json!({
            "action": "desktop_commander",
            "tool": "delete_everything",
            "args": {}
        })];
        let res = guard.validate_commands(&cmds).unwrap();
        assert!(!res.valid);
        assert!(res.errors.iter().any(|e| e.contains("Unsupported desktop_commander tool")));
    }

    #[test]
    fn validate_desktop_commander_missing_args_fails() {
        let guard = Guardrails::with_defaults();
        let cmds = vec![json!({
            "action": "desktop_commander",
            "tool": "write_file"
        })];
        let res = guard.validate_commands(&cmds).unwrap();
        assert!(!res.valid);
        assert!(res.errors.iter().any(|e| e.contains("Missing required object field 'args'")));
    }
}
