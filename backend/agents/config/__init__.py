"""
Unified configuration interface for agents.

Re-exports all configuration classes for backward compatibility.
Import from here to get all config options:
    from agents.config import AgentConfig
"""
from .model_config import ModelConfig
from .tool_config import ToolConfig
from .prompts import Prompts
from .planning_prompts import PlanningPrompts
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
        """
        return ConfigValidator.validate_all(ModelConfig, ToolConfig)


# Validate configuration on module import
validation_result = AgentConfig.validate()
if not validation_result['valid']:
    print("Agent configuration validation failed with errors:")
    for error in validation_result['errors']:
        print(f"  ERROR: {error}")

if validation_result['warnings']:
    print("Agent configuration validation warnings:")
    for warning in validation_result['warnings']:
        print(f"  WARNING: {warning}")

# Log availability status
print(f"Godot tools available: {validation_result['godot_available']}")
