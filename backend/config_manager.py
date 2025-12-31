"""
Configuration manager for Godoty.

Handles persistent JSON configuration stored in ~/.godoty/config.json.
Provides a simple interface for getting/setting configuration values.
"""
import json
import os
import time
from threading import Lock
from typing import Dict, Any
from dotenv import load_dotenv
from user_data import get_config_path


class ConfigManager:
    """Manages application configuration stored in JSON file with caching support."""

    def __init__(self):
        # Load .env from user data directory
        user_data_dir = os.path.dirname(get_config_path())
        env_path = os.path.join(user_data_dir, '.env')
        load_dotenv(env_path)
        self.config_path = get_config_path()

        # Cache-related instance variables
        self._cache_lock = Lock()
        self._cache_timestamp = 0
        self._cache_ttl = 60  # 60 seconds cache TTL
        self._config_cache = None

        self._config = self._load_config()

    def _invalidate_cache(self):
        """Invalidate the configuration cache."""
        with self._cache_lock:
            self._cache_timestamp = 0

    def _is_cache_valid(self) -> bool:
        """Check if the cache is still valid."""
        return time.time() - self._cache_timestamp < self._cache_ttl

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file with caching."""
        with self._cache_lock:
            # Check if cache is still valid
            if self._config_cache is not None and self._is_cache_valid():
                return self._config_cache

            # Load from file
            if self.config_path.exists():
                try:
                    with open(self.config_path, 'r', encoding='utf-8') as f:
                        self._config_cache = json.load(f)
                        self._cache_timestamp = time.time()
                        return self._config_cache
                except (json.JSONDecodeError, IOError):
                    pass

            # Fallback to defaults
            self._config_cache = self._get_defaults()
            self._cache_timestamp = time.time()
            return self._config_cache

    def _save_config(self):
        """Save configuration to JSON file."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except IOError:
            pass

    def _get_defaults(self) -> Dict[str, Any]:
        """Get default configuration values."""
        return {
            "openrouter_api_key": "",
            "default_model": "anthropic/claude-3-opus-4.5",
            "app_settings": {},
            # Environment variables override defaults
            "supabase_url": os.getenv("SUPABASE_URL", "https://skwlndaqqkxushqkhlgg.supabase.co"),
            "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNrd2xuZGFxcWt4dXNocWtobGdnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjUwNTA0OTYsImV4cCI6MjA4MDYyNjQ5Nn0.1d_H4e897JV2szNBMY7lzhicu8Pa0xIcyqm5WgVUedM")
        }

    @property
    def openrouter_api_key(self) -> str:
        """Get OpenRouter API key."""
        return self._config.get("openrouter_api_key", "")

    @openrouter_api_key.setter
    def openrouter_api_key(self, value: str):
        """Set OpenRouter API key."""
        self._config["openrouter_api_key"] = value
        self._invalidate_cache()
        self._save_config()

    @property
    def default_model(self) -> str:
        """Get default model."""
        return self._config.get("default_model", "anthropic/claude-opus-4.5")
    @default_model.setter
    def default_model(self, value: str):
        """Set default model."""
        self._config["default_model"] = value
        self._invalidate_cache()
        self._save_config()

    # Hardcoded Supabase configuration (public values safe for client apps)
    SUPABASE_URL = "https://skwlndaqqkxushqkhlgg.supabase.co"
    SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNrd2xuZGFxcWt4dXNocWtobGdnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjUwNTA0OTYsImV4cCI6MjA4MDYyNjQ5Nn0.1d_H4e897JV2szNBMY7lzhicu8Pa0xIcyqm5WgVUedM"

    @property
    def supabase_url(self) -> str:
        """Get Supabase URL from environment, config, or hardcoded default."""
        return os.getenv("SUPABASE_URL") or self._config.get("supabase_url", self.SUPABASE_URL)

    @property
    def supabase_anon_key(self) -> str:
        """Get Supabase anon key from environment, config, or hardcoded default."""
        return os.getenv("SUPABASE_ANON_KEY") or self._config.get("supabase_anon_key", self.SUPABASE_ANON_KEY)

    @property
    def is_configured(self) -> bool:
        """Check if application is fully configured."""
        return bool(self.openrouter_api_key.strip())

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key, falling back to defaults."""
        # For Supabase config, check environment first, then config, then hardcoded
        if key == "supabase_url":
            return os.getenv("SUPABASE_URL") or self._config.get("supabase_url", self.SUPABASE_URL)
        if key == "supabase_anon_key":
            return os.getenv("SUPABASE_ANON_KEY") or self._config.get("supabase_anon_key", self.SUPABASE_ANON_KEY)
        # For other keys, check config then defaults
        if key in self._config:
            return self._config[key]
        defaults = self._get_defaults()
        if key in defaults:
            return defaults[key]
        return default

    def set(self, key: str, value: Any):
        """Set configuration value by key and invalidate cache."""
        self._config[key] = value
        self._invalidate_cache()
        self._save_config()

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values."""
        return self._config.copy()

    def reset_to_defaults(self):
        """Reset configuration to defaults."""
        self._config = self._get_defaults()
        self._save_config()


# Global config manager instance
_config_manager = None


def get_config() -> ConfigManager:
    """Get the global configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager