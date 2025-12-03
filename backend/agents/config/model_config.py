"""
Model configuration for Godoty agent.

Handles all model-related settings including:
- Model ID from environment
- Temperature and token limits (hardcoded)
- OpenRouter configuration
- Metrics tracking configuration (hardcoded)
"""
import os
import sys
import logging
from typing import Dict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

class ModelConfig:
    """Configuration for Godoty agent model."""
    
    # Get model from environment with hardcoded fallback
    _model_id = os.getenv("DEFAULT_GODOTY_MODEL", "x-ai/grok-4.1-fast:free")
    _openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
    
    # Hardcoded Model Parameters
    AGENT_TEMPERATURE = 0.7
    AGENT_MAX_TOKENS = 4000
    
    # Hardcoded App Info
    APP_NAME = "Godoty"
    APP_URL = "http://localhost:8000"
    
    # Hardcoded Metrics Tracking Configuration
    ENABLE_METRICS_TRACKING = True
    METRICS_DB_PATH = ".godoty_metrics.db"
    ENABLE_PRECISE_COST_TRACKING = False
    COST_QUERY_DELAY_MS = 1000
    
    @classmethod
    def update_config(cls, model_id: str = None, api_key: str = None):
        """Update configuration dynamically."""
        if model_id:
            cls._model_id = model_id
        if api_key is not None:  # Allow empty string to clear key
            cls._openrouter_api_key = api_key

    @classmethod
    def get_model_config(cls) -> Dict:
        """Get model configuration as a dictionary."""
        return {
            "temperature": cls.AGENT_TEMPERATURE,
            "max_tokens": cls.AGENT_MAX_TOKENS,
            "model_id": cls._model_id
        }
    
    @classmethod
    def get_openrouter_config(cls) -> Dict:
        """Get OpenRouter configuration for Godoty agent."""
        return {
            "api_key": cls._openrouter_api_key,
            "model_id": cls._model_id,
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

    @classmethod
    def get_sessions_storage_dir(cls) -> str:
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
