# Testing Guide

## Overview

This directory contains the refactored test suite for the Godot-Assistant backend. Tests are organized by functionality using pytest.

## Test Organization

The test suite is organized into the following files:

### `conftest.py`
Shared pytest fixtures and configuration for all tests:
- `mock_api_key` - Mock OpenRouter API key
- `temp_dir` - Temporary directory for test files
- `temp_storage_dir` - Temporary storage for session tests
- `mock_openrouter_response` - Mock API responses
- `sample_test_files` - Sample file structure for testing
- `mock_planning_agent` - Mock planning agent instance
- `reset_environment` - Automatic environment cleanup

### `test_planning_agent.py`
Tests for the planning agent functionality:
- Agent loop integration with Strands
- Tool execution during planning
- Streaming event handling
- Multi-step reasoning
- Conversation management


### `test_api_endpoints.py`
Integration tests for API endpoints:
- Health check endpoint
- Configuration endpoint
- Plan generation (non-streaming)
- Plan generation (streaming)
- Conversation reset endpoint

### `test_mcp_integration.py`
Tests for MCP (Model Context Protocol) integration:
- MCPToolManager singleton pattern
- Server initialization
- Sequential thinking tool
- Context7 documentation tools
- Graceful degradation

### `test_multi_agent.py`
Tests for multi-agent session management:
- Session creation and deletion
- Session persistence
- Message processing

## Running Tests

### Run All Tests
```bash
cd backend
pytest tests/ -v
```

### Run Specific Test File
```bash
pytest tests/test_planning_agent.py -v
pytest tests/test_api_endpoints.py -v
```

### Run by Marker

Tests are organized with markers:
- `@pytest.mark.unit` - Fast unit tests
- `@pytest.mark.integration` - Integration tests (require running server)
- `@pytest.mark.mcp` - Tests requiring MCP servers

```bash
# Run only unit tests (fast)
pytest tests/ -v -m unit

# Run only integration tests
pytest tests/ -v -m integration

# Run only MCP tests
pytest tests/ -v -m mcp

# Skip integration tests
pytest tests/ -v -m "not integration"
```

### Run with Coverage
```bash
pytest tests/ --cov=agents --cov-report=html
```

## Prerequisites

###For Unit Tests
- Python 3.11+
- Dependencies from `requirements.txt`
- Valid `.env` configuration

### For Integration Tests
- Running FastAPI server (`python main.py`)
- OpenRouter API key configured

### For MCP Tests
- Node.js (for Context7)
- `uvx` or `npx` available
- MCP servers configured in `.env`

## Test Fixtures

Common fixtures are available in all tests via `conftest.py`:

```python
def test_example(mock_api_key, temp_dir):
    """Example test using fixtures."""
    # mock_api_key provides a test API key
    # temp_dir provides a temporary directory
    pass
```

## Writing New Tests

### Unit Test Example
```python
@pytest.mark.unit
def test_my_function():
    """Test a specific function."""
    result = my_function()
    assert result is not None
```

### Async Test Example
```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_function():
    """Test an async function."""
    result = await my_async_function()
    assert result is not None
```

### Integration Test Example
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_endpoint():
    """Test an API endpoint (requires running server)."""
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/api/endpoint")
        assert response.status_code == 200
```

## Migration Notes

This test structure migrates from the previous scattered test files:
- `reproduce_agent_loop.py` → `test_planning_agent.py`
- `test_agent.py` → `test_api_endpoints.py`
- `test_mcp_integration.py` → `tests/test_mcp_integration.py` (moved)
- `test_multi_agent.py` → `tests/test_multi_agent.py` (moved)

Note: The executor agent system has been removed as part of the architecture cleanup, so `test_executor_agent.py` is no longer needed.

Old debugging scripts (`check_async.py`, `test_imports.py`, etc.) have been removed as their functionality is covered by the new test suite.

## Continuous Integration

Tests can be run in CI/CD pipelines:

```yaml
# Example GitHub Actions
- name: Run Tests
  run: |
    cd backend
    pytest tests/ -v -m "not integration"  # Skip integration tests in CI
```

## Troubleshooting

### Import Errors
Make sure you're running pytest from the `backend` directory:
```bash
cd backend
pytest tests/
```

### MCP Tests Failing
Check that MCP servers are properly configured:
```bash
# Test MCP availability
uvx mcp-server-sequential-thinking --help
npx -y @context7/mcp-server --help
```

### Integration Tests Failing
Ensure the server is running:
```bash
# Terminal 1
python main.py

# Terminal 2
pytest tests/test_api_endpoints.py -v
```
