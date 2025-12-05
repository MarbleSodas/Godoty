"""
Configuration manager for Godoty.

Handles persistent JSON configuration stored in ~/.godoty/config.json.
Provides a simple interface for getting/setting configuration values.
"""
import json
from typing import Dict, Any
from user_data import get_config_path


class ConfigManager:
    """Manages application configuration stored in JSON file."""

    def __init__(self):
        self.config_path = get_config_path()
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return self._get_defaults()
        else:
            return self._get_defaults()

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
            "app_settings": {}
        }

    @property
    def openrouter_api_key(self) -> str:
        """Get OpenRouter API key."""
        return self._config.get("openrouter_api_key", "")

    @openrouter_api_key.setter
    def openrouter_api_key(self, value: str):
        """Set OpenRouter API key."""
        self._config["openrouter_api_key"] = value
        self._save_config()

    @property
    def default_model(self) -> str:
        """Get default model."""
        return self._config.get("default_model", "anthropic/claude-opus-4.5")
    @default_model.setter
    def default_model(self, value: str):
        """Set default model."""
        self._config["default_model"] = value
        self._save_config()

    @property
    def is_configured(self) -> bool:
        """Check if application is fully configured."""
        return bool(self.openrouter_api_key.strip())

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        """Set configuration value by key."""
        self._config[key] = value
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