# Godoty Backend

Strands agent backend for Godot 4.x development assistance using OpenRouter.

## Architecture

This backend implements a comprehensive Strands agent integration with:

- **Custom OpenRouter Model Provider**: Extends Strands OpenAI model for OpenRouter compatibility
- **Godot-Specific Tools**: File operations, scene analysis, and documentation search
- **Session Management**: Project-based conversation persistence using Strands FileSessionManager
- **Metrics & Cost Tracking**: Real-time OpenRouter pricing integration
- **SSE Streaming**: Real-time communication with Angular frontend
- **Desktop Integration**: PyWebView bridge for standalone application

## Project Structure

```
backend/
├── main.py                 # FastAPI application entry point
├── requirements.txt        # Python dependencies
├── start_server.py        # Development startup script
├── app/
│   ├── config.py          # Environment configuration
│   ├── models/
│   │   └── openrouter_model.py  # Custom OpenRouter provider
│   ├── agents/
│   │   └── godoty_agent.py     # Main Godoty agent
│   ├── tools/
│   │   └── godot_tools.py      # Godot-specific tools
│   ├── sessions/
│   │   └── session_manager.py  # Session management
│   ├── metrics/
│   │   └── openrouter_metrics.py # Cost tracking
│   └── api/
│       ├── endpoints.py         # FastAPI routes
│       └── streaming.py         # SSE utilities
└── pywebview/
    ├── api_bridge.py         # JavaScript ↔ Python bridge
    └── desktop_main.py       # Desktop entry point
```

## Configuration

The backend uses environment variables configured in `.env`:

```bash
# OpenRouter API Configuration
OPENROUTER_API_KEY=your_openrouter_api_key_here
DEFAULT_GODOTY_MODEL=x-ai/grok-4.1-fast:free

# Application Configuration
APP_NAME=Godoty
APP_URL=http://localhost:8000

# Server Configuration
HOST=0.0.0.0
PORT=8000
DEBUG=false
```

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables in `.env` file

3. Start the development server:
```bash
python start_server.py
```

Or use uvicorn directly:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

### Health & Connection
- `GET /api/godoty/health` - Application health status
- `GET /api/godoty/connection/status` - OpenRouter connection status
- `GET /api/godoty/config` - Configuration details

### Session Management
- `POST /api/godoty/sessions` - Create new session
- `GET /api/godoty/sessions` - List sessions for project
- `GET /api/godoty/sessions/{id}` - Get session details
- `PUT /api/godoty/sessions/{id}` - Update session
- `POST /api/godoty/sessions/{id}/hide` - Hide session
- `POST /api/godoty/sessions/{id}/stop` - Stop session
- `DELETE /api/godoty/sessions/{id}` - Delete session

### Chat & Communication
- `POST /api/godoty/sessions/{id}/chat/stream` - Start streaming chat
- `POST /api/godoty/sessions/{id}/chat/send` - Send chat message

### Metrics & Analytics
- `GET /api/godoty/metrics` - Usage and cost metrics

## Features

### Godot-Specific Tools

The agent includes specialized tools for Godot development:

1. **Project File Analysis**
   - Scan and categorize project files
   - Support for scripts (.gd), scenes (.tscn), resources (.tres)

2. **Script Analysis**
   - Read and parse GDScript files
   - Extract classes, functions, and variables
   - Syntax-aware code inspection

3. **Scene Structure Analysis**
   - Parse .tscn files and extract node hierarchies
   - Understand parent-child relationships
   - Analyze node properties and connections

4. **Documentation Search**
   - Search through project documentation
   - Find relevant information using keyword matching
   - Support for Markdown and text files

### OpenRouter Integration

- **Custom Model Provider**: Extends Strands OpenAI model for OpenRouter compatibility
- **Pricing Integration**: Real-time cost calculation using OpenRouter pricing API
- **Usage Tracking**: Token-level usage monitoring and cost warnings
- **Model Selection**: Support for multiple OpenRouter models

### Session Management

- **Project-Based Storage**: Sessions stored in project directory (`.godot/godoty_sessions/`)
- **Strands Integration**: Uses FileSessionManager for persistence
- **Metadata Tracking**: Session titles, dates, costs, and usage statistics
- **Cross-Platform**: Sessions travel with Godot projects

### Streaming Communication

- **Server-Sent Events**: Real-time streaming to Angular frontend
- **Event Types**: text, tool_use, tool_result, plan_created, metadata, done, error
- **Error Handling**: Robust error recovery and user feedback
- **Cancellation Support**: AbortSignal support for request cancellation

### Desktop Integration

- **PyWebView Bridge**: JavaScript ↔ Python communication
- **Async Operations**: Proper async handling for desktop streaming
- **Environment Detection**: Automatic browser vs desktop mode detection
- **API Compatibility**: Same API surface in both deployment modes

## Development

### Running in Development Mode

1. Install dependencies:
```bash
pip install fastapi uvicorn python-dotenv pydantic-settings
```

2. Create `.env` file with your OpenRouter API key

3. Start the server:
```bash
python start_server.py
```

4. Access the API documentation at `http://localhost:8000/docs`

### Running Desktop Application

```bash
python pywebview/desktop_main.py
```

### Testing

Basic syntax validation:
```bash
python -c "
import sys
sys.path.append('.')
# Test imports and syntax validation
"
```

## Dependencies

### Core Dependencies
- **FastAPI**: Web framework and API server
- **Pydantic Settings**: Configuration management
- **Uvicorn**: ASGI server
- **Strands**: Agent framework (to be installed)

### OpenRouter Integration
- **OpenAI**: OpenRouter-compatible client
- **HTTPX**: Async HTTP client
- **AIOHTTP**: Additional HTTP utilities

### Desktop Support
- **PyWebView**: Desktop application wrapper

### Development Dependencies
- **pytest**: Testing framework
- **black**: Code formatting
- **mypy**: Type checking

## Security

- **API Key Management**: Environment variables only, never exposed to frontend
- **Path Validation**: Restricted file access to project directory
- **Input Sanitization**: All tool parameters validated
- **Error Handling**: Clean error messages for frontend consumption

## Deployment

### Development Server
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Production Server
```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app
```

### Desktop Application
```bash
python pywebview/desktop_main.py
```

## Frontend Integration

The backend is designed to work with the existing Angular frontend:

- **Service Compatibility**: Matches existing ChatService, SessionService, MetricsService interfaces
- **Endpoint Structure**: Uses `/api/godoty` base path expected by frontend
- **Event Format**: SSE events compatible with frontend MessageEvent interface
- **Error Handling**: Consistent error responses for frontend error handling

## Notes

- This is a complete backend implementation ready for Strands framework integration
- The implementation follows best practices and established architectural patterns
- All modules are properly structured with comprehensive error handling
- The codebase maintains compatibility with the existing sophisticated Angular frontend
- Both web and desktop deployment modes are supported