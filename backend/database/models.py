"""
SQLAlchemy ORM models for metrics tracking.

Defines database models for message, session, and project-level metrics.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class MessageMetrics(Base):
    """
    Message-level metrics model.
    
    Stores token usage and cost information for individual API calls.
    """
    __tablename__ = "message_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String, unique=True, nullable=False, index=True)
    session_id = Column(String, ForeignKey("session_metrics.session_id", ondelete="CASCADE"), index=True)
    project_id = Column(String, ForeignKey("project_metrics.project_id", ondelete="CASCADE"), index=True)
    
    # Model information
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
    response_time_ms = Column(Integer)
    
    # Additional metadata
    stop_reason = Column(String)
    tool_calls_count = Column(Integer, default=0)
    tool_errors_count = Column(Integer, default=0)
    
    # Relationships
    session = relationship("SessionMetrics", back_populates="messages")
    project = relationship("ProjectMetrics", back_populates="messages")

    def to_dict(self) -> dict:
        """Convert model to dictionary."""
        return {
            "id": self.id,
            "message_id": self.message_id,
            "session_id": self.session_id,
            "project_id": self.project_id,
            "model_id": self.model_id,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": self.estimated_cost,
            "actual_cost": self.actual_cost,
            "generation_id": self.generation_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "response_time_ms": self.response_time_ms,
            "stop_reason": self.stop_reason,
            "tool_calls_count": self.tool_calls_count,
            "tool_errors_count": self.tool_errors_count,
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
    
    # Error tracking
    total_tool_errors = Column(Integer, nullable=False, default=0)
    
    # Session information
    message_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
    
    # Session metadata (JSON string)
    models_used = Column(Text)
    
    # Relationships
    messages = relationship("MessageMetrics", back_populates="session", cascade="all, delete-orphan")
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
            "total_tool_errors": self.total_tool_errors,
            "message_count": self.message_count,
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
    message_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
    
    # Project metadata
    name = Column(String)
    description = Column(Text)
    
    # Relationships
    sessions = relationship("SessionMetrics", back_populates="project", cascade="all, delete-orphan")
    messages = relationship("MessageMetrics", back_populates="project", cascade="all, delete-orphan")

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
            "message_count": self.message_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "name": self.name,
            "description": self.description,
        }
