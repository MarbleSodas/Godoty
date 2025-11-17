# Godot Agent Integration Tools - Test Suite

This directory contains comprehensive tests for the Godot Agent Integration Tools, ensuring reliability, security, and proper functionality of all components.

## Test Structure

```
tests/
├── __init__.py                 # Test package initialization
├── conftest.py                 # Pytest configuration and fixtures
├── README.md                   # This file - test documentation
├── test_godot_bridge.py        # Tests for WebSocket bridge
├── test_godot_debug_tools.py   # Tests for planning/debug tools
├── test_godot_executor_tools.py # Tests for executor/action tools
├── test_godot_security.py      # Tests for security validation
└── test_integration.py         # Integration and end-to-end tests
```

## Test Categories

### 1. Unit Tests
- **test_godot_bridge.py**: Tests the WebSocket connection management, command handling, and project path detection
- **test_godot_debug_tools.py**: Tests scene analysis, visual context capture, and project inspection
- **test_godot_executor_tools.py**: Tests node manipulation, scene management, and automation tools
- **test_godot_security.py**: Tests security validation, path checking, and operation risk assessment

### 2. Integration Tests
- **test_integration.py**: Tests component integration, end-to-end workflows, error recovery, and performance scenarios

## Running Tests

### Prerequisites

Install the required dependencies:

```bash
pip install pytest pytest-asyncio pytest-mock
```

### Basic Test Execution

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_godot_bridge.py

# Run specific test class
pytest tests/test_godot_bridge.py::TestGodotBridge

# Run specific test method
pytest tests/test_godot_bridge.py::TestGodotBridge::test_bridge_initialization_default_config
```

### Running Tests with Markers

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run only WebSocket-dependent tests
pytest -m websocket

# Run slow tests (for comprehensive testing)
pytest -m slow
```

### Running Tests with Coverage

```bash
# Install coverage
pip install pytest-cov

# Run tests with coverage report
pytest --cov=agents.tools --cov-report=html

# Generate coverage report in terminal
pytest --cov=agents.tools --cov-report=term-missing
```

## Test Configuration

### Environment Variables

The tests can be configured with environment variables:

```bash
# Set test timeout (default: 30 seconds)
export TEST_TIMEOUT=60

# Enable debug logging
export TEST_DEBUG=true

# Skip integration tests (faster testing)
export SKIP_INTEGRATION=true
```

### Pytest Configuration

The `conftest.py` file contains:

- **Fixtures**: Mock objects and test data
- **Markers**: Custom test markers for categorization
- **Hooks**: Pytest configuration and setup

## Key Test Features

### 1. Mock WebSocket Testing

Tests use a sophisticated mock WebSocket implementation:

```python
class MockWebSocket:
    def __init__(self):
        self.messages = []
        self.closed = False
        self.response_data = {}
```

### 2. Comprehensive Fixtures

Pre-configured test data:

- `mock_project_info`: Simulated Godot project information
- `mock_scene_tree`: Complex scene tree structure
- `mock_node_info`: Individual node data
- `mock_visual_snapshot`: Viewport and screenshot data
- `mock_search_results`: Node search results

### 3. Async Test Support

All tests support async/await patterns:

```python
@pytest.mark.asyncio
async def test_async_operation(self, mock_godot_bridge):
    result = await some_async_operation()
    assert result.success is True
```

### 4. Error Scenario Testing

Comprehensive error handling tests:

- Connection failures
- Timeout scenarios
- Invalid data handling
- Partial failures
- Security violations

## Test Coverage Areas

### Godot Bridge (`test_godot_bridge.py`)

- ✅ Connection management and reconnection
- ✅ Command sending and response handling
- ✅ Project path detection and validation
- ✅ Error handling and recovery
- ✅ WebSocket communication
- ✅ Utility functions (path conversion, validation)

### Debug Tools (`test_godot_debug_tools.py`)

- ✅ Project overview and statistics
- ✅ Scene tree analysis and recommendations
- ✅ Visual context capture (screenshots, viewport)
- ✅ Node search and filtering
- ✅ Debug output retrieval
- ✅ Project structure analysis
- ✅ Performance metrics

### Executor Tools (`test_godot_executor_tools.py`)

- ✅ Node creation, modification, deletion
- ✅ Scene management (create, open, save)
- ✅ Property modification with validation
- ✅ Batch operations
- ✅ Selection and focus controls
- ✅ Playback control (play/stop)
- ✅ Operation history and undo/redo

### Security Module (`test_godot_security.py`)

- ✅ Operation risk assessment (SAFE to CRITICAL)
- ✅ Path validation and traversal prevention
- ✅ Parameter validation and sanitization
- ✅ Security context management
- ✅ Sensitive file detection
- ✅ Node and scene name validation

### Integration Tests (`test_integration.py`)

- ✅ End-to-end workflows
- ✅ Component interaction
- ✅ Error recovery scenarios
- ✅ Performance and concurrency
- ✅ Configuration changes
- ✅ Memory management

## Test Markers

### Built-in Markers

- `@pytest.mark.asyncio`: Marks async test functions
- `@pytest.mark.unit`: Unit tests (isolated component testing)
- `@pytest.mark.integration`: Integration tests (component interaction)
- `@pytest.mark.websocket`: Tests requiring WebSocket functionality
- `@pytest.mark.slow`: Long-running tests

### Custom Usage

