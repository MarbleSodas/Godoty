"""Better Agents scenario tests for Godoty.

These tests validate agent behavior through end-to-end scenarios,
ensuring consistent and predictable agent responses.

Test Categories:
- test_code_generation.py: GDScript code quality scenarios
- test_scene_analysis.py: Observer perception scenarios
- test_feature_planning.py: Architect planning scenarios
- test_delegation_routing.py: Lead routing decisions
- test_protocol.py: Protocol communication scenarios
"""

from .conftest import (
    assert_gdscript_quality,
    calculate_quality_score,
    MockTeamResponse,
)

__all__ = [
    "assert_gdscript_quality",
    "calculate_quality_score",
    "MockTeamResponse",
]
