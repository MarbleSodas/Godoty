"""
SQLAlchemy ORM models for metrics tracking.

Defines database models for message, session, and project-level metrics.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class ApiCallMetrics(Base):
    """
    API Call-level metrics model.

    Stores token usage and cost information for individual OpenRouter API calls.
    Replaces the previous MessageMetrics to strictly track API usage.
    """
    __tablename__ = "api_call_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # We use generation_id or a UUID as the unique identifier for the call
    call_id = Column(String, unique=True, nullable=False, index=True) 
    session_id = Column(String, ForeignKey("session_metrics.session_id", ondelete="CASCADE"), index=True)
    project_id = Column(String, ForeignKey("project_metrics.project_id", ondelete="CASCADE"), index=True)

    # Context metadata
    message_id = Column(String, nullable=True, index=True) # Link to logical chat message if applicable
    agent_type = Column(String, nullable=True) 
    model_id = Column(String, nullable=False, index=True)

    # Token counts
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)

    # Cost information (in USD)
    estimated_cost = Column(Float, nullable=False, default=0.0)
    actual_cost = Column(Float, nullable=True)

    # OpenRouter generation ID
    generation_id = Column(String, index=True)

    # Timing information
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Additional metadata
    stop_reason = Column(String)
    tool_calls_count = Column(Integer, default=0)

    # Tool error tracking
    tool_errors_count = Column(Integer, default=0)

    # Tool details for better tracking (JSON field)
    tool_details = Column(Text, nullable=True)  # JSON string with tool names, IDs, outcomes

    # Relationships
    session = relationship("SessionMetrics", back_populates="api_calls")
    project = relationship("ProjectMetrics", back_populates="api_calls")

    def to_dict(self) -> dict:
        """Convert model to dictionary."""
        return {
            "id": self.id,
            "call_id": self.call_id,
            "session_id": self.session_id,
            "project_id": self.project_id,
            "message_id": self.message_id,
            "agent_type": self.agent_type,
            "model_id": self.model_id,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": self.estimated_cost,
            "actual_cost": self.actual_cost,
            "generation_id": self.generation_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "stop_reason": self.stop_reason,
            "tool_calls_count": self.tool_calls_count,
            "tool_errors_count": self.tool_errors_count,
            "tool_details": self.tool_details,
        }


class SessionMetrics(Base):
    """
    Session-level metrics model.

    Stores aggregated metrics for a conversation session.
    """
    __tablename__ = "session_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, unique=True, nullable=False, index=True)
    project_id = Column(String, ForeignKey("project_metrics.project_id", ondelete="CASCADE"), index=True)

    # Aggregated token counts
    total_prompt_tokens = Column(Integer, nullable=False, default=0)
    total_completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)

    # Aggregated costs
    total_estimated_cost = Column(Float, nullable=False, default=0.0)
    total_actual_cost = Column(Float)

    # Session information
    call_count = Column(Integer, nullable=False, default=0) # Number of API calls
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    # Session metadata (JSON string)
    models_used = Column(Text)
    
    # Relationships
    api_calls = relationship("ApiCallMetrics", back_populates="session", cascade="all, delete-orphan")
    project = relationship("ProjectMetrics", back_populates="sessions")

    def to_dict(self) -> dict:
        """Convert model to dictionary."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "project_id": self.project_id,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "total_estimated_cost": self.total_estimated_cost,
            "total_actual_cost": self.total_actual_cost,
            "call_count": self.call_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "models_used": self.models_used,
        }


class ProjectMetrics(Base):
    """
    Project-level metrics model.
    
    Stores aggregated metrics for an entire project.
    """
    __tablename__ = "project_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String, unique=True, nullable=False, index=True)
    
    # Aggregated token counts
    total_prompt_tokens = Column(Integer, nullable=False, default=0)
    total_completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    
    # Aggregated costs
    total_estimated_cost = Column(Float, nullable=False, default=0.0)
    total_actual_cost = Column(Float)
    
    # Project information
    session_count = Column(Integer, nullable=False, default=0)
    call_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
    
    # Project metadata
    name = Column(String)
    description = Column(Text)
    
    # Relationships
    sessions = relationship("SessionMetrics", back_populates="project", cascade="all, delete-orphan")
    api_calls = relationship("ApiCallMetrics", back_populates="project", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        """Convert model to dictionary."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "total_estimated_cost": self.total_estimated_cost,
            "total_actual_cost": self.total_actual_cost,
            "session_count": self.session_count,
            "call_count": self.call_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "name": self.name,
            "description": self.description,
        }
