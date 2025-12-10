"""
Model configuration for Godoty agent.

Handles all model-related settings including:
- Model ID from persistent configuration
- Temperature and token limits (hardcoded)
- OpenRouter configuration
- Metrics tracking configuration (hardcoded)
"""
import os
import sys
import logging
from pathlib import Path
from typing import Dict
from config_manager import get_config

logger = logging.getLogger(__name__)


class ModelConfig:
    """Configuration for Godoty agent model."""

    def __init__(self):
        self.config_manager = get_config()
        self._migrate_from_env_if_needed()

    def _migrate_from_env_if_needed(self):
        """Auto-migrate from .env file if config is empty (developer convenience only)."""
        # Only migrate if no API key is configured
        if not self.config_manager.openrouter_api_key.strip():
            try:
                # Only attempt if .env exists (developer mode)
                env_path = Path(__file__).parent.parent.parent / '.env'
                if not env_path.exists():
                    logger.debug("No .env file found - skipping migration")
                    return

                # Try to import dotenv (may not be installed for end users)
                try:
                    from dotenv import load_dotenv
                    load_dotenv(env_path)
                except ImportError:
                    logger.debug("python-dotenv not installed - skipping .env migration")
                    return

                api_key = os.getenv('OPENROUTER_API_KEY', '')
                model = os.getenv('DEFAULT_GODOTY_MODEL', 'anthropic/claude-3-opus-4.5')

                if api_key.strip():
                    self.config_manager.openrouter_api_key = api_key
                    self.config_manager.default_model = model
                    self.config_manager._save_config()
                    logger.info("Migrated configuration from .env to persistent storage")
            except Exception as e:
                logger.debug(f"No .env migration needed: {e}")

    @property
    def _model_id(self):
        return self.config_manager.default_model

    @property
    def _openrouter_api_key(self):
        return self.config_manager.openrouter_api_key
    
    # Hardcoded Model Parameters
    AGENT_TEMPERATURE = 0.7
    AGENT_MAX_TOKENS = 4000
    
    # Task-based Temperature Settings
    # Lower temperature for code generation to ensure consistency
    # Higher temperature for planning/discussion for creativity
    TEMPERATURE_BY_TASK = {
        "code_generation": 0.3,    # Precise, deterministic code output
        "code_modification": 0.3,  # Precise edits
        "planning": 0.7,           # Creative problem-solving
        "learning": 0.7,           # Exploratory research
        "execution": 0.5,          # Balanced for tool use
        "default": 0.7,            # Fallback
    }
    
    @classmethod
    def get_temperature_for_task(cls, task_type: str = "default") -> float:
        """Get appropriate temperature for a task type."""
        return cls.TEMPERATURE_BY_TASK.get(task_type, cls.TEMPERATURE_BY_TASK["default"])
    
    # Hardcoded App Info
    APP_NAME = "Godoty"
    APP_URL = "http://localhost:8000"
    
    # Hardcoded Metrics Tracking Configuration
    ENABLE_METRICS_TRACKING = True
    METRICS_DB_PATH = ".godoty_metrics.db"
    ENABLE_PRECISE_COST_TRACKING = False
    COST_QUERY_DELAY_MS = 1000
    
    # Web Search Capable Models (support :online suffix via OpenRouter)
    # These models are known to work well with OpenRouter's web search feature
    WEB_SEARCH_CAPABLE_MODELS = [
        # Anthropic models
        "anthropic/claude-sonnet-4",
        "anthropic/claude-opus-4", 
        "anthropic/claude-haiku-4",
        # OpenAI models
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "openai/gpt-4-turbo",
        # Google models
        "google/gemini-2.0-flash-001",
        "google/gemini-pro-1.5",
        # xAI models
        "x-ai/grok-2",
        "x-ai/grok-2-mini",
        # DeepSeek
        "deepseek/deepseek-chat",
        # Meta
        "meta-llama/llama-3.3-70b-instruct",
    ]
    
    @classmethod
    def get_allowed_models(cls) -> list:
        """Get list of models that support web search (global restriction)."""
        return cls.WEB_SEARCH_CAPABLE_MODELS.copy()
    
    def update_config(self, model_id: str = None, api_key: str = None):
        """Update configuration dynamically and persist to storage."""
        if model_id:
            self.config_manager.default_model = model_id
        if api_key is not None:  # Allow empty string to clear key
            self.config_manager.openrouter_api_key = api_key

        # Save to persistent storage
        self.config_manager._save_config()
        logger.info("Configuration updated and saved")

    def get_model_config(self) -> Dict:
        """Get model configuration as a dictionary."""
        return {
            "temperature": self.AGENT_TEMPERATURE,
            "max_tokens": self.AGENT_MAX_TOKENS,
            "model_id": self._model_id
        }

    def get_openrouter_config(self) -> Dict:
        """Get OpenRouter configuration for Godoty agent."""
        return {
            "api_key": self._openrouter_api_key,
            "model_id": self._model_id,
            "app_name": self.APP_NAME,
            "app_url": self.APP_URL
        }

    def get_metrics_config(self) -> Dict:
        """Get metrics tracking configuration."""
        return {
            "enabled": self.ENABLE_METRICS_TRACKING,
            "db_path": self.METRICS_DB_PATH,
            "precise_cost_tracking": self.ENABLE_PRECISE_COST_TRACKING,
            "cost_query_delay_ms": self.COST_QUERY_DELAY_MS
        }

    def get_sessions_storage_dir(self) -> str:
        """Get persistent storage directory for FileSessionManager sessions."""
        app_name = "Godoty"

        if sys.platform == "win32":
            base_path = os.environ.get("APPDATA") or os.path.expanduser("~/AppData/Roaming")
        elif sys.platform == "darwin":
            base_path = os.path.expanduser("~/Library/Application Support")
        else:  # linux
            base_path = os.path.expanduser("~/.local/share")

        app_dir = os.path.join(base_path, app_name)
        sessions_dir = os.path.join(app_dir, "sessions")
        os.makedirs(sessions_dir, exist_ok=True)

        return sessions_dir

# Create a singleton instance for backward compatibility
_model_config_instance = None

# Save references to original instance methods before overwriting
_orig_get_model_config = ModelConfig.get_model_config
_orig_get_openrouter_config = ModelConfig.get_openrouter_config
_orig_get_metrics_config = ModelConfig.get_metrics_config
_orig_get_sessions_storage_dir = ModelConfig.get_sessions_storage_dir
_orig_update_config = ModelConfig.update_config


def get_model_config():
    """Get or create global ModelConfig instance."""
    global _model_config_instance
    if _model_config_instance is None:
        _model_config_instance = ModelConfig()
    return _model_config_instance


# Backward compatibility: expose class methods that delegate to singleton instance
# These allow calling ModelConfig.method() without instantiating
ModelConfig.get_model_config = staticmethod(lambda: _orig_get_model_config(get_model_config()))
ModelConfig.get_openrouter_config = staticmethod(lambda: _orig_get_openrouter_config(get_model_config()))
ModelConfig.get_metrics_config = staticmethod(lambda: _orig_get_metrics_config(get_model_config()))
ModelConfig.get_sessions_storage_dir = staticmethod(lambda: _orig_get_sessions_storage_dir(get_model_config()))
ModelConfig.update_config = staticmethod(lambda model_id=None, api_key=None: _orig_update_config(get_model_config(), model_id, api_key))
