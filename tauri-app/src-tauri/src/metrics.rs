use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::RwLock;

/// Comprehensive metrics for agentic workflow execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowMetrics {
    // Token usage
    pub total_tokens: u32,
    pub planning_tokens: u32,
    pub generation_tokens: u32,
    pub validation_tokens: u32,
    pub documentation_tokens: u32,

    // Cost tracking (in USD)
    #[serde(default)]
    pub total_cost_usd: f64,
    #[serde(default)]
    pub planning_cost_usd: f64,
    #[serde(default)]
    pub generation_cost_usd: f64,
    #[serde(default)]
    pub validation_cost_usd: f64,

    // Execution time (milliseconds)
    pub total_time_ms: u64,
    pub planning_time_ms: u64,
    pub generation_time_ms: u64,
    pub validation_time_ms: u64,
    pub kb_search_time_ms: u64,

    // Knowledge base metrics
    pub plugin_kb_queries: u32,
    pub docs_kb_queries: u32,
    pub total_docs_retrieved: u32,
    pub avg_relevance_score: f32,

    // Success metrics
    pub commands_generated: u32,
    pub commands_validated: u32,
    pub validation_errors: u32,
    pub validation_warnings: u32,
    pub reasoning_steps: u32,
    pub retry_attempts: u32,

    // Timestamps
    pub started_at: u64,
    pub completed_at: u64,

    // Request metadata
    pub request_id: String,
    pub user_input: String,
    pub success: bool,
    pub error_message: Option<String>,
}

impl WorkflowMetrics {
    pub fn new(request_id: String, user_input: String) -> Self {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();

        Self {
            total_tokens: 0,
            planning_tokens: 0,
            generation_tokens: 0,
            total_cost_usd: 0.0,
            planning_cost_usd: 0.0,
            generation_cost_usd: 0.0,
            validation_cost_usd: 0.0,
            validation_tokens: 0,
            documentation_tokens: 0,
            total_time_ms: 0,
            planning_time_ms: 0,
            generation_time_ms: 0,
            validation_time_ms: 0,
            kb_search_time_ms: 0,
            plugin_kb_queries: 0,
            docs_kb_queries: 0,
            total_docs_retrieved: 0,
            avg_relevance_score: 0.0,
            commands_generated: 0,
            commands_validated: 0,
            validation_errors: 0,
            validation_warnings: 0,
            reasoning_steps: 0,
            retry_attempts: 0,
            started_at: now,
            completed_at: now,
            request_id,
            user_input,
            success: false,
            error_message: None,
        }
    }

    pub fn finalize(&mut self, success: bool, error_message: Option<String>) {
        self.completed_at = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
        self.total_time_ms = (self.completed_at - self.started_at) * 1000;
        self.success = success;
        self.error_message = error_message;
    }
}

/// Metrics storage and aggregation
#[derive(Clone)]
pub struct MetricsStore {
    metrics: Arc<RwLock<Vec<WorkflowMetrics>>>,
    storage_path: PathBuf,
}

impl MetricsStore {
    pub fn new(storage_dir: PathBuf) -> Self {
        let mut storage_path = storage_dir;
        storage_path.push("workflow_metrics.json");

        Self {
            metrics: Arc::new(RwLock::new(Vec::new())),
            storage_path,
        }
    }

    /// Add metrics for a completed workflow
    pub async fn add_metrics(&self, metrics: WorkflowMetrics) -> Result<()> {
        let mut store = self.metrics.write().await;
        store.push(metrics);

        // Keep only last 1000 entries to prevent unbounded growth
        if store.len() > 1000 {
            let excess = store.len() - 1000;
            store.drain(0..excess);
        }

        Ok(())
    }

    /// Get all metrics
    pub async fn get_all_metrics(&self) -> Vec<WorkflowMetrics> {
        let store = self.metrics.read().await;
        store.clone()
    }

    /// Get metrics summary
    pub async fn get_summary(&self) -> MetricsSummary {
        let store = self.metrics.read().await;

        if store.is_empty() {
            return MetricsSummary::default();
        }

        let total_requests = store.len() as u32;
        let successful_requests = store.iter().filter(|m| m.success).count() as u32;
        let total_tokens: u32 = store.iter().map(|m| m.total_tokens).sum();
        let avg_time_ms = store.iter().map(|m| m.total_time_ms).sum::<u64>() / store.len() as u64;
        let total_commands = store.iter().map(|m| m.commands_generated).sum();

        MetricsSummary {
            total_requests,
            successful_requests,
            failed_requests: total_requests - successful_requests,
            success_rate: (successful_requests as f32 / total_requests as f32) * 100.0,
            total_tokens,
            avg_tokens_per_request: total_tokens / total_requests,
            avg_time_ms,
            total_commands_generated: total_commands,
        }
    }

    /// Save metrics to disk
    pub async fn save_to_disk(&self) -> Result<()> {
        let store = self.metrics.read().await;
        let json = serde_json::to_string_pretty(&*store)?;
        fs::write(&self.storage_path, json)?;
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct MetricsSummary {
    pub total_requests: u32,
    pub successful_requests: u32,
    pub failed_requests: u32,
    pub success_rate: f32,
    pub total_tokens: u32,
    pub avg_tokens_per_request: u32,
    pub avg_time_ms: u64,
    pub total_commands_generated: u32,
}
