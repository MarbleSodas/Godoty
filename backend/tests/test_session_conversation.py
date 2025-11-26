"""Test session-based conversation flow."""
import pytest
import os
import json
import tempfile
import shutil
from unittest.mock import MagicMock, patch
from agents.multi_agent_manager import MultiAgentManager


@pytest.fixture
def temp_storage_dir():
    """Create a temporary storage directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def manager(temp_storage_dir):
    """Create a MultiAgentManager instance with temp storage and mocked agents."""
    with patch('agents.multi_agent_manager.get_planning_agent') as mock_planner, \
         patch('agents.multi_agent_manager.get_executor_agent') as mock_executor:

        # Setup mock agents
        planner_instance = MagicMock()
        mock_agent = MagicMock()
        # Make state.get() return a JSON-serializable dict
        mock_agent.state.get.return_value = {}
        mock_agent._session_manager = None
        planner_instance.agent = mock_agent

        executor_instance = MagicMock()
        executor_mock_agent = MagicMock()
        # Make state.get() return a JSON-serializable dict
        executor_mock_agent.state.get.return_value = {}
        executor_mock_agent._session_manager = None
        executor_instance.agent = executor_mock_agent

        mock_planner.return_value = planner_instance
        mock_executor.return_value = executor_instance

        manager = MultiAgentManager()
        manager.storage_dir = temp_storage_dir
        yield manager


@pytest.mark.asyncio
async def test_shared_session_manager(manager):
    """Test that planning and executor graphs share session manager."""
    session_id = "test-shared-manager"
    manager.create_session(session_id, "Test session")

    graphs = manager._active_graphs[session_id]

    # Verify both graphs exist
    assert "planning" in graphs
    assert "executor" in graphs

    # Verify shared session reference is stored
    assert "shared_session" in graphs
    assert graphs["shared_session"] is not None


@pytest.mark.asyncio
async def test_context_generation(manager):
    """Test execution context extraction from planning conversation."""
    session_id = "test-context"
    manager.create_session(session_id, "Test context generation")

    # Create mock session with planning messages
    session_path = os.path.join(manager.storage_dir, f"session_{session_id}")
    os.makedirs(session_path, exist_ok=True)
    session_file = os.path.join(session_path, "session.json")

    session_data = {
        "messages": [
            {"role": "user", "content": "Build menu system"},
            {"role": "assistant", "content": "I'll create a menu with these steps: 1. Create scene 2. Add nodes 3. Configure"},
            {"role": "assistant", "content": "The plan is ready for execution"}
        ]
    }

    with open(session_file, 'w') as f:
        json.dump(session_data, f)

    # Generate context
    context = manager._generate_execution_context(session_id)

    assert "menu" in context.lower()
    assert "Original Request" in context
    assert len(context) > 0


@pytest.mark.asyncio
async def test_plan_detection_positive(manager):
    """Test plan completion detection with valid plan text."""
    plan_text = """## Objective
Create a player movement system

## Execution Steps

1. Create the player scene
2. Add CharacterBody2D node
3. Write movement script

## Success Criteria
Player can move with arrow keys"""

    plan_info = manager._detect_plan_completion(plan_text)

    assert plan_info is not None
    assert "title" in plan_info
    assert plan_info.get("step_count", 0) >= 1
    assert plan_info.get("is_conversational") == True


@pytest.mark.asyncio
async def test_plan_detection_negative(manager):
    """Test plan completion detection with non-plan text."""
    non_plan_text = """This is just a regular conversation.
I'm analyzing the codebase to understand the structure.
Let me think about this some more."""

    plan_info = manager._detect_plan_completion(non_plan_text)

    # Should not detect a plan in regular conversation
    assert plan_info is None


@pytest.mark.asyncio
async def test_tool_phase_categorization(manager):
    """Test tool categorization into execution phases."""
    # Scene tools
    assert manager._categorize_tool_phase("create_scene") == "Scene Creation"
    assert manager._categorize_tool_phase("open_scene") == "Scene Creation"

    # Node tools
    assert manager._categorize_tool_phase("create_node") == "Node Management"
    assert manager._categorize_tool_phase("delete_node") == "Node Management"
    assert manager._categorize_tool_phase("modify_node_property") == "Node Management"

    # File tools
    assert manager._categorize_tool_phase("write_file") == "File Operations"
    assert manager._categorize_tool_phase("read_file") == "File Operations"

    # Analysis tools
    assert manager._categorize_tool_phase("analyze_scene_tree") == "Scene Analysis"
    assert manager._categorize_tool_phase("get_project_overview") == "Scene Analysis"

    # Testing tools
    assert manager._categorize_tool_phase("play_scene") == "Testing & Validation"
    assert manager._categorize_tool_phase("capture_visual_context") == "Testing & Validation"

    # Unknown tool
    assert manager._categorize_tool_phase("unknown_tool") is None


@pytest.mark.asyncio
async def test_session_metadata_migration(manager):
    """Test migration from old structured plan format."""
    session_id = "test-migration"
    metadata_path = os.path.join(manager.storage_dir, f"{session_id}_metadata.json")

    # Create old-style metadata with current_plan
    old_metadata = {
        "title": "Old Session",
        "created_at": "2024-01-01T00:00:00",
        "current_plan": {
            "title": "Old Plan",
            "description": "This was a structured plan",
            "steps": []
        }
    }

    os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
    with open(metadata_path, 'w') as f:
        json.dump(old_metadata, f)

    # Load metadata (should trigger migration)
    metadata = manager._load_session_metadata(session_id)

    # Verify migration happened
    assert "current_plan" not in metadata
    assert metadata.get("legacy_plan_title") == "Old Plan"
    assert metadata.get("migrated_from_structured") == True


@pytest.mark.asyncio
async def test_generate_context_no_session(manager):
    """Test context generation handles missing session gracefully."""
    context = manager._generate_execution_context("nonexistent-session")

    assert "No planning context available" in context or "Context extraction failed" in context


@pytest.mark.asyncio
async def test_generate_context_empty_messages(manager):
    """Test context generation handles empty message list."""
    session_id = "test-empty-messages"
    manager.create_session(session_id, "Empty messages test")

    # Create session file with empty messages
    session_path = os.path.join(manager.storage_dir, f"session_{session_id}")
    os.makedirs(session_path, exist_ok=True)
    session_file = os.path.join(session_path, "session.json")

    session_data = {"messages": []}

    with open(session_file, 'w') as f:
        json.dump(session_data, f)

    context = manager._generate_execution_context(session_id)

    assert "No planning context available" in context


@pytest.mark.asyncio
async def test_generate_context_truncates_long_messages(manager):
    """Test that long messages are truncated to prevent context overflow."""
    session_id = "test-truncate"
    manager.create_session(session_id, "Truncation test")

    # Create session with very long message
    session_path = os.path.join(manager.storage_dir, f"session_{session_id}")
    os.makedirs(session_path, exist_ok=True)
    session_file = os.path.join(session_path, "session.json")

    long_content = "x" * 1000  # 1000 characters
    session_data = {
        "messages": [
            {"role": "user", "content": "Short request"},
            {"role": "assistant", "content": long_content}
        ]
    }

    with open(session_file, 'w') as f:
        json.dump(session_data, f)

    context = manager._generate_execution_context(session_id)

    # Should be truncated with "..."
    assert "..." in context
    assert len(context) < 1000  # Should be shorter than original
