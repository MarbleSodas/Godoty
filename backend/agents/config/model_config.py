"""
Model configuration for agents.

Handles all model-related settings including:
- Model IDs and selections
- Temperature and token limits
- OpenRouter configuration
- Metrics tracking configuration
"""
import os
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class ModelConfig:
    """Configuration for agent models."""
    
    CONFIG_FILE = "agent_config.json"
    
    # Allowed Models
    ALLOWED_MODELS = {
        "Gemini 3 Pro": "google/gemini-3-pro-preview",
        "Grok 4.1 Fast": "x-ai/grok-4.1-fast",
        "Sonnet 4.5": "anthropic/claude-sonnet-4.5",
        "Haiku 4.5": "anthropic/claude-haiku-4.5",
        "Minimax M2": "minimax/minimax-m2",
        "GPT 5.1 Codex": "openai/gpt-5.1-codex",
        "GLM 4.6": "z-ai/glm-4.6"
    }
    
    # Default values
    _DEFAULT_PLANNING_MODEL = "x-ai/grok-4.1-fast"
    _DEFAULT_EXECUTOR_MODEL = "x-ai/grok-4.1-fast"
    
    FALLBACK_MODEL = "openai/gpt-4-turbo"
    EXECUTOR_FALLBACK_MODEL = "minimax/minimax-m2"
    
    # Instance variables for dynamic configuration
    _planning_model = os.getenv("DEFAULT_PLANNING_MODEL", _DEFAULT_PLANNING_MODEL)
    _executor_model = os.getenv("DEFAULT_EXECUTOR_MODEL", _DEFAULT_EXECUTOR_MODEL)
    _openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
    
    # Model Parameters
    AGENT_TEMPERATURE = float(os.getenv("AGENT_TEMPERATURE", "0.7"))
    AGENT_MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "4000"))
    
    # App Info
    APP_NAME = os.getenv("APP_NAME", "Godot-Assistant")
    APP_URL = os.getenv("APP_URL", "http://localhost:8000")
    
    # Metrics Tracking Configuration
    ENABLE_METRICS_TRACKING = os.getenv("ENABLE_METRICS_TRACKING", "true").lower() == "true"
    METRICS_DB_PATH = os.getenv("METRICS_DB_PATH", ".godoty_metrics.db")
    ENABLE_PRECISE_COST_TRACKING = os.getenv("ENABLE_PRECISE_COST_TRACKING", "false").lower() == "true"
    COST_QUERY_DELAY_MS = int(os.getenv("COST_QUERY_DELAY_MS", "1000"))
    
    @classmethod
    def load_config(cls):
        """Load configuration from file if it exists."""
        if os.path.exists(cls.CONFIG_FILE):
            try:
                with open(cls.CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    cls._planning_model = config.get("planning_model", cls._planning_model)
                    cls._executor_model = config.get("executor_model", cls._executor_model)
                    cls._openrouter_api_key = config.get("openrouter_api_key", cls._openrouter_api_key)
                    logger.info(f"Loaded configuration from {cls.CONFIG_FILE}")
            except Exception as e:
                logger.error(f"Error loading configuration: {e}")

    @classmethod
    def save_config(cls):
        """Save current configuration to file."""
        config = {
            "planning_model": cls._planning_model,
            "executor_model": cls._executor_model,
            "openrouter_api_key": cls._openrouter_api_key
        }
        try:
            with open(cls.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info(f"Saved configuration to {cls.CONFIG_FILE}")
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")

    @classmethod
    def update_config(cls, planning_model: Optional[str] = None, executor_model: Optional[str] = None, api_key: Optional[str] = None):
        """Update configuration dynamically."""
        if planning_model:
            cls._planning_model = planning_model
        if executor_model:
            cls._executor_model = executor_model
        if api_key is not None: # Allow empty string to clear key
            cls._openrouter_api_key = api_key
        
        cls.save_config()

    @classmethod
    def get_model_config(cls) -> Dict:
        """Get model configuration as a dictionary."""
        return {
            "temperature": cls.AGENT_TEMPERATURE,
            "max_tokens": cls.AGENT_MAX_TOKENS,
            "planning_model": cls._planning_model,
            "executor_model": cls._executor_model,
            "allowed_models": cls.ALLOWED_MODELS
        }
    
    @classmethod
    def get_openrouter_config(cls) -> Dict:
        """Get OpenRouter configuration for planning agent."""
        return {
            "api_key": cls._openrouter_api_key,
            "model_id": cls._planning_model,
            "app_name": cls.APP_NAME,
            "app_url": cls.APP_URL
        }
    
    @classmethod
    def get_executor_openrouter_config(cls) -> Dict:
        """Get OpenRouter configuration for executor agent."""
        return {
            "api_key": cls._openrouter_api_key,
            "model_id": cls._executor_model,
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

# Load config on module import
ModelConfig.load_config()
