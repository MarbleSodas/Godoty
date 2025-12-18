"""Pydantic schemas for structured agent outputs.

Defines output schemas for Godoty agents that benefit from structured responses:
- CodeProposal: For Coder agent's code generation
- ArchitecturePlan: For Architect agent's planning
- ObservationReport: For Observer agent's analysis

These schemas are conditionally applied via TeamConfig.use_structured_output.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CodeFile(BaseModel):
    path: str = Field(
        ...,
        description="Relative path from project root (e.g., 'scripts/player.gd')",
    )
    content: str = Field(
        ...,
        description="Complete GDScript code with static typing and proper formatting",
    )
    action: str = Field(
        default="write",
        description="Action to perform: 'write' (create/overwrite), 'modify' (edit existing)",
    )


class CodeProposal(BaseModel):
    summary: str = Field(
        ...,
        description="One-sentence summary of what this code does",
    )
    files: list[CodeFile] = Field(
        ...,
        description="List of files to create or modify",
    )
    requires_hitl: bool = Field(
        default=True,
        description="Whether this change requires HITL confirmation (always True for file writes)",
    )
    reasoning: str = Field(
        ...,
        description="Brief explanation of design decisions and Godot best practices applied",
    )
    potential_issues: list[str] = Field(
        default_factory=list,
        description="Any potential issues or things to watch out for",
    )


class PlanTask(BaseModel):
    task_id: str = Field(
        ...,
        description="Short identifier like 'T1', 'T2', etc.",
    )
    description: str = Field(
        ...,
        description="What needs to be done in this task",
    )
    agent: str = Field(
        ...,
        description="Which agent should handle: 'Coder', 'Observer', or 'Lead'",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Task IDs that must complete before this one",
    )
    files_affected: list[str] = Field(
        default_factory=list,
        description="File paths that will be created or modified",
    )
    complexity: str = Field(
        default="medium",
        description="Complexity estimate: 'low', 'medium', 'high'",
    )


class ArchitecturePlan(BaseModel):
    feature_name: str = Field(
        ...,
        description="Name of the feature being planned",
    )
    overview: str = Field(
        ...,
        description="High-level overview of the implementation approach",
    )
    prerequisites: list[str] = Field(
        default_factory=list,
        description="Things that must exist before implementation (nodes, autoloads, etc.)",
    )
    tasks: list[PlanTask] = Field(
        ...,
        description="Ordered list of tasks to complete the feature",
    )
    files_to_create: list[str] = Field(
        default_factory=list,
        description="New files that will be created",
    )
    files_to_modify: list[str] = Field(
        default_factory=list,
        description="Existing files that need changes",
    )
    potential_challenges: list[str] = Field(
        default_factory=list,
        description="Possible challenges and how to address them",
    )
    estimated_complexity: str = Field(
        default="medium",
        description="Overall complexity: 'low', 'medium', 'high', 'very_high'",
    )


class SceneNodeInfo(BaseModel):
    name: str = Field(..., description="Node name in scene tree")
    type: str = Field(..., description="Node class type (e.g., 'CharacterBody2D')")
    children_count: int = Field(default=0, description="Number of child nodes")
    has_script: bool = Field(default=False, description="Whether node has an attached script")


class ObservationReport(BaseModel):
    summary: str = Field(
        ...,
        description="Brief summary of what was observed",
    )
    scene_info: str | None = Field(
        default=None,
        description="Current scene path and root node type",
    )
    key_nodes: list[SceneNodeInfo] = Field(
        default_factory=list,
        description="Important nodes found in the scene",
    )
    active_script: str | None = Field(
        default=None,
        description="Currently open script path, if any",
    )
    issues_detected: list[str] = Field(
        default_factory=list,
        description="Problems or potential issues found",
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Recommendations for improvement",
    )


__all__ = [
    "CodeFile",
    "CodeProposal",
    "PlanTask",
    "ArchitecturePlan",
    "SceneNodeInfo",
    "ObservationReport",
]
