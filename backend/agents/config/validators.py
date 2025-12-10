"""
Configuration validation utilities.

Handles validation of configuration values and provides useful error messages.
"""
import logging
import shutil
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


class ConfigValidator:
    """Validator for agent configuration."""
    
    @staticmethod
    def validate_model_config(model_config) -> Dict:
        """
        Validate model configuration.
        
        Returns:
            Dict with validation results
        """
        warnings = []
        errors = []
        
        # Check OpenRouter API Key
        api_key = model_config.get_openrouter_config().get("api_key")
        if not api_key:
            errors.append("OpenRouter API key is not set. Please configure it in Settings.")
        elif not api_key.startswith("sk-or-v1-"):
            warnings.append("OPENROUTER_API_KEY format looks incorrect. Should start with 'sk-or-v1-'.")
        
        # Validate model configuration
        if model_config.AGENT_TEMPERATURE < 0 or model_config.AGENT_TEMPERATURE > 2:
            warnings.append(f"AGENT_TEMPERATURE ({model_config.AGENT_TEMPERATURE}) should be between 0 and 2.")
        
        if model_config.AGENT_MAX_TOKENS < 100 or model_config.AGENT_MAX_TOKENS > 32000:
            warnings.append(f"AGENT_MAX_TOKENS ({model_config.AGENT_MAX_TOKENS}) should be between 100 and 32000.")
        
        return {"warnings": warnings, "errors": errors}
    
    @staticmethod
    def validate_tool_config(tool_config) -> Dict:
        """
        Validate tool configuration.

        Returns:
            Dict with validation results
        """
        warnings = []
        errors = []
        godot_available = True

        # Validate Godot configuration
        if tool_config.ENABLE_GODOT_TOOLS:
            if tool_config.GODOT_BRIDGE_PORT < 1 or tool_config.GODOT_BRIDGE_PORT > 65535:
                errors.append(f"GODOT_BRIDGE_PORT ({tool_config.GODOT_BRIDGE_PORT}) must be between 1 and 65535.")
                godot_available = False
            
            if tool_config.GODOT_CONNECTION_TIMEOUT <= 0:
                warnings.append(f"GODOT_CONNECTION_TIMEOUT ({tool_config.GODOT_CONNECTION_TIMEOUT}) should be positive.")
            
            if tool_config.GODOT_MAX_RETRIES < 0:
                warnings.append(f"GODOT_MAX_RETRIES ({tool_config.GODOT_MAX_RETRIES}) should be non-negative.")

        # Check if screenshot directory is accessible
        if tool_config.ENABLE_GODOT_TOOLS:
            try:
                screenshot_path = Path(tool_config.get_screenshot_dir())
                screenshot_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                warnings.append(f"Cannot create screenshot directory: {e}")
        
        return {
            "warnings": warnings,
            "errors": errors,
            "godot_available": tool_config.ENABLE_GODOT_TOOLS and godot_available
        }
    
    @classmethod
    def validate_all(cls, model_config, tool_config) -> Dict:
        """
        Validate all configuration.
        
        Returns:
            Dict with validation results:
            - 'valid': bool indicating overall validity
            - 'warnings': list of warning messages
            - 'errors': list of error messages
            - 'godot_available': bool indicating if Godot tools can be used
        """
        model_results = cls.validate_model_config(model_config)
        tool_results = cls.validate_tool_config(tool_config)
        
        all_warnings = model_results["warnings"] + tool_results["warnings"]
        all_errors = model_results["errors"] + tool_results["errors"]
        
        # Log validation results
        if all_errors:
            logger.error(f"Configuration validation failed with {len(all_errors)} error(s)")
            for error in all_errors:
                logger.error(f"  - {error}")
        
        if all_warnings:
            logger.warning(f"Configuration validation found {len(all_warnings)} warning(s)")
            for warning in all_warnings:
                logger.warning(f"  - {warning}")
        
        if not all_errors and not all_warnings:
            logger.info("Configuration validation passed successfully")
        
        return {
            'valid': len(all_errors) == 0,
            'warnings': all_warnings,
            'errors': all_errors,
            'godot_available': tool_results.get("godot_available", False)
        }
