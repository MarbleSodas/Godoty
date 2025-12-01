"""
Unified configuration interface for agents.

Re-exports all configuration classes for backward compatibility.
Import from here to get all config options:
    from agents.config import AgentConfig
"""
import os
from .model_config import ModelConfig
from .tool_config import ToolConfig
from .prompts import Prompts
from .validators import ConfigValidator


class AgentConfig(ModelConfig, ToolConfig, Prompts):
    """
    Unified agent configuration.
    
    Combines all configuration classes for easy access.
    Maintains backward compatibility with the original config.py interface.
    """
    
    @classmethod
    def validate(cls) -> dict:
        """
        Validate that required configuration is present and valid.
        
        Returns:
            Dict with validation results:
            - 'valid': bool indicating overall validity
            - 'warnings': list of warning messages
            - 'errors': list of error messages
            - 'godot_available': bool indicating if Godot tools can be used
            - 'mcp_available': bool indicating if MCP tools can be used
        """
        return ConfigValidator.validate_all(ModelConfig, ToolConfig)


# Validate configuration on module import, but be less noisy
validation_result = AgentConfig.validate()
if not validation_result['valid']:
    if os.getenv('GODOTY_ENVIRONMENT') != 'production':
        print("Agent configuration validation failed with errors:")
        for error in validation_result['errors']:
            print(f"  ERROR: {error}")

if validation_result['warnings'] and os.getenv('GODOTY_ENVIRONMENT') != 'production':
    print("Agent configuration validation warnings:")
    for warning in validation_result['warnings']:
        print(f"  WARNING: {warning}")

# Only log availability status in debug mode
if os.getenv('GODOTY_DEBUG'):
    print(f"Godot tools available: {validation_result['godot_available']}")
    print(f"MCP tools available: {validation_result['mcp_available']}")
