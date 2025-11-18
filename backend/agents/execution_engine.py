"""
Execution Engine for Godot Assistant.

This module provides basic execution functionality without complex dependencies.
Works directly with structured plans from the planning agent.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, AsyncIterable, Optional

from .execution_models import (
    ExecutionPlan, ExecutionStep, ExecutionResult, ExecutionState,
    ExecutionStatus, StreamEvent, ToolCall
)
from .tools.godot_executor_tools import GodotExecutorTools
from .tools.file_tools import FileTools

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Simple execution engine for executing plans."""

    def __init__(self):
        """Initialize execution engine."""
        self.godot_tools = GodotExecutorTools()
        self.file_tools = FileTools()
        self._active_executions: Dict[str, ExecutionState] = {}

        # Register available tools
        self._tools = {
            # Godot tools
            "create_node": self.godot_tools.create_node,
            "delete_node": self.godot_tools.delete_node,
            "modify_node_property": self.godot_tools.modify_node_property,
            "create_scene": self.godot_tools.create_new_scene,
            "open_scene": self.godot_tools.open_scene,
            "play_scene": self.godot_tools.play_scene,
            "stop_playing": self.godot_tools.stop_playing,

            # File tools
            "write_file": self.file_tools.write_file_safe,
            "read_file": self.file_tools.read_file_safe,
            "delete_file": self.file_tools.delete_file_safe,
        }

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        context: Optional[Dict[str, Any]] = None
    ) -> AsyncIterable[StreamEvent]:
        """
        Execute a plan with streaming events.

        Args:
            plan: Execution plan from planning agent
            context: Optional execution context

        Yields:
            StreamEvent objects
        """
        execution_id = str(uuid.uuid4())
        context = context or {}

        # Create execution state
        state = ExecutionState(
            execution_id=execution_id,
            plan=plan,
            status=ExecutionStatus.RUNNING
        )
        self._active_executions[execution_id] = state

        try:
            yield StreamEvent(
                type="execution_started",
                data={
                    "execution_id": execution_id,
                    "plan_id": plan.id,
                    "step_count": len(plan.steps)
                }
            )

            # Execute steps in dependency order
            executed_steps = set()
            steps_to_execute = list(plan.steps)

            while len(executed_steps) < len(plan.steps):
                # Find steps that can be executed (dependencies satisfied)
                ready_steps = [
                    step for step in steps_to_execute
                    if step.id not in executed_steps and
                    all(dep in executed_steps for dep in step.depends_on)
                ]

                if not ready_steps:
                    # Circular dependency or missing dependency
                    yield StreamEvent(
                        type="execution_failed",
                        data={"error": "Cannot resolve step dependencies"}
                    )
                    break

                # Execute ready steps
                for step in ready_steps:
                    async for event in self._execute_step(step, state, context):
                        yield event
                    executed_steps.add(step.id)

            # Determine final status
            if len(state.failed_steps) > 0:
                state.status = ExecutionStatus.FAILED
                yield StreamEvent(
                    type="execution_completed",
                    data={
                        "status": "failed",
                        "completed": len(state.completed_steps),
                        "failed": len(state.failed_steps)
                    }
                )
            else:
                state.status = ExecutionStatus.COMPLETED
                yield StreamEvent(
                    type="execution_completed",
                    data={
                        "status": "completed",
                        "completed": len(state.completed_steps)
                    }
                )

        except Exception as e:
            logger.error(f"Execution failed: {e}")
            state.status = ExecutionStatus.FAILED
            yield StreamEvent(
                type="execution_error",
                data={"error": str(e)}
            )

        finally:
            # Clean up
            if execution_id in self._active_executions:
                del self._active_executions[execution_id]

    async def _execute_step(
        self,
        step: ExecutionStep,
        state: ExecutionState,
        context: Dict[str, Any]
    ) -> AsyncIterable[StreamEvent]:
        """
        Execute a single step.

        Args:
            step: Step to execute
            state: Execution state
            context: Execution context

        Yields:
            StreamEvent objects
        """
        step_id = step.id
        execution_id = state.execution_id

        yield StreamEvent(
            type="step_started",
            data={
                "step_id": step_id,
                "title": step.title,
                "tool_count": len(step.tool_calls)
            }
        )

        state.current_step = step_id
        start_time = datetime.now()

        try:
            # Execute all tool calls
            tool_results = []
            for i, tool_call in enumerate(step.tool_calls):
                yield StreamEvent(
                    type="tool_started",
                    data={
                        "step_id": step_id,
                        "tool_name": tool_call.name,
                        "tool_index": i
                    }
                )

                try:
                    result = await self._execute_tool(tool_call, context)
                    tool_results.append(result)

                    yield StreamEvent(
                        type="tool_completed",
                        data={
                            "step_id": step_id,
                            "tool_name": tool_call.name,
                            "success": True
                        }
                    )
                except Exception as e:
                    error_msg = str(e)
                    tool_results.append({"error": error_msg, "success": False})

                    yield StreamEvent(
                        type="tool_failed",
                        data={
                            "step_id": step_id,
                            "tool_name": tool_call.name,
                            "error": error_msg
                        }
                    )

            # Check if all tools succeeded
            all_success = all(
                result.get("success", True) for result in tool_results
            )

            # Create step result
            end_time = datetime.now()
            result = ExecutionResult(
                step_id=step_id,
                status=ExecutionStatus.COMPLETED if all_success else ExecutionStatus.FAILED,
                started_at=start_time,
                completed_at=end_time,
                output=f"Executed {len(tool_results)} tools",
                error=None if all_success else "Some tools failed"
            )

            state.step_results[step_id] = result

            if all_success:
                state.completed_steps.append(step_id)
                yield StreamEvent(
                    type="step_completed",
                    data={
                        "step_id": step_id,
                        "success": True,
                        "duration": (end_time - start_time).total_seconds()
                    }
                )
            else:
                state.failed_steps.append(step_id)
                yield StreamEvent(
                    type="step_failed",
                    data={
                        "step_id": step_id,
                        "success": False,
                        "error": result.error
                    }
                )

        except Exception as e:
            logger.error(f"Step execution failed: {e}")

            result = ExecutionResult(
                step_id=step_id,
                status=ExecutionStatus.FAILED,
                started_at=start_time,
                completed_at=datetime.now(),
                error=str(e)
            )

            state.step_results[step_id] = result
            state.failed_steps.append(step_id)

            yield StreamEvent(
                type="step_error",
                data={
                    "step_id": step_id,
                    "error": str(e)
                }
            )

        finally:
            state.current_step = None

    async def _execute_tool(
        self,
        tool_call: ToolCall,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a single tool call.

        Args:
            tool_call: Tool to execute
            context: Execution context

        Returns:
            Tool execution result
        """
        tool_name = tool_call.name
        parameters = tool_call.parameters

        if tool_name not in self._tools:
            raise ValueError(f"Unknown tool: {tool_name}")

        # Add context to parameters
        if context:
            parameters = {**parameters, **context}

        tool_func = self._tools[tool_name]

        try:
            # Execute tool with timeout
            result = await asyncio.wait_for(tool_func(**parameters), timeout=30)

            # Convert result to consistent format
            if hasattr(result, '__dict__'):
                return {
                    "success": getattr(result, 'success', True),
                    "data": result.__dict__
                }
            elif isinstance(result, dict):
                return {"success": True, "data": result}
            else:
                return {"success": True, "data": result}

        except asyncio.TimeoutError:
            raise Exception(f"Tool '{tool_name}' timed out")
        except Exception as e:
            logger.error(f"Tool '{tool_name}' failed: {e}")
            return {"success": False, "error": str(e)}

    def get_execution_status(self, execution_id: str) -> Optional[ExecutionState]:
        """Get execution status."""
        return self._active_executions.get(execution_id)

    def list_active_executions(self) -> List[ExecutionState]:
        """List active executions."""
        return list(self._active_executions.values())

    async def cancel_execution(self, execution_id: str) -> bool:
        """Cancel an execution."""
        if execution_id in self._active_executions:
            state = self._active_executions[execution_id]
            state.status = ExecutionStatus.FAILED
            del self._active_executions[execution_id]
            return True
        return False