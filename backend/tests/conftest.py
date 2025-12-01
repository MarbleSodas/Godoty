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