```python
@pytest.mark.integration
@pytest.mark.websocket
async def test_full_workflow(self):
    # Integration test requiring WebSocket
    pass
```

## Mock Strategy

### 1. WebSocket Mocking

```python
@pytest.fixture
def mock_websocket():
    return MockWebSocket()
```

### 2. Bridge Mocking

```python
@pytest.fixture
async def mock_godot_bridge(mock_websocket, mock_godot_config):
    with patch('websockets.connect') as mock_connect:
        mock_connect.return_value = mock_websocket
        bridge = GodotBridge(mock_godot_config)
        yield bridge
```

### 3. Response Simulation

```python
mock_bridge.send_command = AsyncMock(return_value=MagicMock(
    success=True,
    data=mock_response_data
))
```

## Performance Testing

### Concurrency Tests

```python
@pytest.mark.asyncio
@pytest.mark.slow
async def test_concurrent_operations(self, mock_godot_bridge):
    tasks = [create_node(...) for _ in range(10)]
    results = await asyncio.gather(*tasks)
    assert all(result.success for result in results)
```

### Memory Tests

```python
async def test_memory_usage(self, mock_godot_bridge):
    for i in range(100):
        await create_node("Node", "Root", f"Node{i}")
    # Verify memory management
```

## Error Testing Patterns

### 1. Connection Failures

```python
async def test_connection_failure(self):
    mock_bridge.connect = AsyncMock(return_value=False)
    result = await some_operation()
    assert result.success is False
```

### 2. Timeout Scenarios

```python
async def test_timeout_recovery(self):
    mock_bridge.send_command = AsyncMock(side_effect=asyncio.TimeoutError())
    result = await some_operation_with_retry()
    assert result.success is True  # After retry
```

### 3. Invalid Data

```python
async def test_invalid_data_handling(self):
    mock_bridge.send_command = AsyncMock(return_value=MagicMock(
        success=True,
        data=None  # Missing expected data
    ))
    result = await some_operation()
    assert result.success is False
```

## Security Testing

### 1. Path Traversal

```python
def test_path_traversal_prevention(self):
    result = validate_path("res://../../../etc/passwd", "godot_path")
    assert result.allowed is False
    assert "directory traversal" in result.reason
```

### 2. Risk Assessment

```python
def test_operation_risk_levels(self):
    context = SecurityContext()
    context.set_risk_threshold(OperationRisk.LOW)

    result = validate_operation("delete_node", {})
    assert result.allowed is False  # Exceeds threshold
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Godot Tools Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.9
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-asyncio pytest-cov
    - name: Run tests
      run: |
        pytest --cov=agents.tools --cov-report=xml
    - name: Upload coverage
      uses: codecov/codecov-action@v1
```

## Debugging Tests

### 1. Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 2. Use Pytest Debugger

```bash
# Run with pdb on failure
pytest --pdb

# Run with specific test on failure
pytest --lf --pdb
```

### 3. Print Test Information

```python
def test_with_debug_info(self, mock_godot_bridge):
    print(f"Bridge state: {mock_godot_bridge.connection_state}")
    result = await some_operation()
    print(f"Operation result: {result}")
```

## Test Best Practices

### 1. Test Isolation

Each test should be independent:

```python
@pytest.fixture(autouse=True)
async def cleanup_after_test():
    yield
    # Cleanup code here
```

### 2. Descriptive Test Names

```python
def test_create_node_success_with_all_parameters(self):
    # Clear what this test does
    pass
```

### 3. Comprehensive Assertions

```python
def test_operation_result(self):
    result = await some_operation()

    # Check all aspects of the result
    assert result.success is True
    assert result.data is not None
    assert result.error is None
    assert "expected_field" in result.data
```

### 4. Error Message Validation

```python
def test_error_handling(self):
    result = await failing_operation()

    assert result.success is False
    assert "specific error message" in result.error
```

## Contributing Tests

### 1. Adding New Tests

1. Choose appropriate test file or create new one
2. Use descriptive test names
3. Follow existing patterns and fixtures
4. Include both success and failure scenarios
5. Add appropriate markers

### 2. Test Review Checklist

- [ ] Test name is descriptive
- [ ] Test follows AAA pattern (Arrange, Act, Assert)
- [ ] Appropriate fixtures are used
- [ ] Both success and failure cases are tested
- [ ] Error messages are validated
- [ ] Test is isolated and independent
- [ ] Mocks are properly configured
- [ ] Async/await is used correctly

### 3. Running Tests Before Submission

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=agents.tools

# Run integration tests
pytest -m integration

# Run specific new test
pytest tests/test_new_feature.py
```

## Troubleshooting

### Common Issues

1. **Async Test Failures**: Ensure `@pytest.mark.asyncio` decorator is used
2. **Import Errors**: Check that `PYTHONPATH` includes the project directory
3. **Mock Not Working**: Verify patch paths and mock configuration
4. **Timeout Failures**: Increase timeout values or check mock responses
5. **Fixture Not Found**: Ensure fixture is defined in `conftest.py`

### Debug Commands

```bash
# List all tests
pytest --collect-only

# Run tests with specific output
pytest -v -s

# Show local variables on failure
pytest --tb=long

# Stop on first failure
pytest -x
```

This comprehensive test suite ensures the reliability and security of the Godot Agent Integration Tools while providing clear guidance for maintenance and extension.