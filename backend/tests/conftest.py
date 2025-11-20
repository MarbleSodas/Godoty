"""
Shared pytest fixtures and configuration for test suite.
"""
import pytest
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_api_key():
    """Provide a mock OpenRouter API key for testing."""
    return "sk-or-v1-test-key-1234567890abcdef"


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    # Cleanup
    if os.path.exists(temp_path):
        shutil.rmtree(temp_path)


@pytest.fixture
def temp_storage_dir():
    """Create a temporary storage directory for session tests."""
    dir_path = tempfile.mkdtemp(prefix="test_sessions_")
    yield dir_path
    # Cleanup
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)


@pytest.fixture
def mock_openrouter_response():
    """Mock OpenRouter API response."""
    return {
        "id": "gen-test123",
        "model": "openai/gpt-4-turbo",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Test response from OpenRouter"
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30
        }
    }


@pytest.fixture
def sample_test_files(temp_dir):
    """Create sample test files in temporary directory."""
    files = {
        "test.py": "# Test Python file\nprint('hello')",
        "test.txt": "Sample text file",
        "subdir/nested.py": "# Nested file\nclass Test:\n    pass"
    }
    
    for file_path, content in files.items():
        full_path = Path(temp_dir) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
    
    return temp_dir


@pytest.fixture
def mock_planning_agent():
    """Mock planning agent for testing."""
    agent = MagicMock()
    agent.plan_async = MagicMock(return_value="Test plan output")
    
    async def mock_plan_stream(prompt):
        """Mock streaming plan generation."""
        yield {"type": "start", "data": {"message": "Starting plan generation"}}
        yield {"type": "data", "data": {"text": "Test "}}
        yield {"type": "data", "data": {"text": "plan "}}
        yield {"type": "data", "data": {"text": "output"}}
        yield {"type": "end", "data": {"stop_reason": "end_turn"}}
    
    agent.plan_stream = mock_plan_stream
    agent.reset_conversation = MagicMock()
    agent.close = MagicMock()
    
    return agent


@pytest.fixture
def mock_executor_agent():
    """Mock executor agent for testing."""
    agent = MagicMock()
    
    async def mock_execute_plan(plan, context=None):
        """Mock plan execution."""
        yield {"type": "execution_start", "data": {"plan_title": plan.title}}
        yield {"type": "step_start", "data": {"step": 1}}
        yield {"type": "step_complete", "data": {"step": 1, "status": "success"}}
        yield {"type": "execution_complete", "data": {"status": "success"}}
    
    agent.execute_plan = mock_execute_plan
    agent.get_execution_status = MagicMock(return_value=None)
    agent.cancel_execution = MagicMock(return_value=True)
    agent.list_active_executions = MagicMock(return_value=[])
    
    return agent


@pytest.fixture(autouse=True)
def reset_environment(mock_api_key):
    """Reset environment variables before each test."""
    # Store original env
    original_env = os.environ.copy()
    
    # Set test API key
    os.environ["OPENROUTER_API_KEY"] = mock_api_key
    
    yield
    
    # Restore original env
    os.environ.clear()
    os.environ.update(original_env)


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (slower)"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as unit test (fast)"
    )
    config.addinivalue_line(
        "markers", "mcp: mark test as requiring MCP servers"
    )
