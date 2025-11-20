"""
Database manager for metrics tracking.

Provides database initialization, CRUD operations, and aggregation queries
for metrics data.
"""

import os
import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, select, func, and_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from .models import Base, MessageMetrics, SessionMetrics, ProjectMetrics

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages database connections and operations for metrics tracking.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file. Defaults to .godoty_metrics.db
        """
        if db_path is None:
            db_path = os.path.join(os.getcwd(), ".godoty_metrics.db")

        self.db_path = db_path
        self.db_url = f"sqlite+aiosqlite:///{db_path}"

        # Create async engine
        self.engine = create_async_engine(
            self.db_url,
            echo=False,
            connect_args={"check_same_thread": False}
        )

        # Create session maker
        self.async_session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

        logger.info(f"DatabaseManager initialized with db_path: {db_path}")

    async def initialize(self):
        """Initialize database tables."""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    async def close(self):
        """Close database connections."""
        await self.engine.dispose()
        logger.info("Database connections closed")

    # Message Metrics CRUD Operations

    async def create_message_metrics(
        self,
        message_id: str,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        estimated_cost: float,
        session_id: Optional[str] = None,
        project_id: Optional[str] = None,
        generation_id: Optional[str] = None,
        response_time_ms: Optional[int] = None,
        stop_reason: Optional[str] = None,
        tool_calls_count: int = 0,
        actual_cost: Optional[float] = None
    ) -> MessageMetrics:
        """
        Create a new message metrics record.

        Args:
            message_id: Unique message identifier
            model_id: Model used for the message
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            total_tokens: Total tokens (prompt + completion)
            estimated_cost: Estimated cost in USD
            session_id: Optional session ID
            project_id: Optional project ID
            generation_id: Optional OpenRouter generation ID
            response_time_ms: Optional response time in milliseconds
            stop_reason: Optional stop reason
            tool_calls_count: Number of tool calls made
            actual_cost: Optional actual cost from generation endpoint

        Returns:
            Created MessageMetrics instance
        """
        async with self.async_session_maker() as session:
            try:
                metrics = MessageMetrics(
                    message_id=message_id,
                    session_id=session_id,
                    project_id=project_id,
                    model_id=model_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    estimated_cost=estimated_cost,
                    actual_cost=actual_cost,
                    generation_id=generation_id,
                    response_time_ms=response_time_ms,
                    stop_reason=stop_reason,
                    tool_calls_count=tool_calls_count
                )

                session.add(metrics)
                await session.commit()
                await session.refresh(metrics)

                logger.info(f"Created message metrics: {message_id}")
                return metrics
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to create message metrics: {e}")
                raise

    async def get_message_metrics(self, message_id: str) -> Optional[MessageMetrics]:
        """Get message metrics by ID."""
        async with self.async_session_maker() as session:
            result = await session.execute(
                select(MessageMetrics).where(MessageMetrics.message_id == message_id)
            )
            return result.scalar_one_or_none()

    async def update_message_actual_cost(self, message_id: str, actual_cost: float):
        """Update actual cost for a message after querying generation endpoint."""
        async with self.async_session_maker() as session:
            try:
                result = await session.execute(
                    select(MessageMetrics).where(MessageMetrics.message_id == message_id)
                )
                metrics = result.scalar_one_or_none()

                if metrics:
                    metrics.actual_cost = actual_cost
                    await session.commit()
                    logger.info(f"Updated actual cost for message {message_id}: ${actual_cost}")
                else:
                    logger.warning(f"Message metrics not found: {message_id}")
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to update actual cost: {e}")
                raise

    # Session Metrics Operations

    async def get_or_create_session_metrics(
        self,
        session_id: str,
        project_id: Optional[str] = None
    ) -> SessionMetrics:
        """Get existing session metrics or create new one."""
        async with self.async_session_maker() as session:
            try:
                result = await session.execute(
                    select(SessionMetrics).where(SessionMetrics.session_id == session_id)
                )
                metrics = result.scalar_one_or_none()

                if metrics:
                    return metrics

                # Create new session metrics
                metrics = SessionMetrics(
                    session_id=session_id,
                    project_id=project_id
                )
                session.add(metrics)
                await session.commit()
                await session.refresh(metrics)

                logger.info(f"Created session metrics: {session_id}")
                return metrics
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to get/create session metrics: {e}")
                raise

    async def update_session_metrics(
        self,
        session_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        estimated_cost: float,
        model_id: str,
        actual_cost: Optional[float] = None
    ):
        """Update session metrics by adding message metrics."""
        async with self.async_session_maker() as session:
            try:
                result = await session.execute(
                    select(SessionMetrics).where(SessionMetrics.session_id == session_id)
                )
                metrics = result.scalar_one_or_none()

                if not metrics:
                    logger.warning(f"Session metrics not found: {session_id}")
                    return

                # Update aggregated values
                metrics.total_prompt_tokens += prompt_tokens
                metrics.total_completion_tokens += completion_tokens
                metrics.total_tokens += total_tokens
                metrics.total_estimated_cost += estimated_cost
                if actual_cost:
                    metrics.total_actual_cost = (metrics.total_actual_cost or 0) + actual_cost
                metrics.message_count += 1
                metrics.updated_at = datetime.utcnow()

                # Update models used
                models_used = json.loads(metrics.models_used) if metrics.models_used else []
                if model_id not in models_used:
                    models_used.append(model_id)
                metrics.models_used = json.dumps(models_used)

                await session.commit()
                logger.info(f"Updated session metrics: {session_id}")
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to update session metrics: {e}")
                raise

    async def get_session_metrics(self, session_id: str) -> Optional[SessionMetrics]:
        """Get session metrics by ID."""
        async with self.async_session_maker() as session:
            result = await session.execute(
                select(SessionMetrics).where(SessionMetrics.session_id == session_id)
            )
            return result.scalar_one_or_none()

    async def get_session_messages(self, session_id: str) -> List[MessageMetrics]:
        """Get all message metrics for a session."""
        async with self.async_session_maker() as session:
            result = await session.execute(
                select(MessageMetrics)
                .where(MessageMetrics.session_id == session_id)
                .order_by(MessageMetrics.created_at)
            )
            return list(result.scalars().all())

    # Project Metrics Operations

    async def get_or_create_project_metrics(
        self,
        project_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> ProjectMetrics:
        """Get existing project metrics or create new one."""
        async with self.async_session_maker() as session:
            try:
                result = await session.execute(
                    select(ProjectMetrics).where(ProjectMetrics.project_id == project_id)
                )
                metrics = result.scalar_one_or_none()

                if metrics:
                    return metrics

                # Create new project metrics
                metrics = ProjectMetrics(
                    project_id=project_id,
                    name=name,
                    description=description
                )
                session.add(metrics)
                await session.commit()
                await session.refresh(metrics)

                logger.info(f"Created project metrics: {project_id}")
                return metrics
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to get/create project metrics: {e}")
                raise

    async def update_project_metrics(
        self,
        project_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        estimated_cost: float,
        actual_cost: Optional[float] = None,
        is_new_session: bool = False,
        is_new_message: bool = True
    ):
        """Update project metrics."""
        async with self.async_session_maker() as session:
            try:
                result = await session.execute(
                    select(ProjectMetrics).where(ProjectMetrics.project_id == project_id)
                )
                metrics = result.scalar_one_or_none()

                if not metrics:
                    logger.warning(f"Project metrics not found: {project_id}")
                    return

                # Update aggregated values
                metrics.total_prompt_tokens += prompt_tokens
                metrics.total_completion_tokens += completion_tokens
                metrics.total_tokens += total_tokens
                metrics.total_estimated_cost += estimated_cost
                if actual_cost:
                    metrics.total_actual_cost = (metrics.total_actual_cost or 0) + actual_cost

                if is_new_session:
                    metrics.session_count += 1
                if is_new_message:
                    metrics.message_count += 1

                metrics.updated_at = datetime.utcnow()

                await session.commit()
                logger.info(f"Updated project metrics: {project_id}")
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to update project metrics: {e}")
                raise

    async def get_project_metrics(self, project_id: str) -> Optional[ProjectMetrics]:
        """Get project metrics by ID."""
        async with self.async_session_maker() as session:
            result = await session.execute(
                select(ProjectMetrics).where(ProjectMetrics.project_id == project_id)
            )
            return result.scalar_one_or_none()

    async def get_project_sessions(self, project_id: str) -> List[SessionMetrics]:
        """Get all session metrics for a project."""
        async with self.async_session_maker() as session:
            result = await session.execute(
                select(SessionMetrics)
                .where(SessionMetrics.project_id == project_id)
                .order_by(SessionMetrics.created_at)
            )
            return list(result.scalars().all())

    async def list_all_projects(self) -> List[ProjectMetrics]:
        """List all projects."""
        async with self.async_session_maker() as session:
            result = await session.execute(
                select(ProjectMetrics).order_by(ProjectMetrics.created_at.desc())
            )
            return list(result.scalars().all())


# Global instance
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """Get or create the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
