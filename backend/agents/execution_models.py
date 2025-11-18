"""
Simplified Execution Models for Godot Assistant.

This module provides basic data structures for executing plans from the planning agent.
Works directly with structured data instead of parsing text.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """Simple execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ToolCall(BaseModel):
    """Represents a tool call."""
    name: str = Field(..., description="Tool name")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Tool parameters")


class ExecutionStep(BaseModel):
    """Simple execution step."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field(..., description="Step title")
    description: str = Field(..., description="Step description")
    tool_calls: List[ToolCall] = Field(default_factory=list, description="Tools to execute")
    depends_on: List[str] = Field(default_factory=list, description="Step dependencies")


class ExecutionPlan(BaseModel):
    """Simple execution plan from planning agent."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field(..., description="Plan title")
    description: str = Field(..., description="Plan description")
    steps: List[ExecutionStep] = Field(..., description="Execution steps")


class ExecutionResult(BaseModel):
    """Result of step execution."""
    step_id: str
    status: ExecutionStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    output: Optional[str] = None
    error: Optional[str] = None


class ExecutionState(BaseModel):
    """Current execution state."""
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    plan: ExecutionPlan
    status: ExecutionStatus = ExecutionStatus.PENDING
    current_step: Optional[str] = None
    completed_steps: List[str] = Field(default_factory=list)
    failed_steps: List[str] = Field(default_factory=list)
    step_results: Dict[str, ExecutionResult] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=datetime.now)


class StreamEvent(BaseModel):
    """Simple stream event."""
    type: str
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)