"""
Model configuration for agents.

Handles all model-related settings including:
- Model IDs and selections
- Temperature and token limits
- OpenRouter configuration
- Metrics tracking configuration
"""
import os
from typing import Dict


class ModelConfig:
    """Configuration for agent models."""
    
    # Planning Agent Models
    DEFAULT_PLANNING_MODEL = os.getenv("DEFAULT_PLANNING_MODEL", "openai/gpt-4-turbo")
    FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "anthropic/claude-3.5-sonnet")
    
    # Executor Agent Models
    DEFAULT_EXECUTOR_MODEL = os.getenv("DEFAULT_EXECUTOR_MODEL", "openrouter/sherlock-dash-alpha")
    EXECUTOR_FALLBACK_MODEL = os.getenv("EXECUTOR_FALLBACK_MODEL", "minimax/minimax-m2")
    
    # Model Parameters
    AGENT_TEMPERATURE = float(os.getenv("AGENT_TEMPERATURE", "0.7"))
    AGENT_MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "4000"))
    
    # OpenRouter API Configuration
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    APP_NAME = os.getenv("APP_NAME", "Godot-Assistant ")
    APP_URL = os.getenv("APP_URL", "http://localhost:8000")
    
    # Metrics Tracking Configuration
    ENABLE_METRICS_TRACKING = os.getenv("ENABLE_METRICS_TRACKING", "true").lower() == "true"
    METRICS_DB_PATH = os.getenv("METRICS_DB_PATH", ".godoty_metrics.db")
    ENABLE_PRECISE_COST_TRACKING = os.getenv("ENABLE_PRECISE_COST_TRACKING", "false").lower() == "true"
    COST_QUERY_DELAY_MS = int(os.getenv("COST_QUERY_DELAY_MS", "1000"))
    
    @classmethod
    def get_model_config(cls) -> Dict:
        """Get model configuration as a dictionary."""
        return {
            "temperature": cls.AGENT_TEMPERATURE,
            "max_tokens": cls.AGENT_MAX_TOKENS
        }
    
    @classmethod
    def get_openrouter_config(cls) -> Dict:
        """Get OpenRouter configuration for planning agent."""
        return {
            "api_key": cls.OPENROUTER_API_KEY,
            "model_id": cls.DEFAULT_PLANNING_MODEL,
            "app_name": cls.APP_NAME,
            "app_url": cls.APP_URL
        }
    
    @classmethod
    def get_executor_openrouter_config(cls) -> Dict:
        """Get OpenRouter configuration for executor agent."""
        return {
            "api_key": cls.OPENROUTER_API_KEY,
            "model_id": cls.DEFAULT_EXECUTOR_MODEL,
            "app_name": cls.APP_NAME,
            "app_url": cls.APP_URL
        }
    
    @classmethod
    def get_metrics_config(cls) -> Dict:
        """Get metrics tracking configuration."""
        return {
            "enabled": cls.ENABLE_METRICS_TRACKING,
            "db_path": cls.METRICS_DB_PATH,
            "precise_cost_tracking": cls.ENABLE_PRECISE_COST_TRACKING,
            "cost_query_delay_ms": cls.COST_QUERY_DELAY_MS
        }
