# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Godoty** is a sophisticated desktop application that provides AI-powered assistance for Godot game development. It integrates a Python backend with AI agents, an Angular frontend, and a Godot Engine plugin for seamless development workflows.

## Architecture & Key Components

### Single-Agent System
- **Planning Agent** (`backend/agents/planning_agent.py`) - Single agent that handles both planning and execution using OpenRouter models
- **Multi-Agent Manager** (`backend/agents/multi_agent_manager.py`) - Session management and conversation persistence

### Hybrid Communication
- **PyWebView Bridge** - JavaScript-Python communication for desktop features
- **FastAPI REST API** - Backend endpoints for agent interactions
- **Server-Sent Events (SSE)** - Real-time streaming for agent responses
- **WebSocket Integration** - Godot plugin communication

### MCP (Model Context Protocol) Integration
- **Sequential Thinking** - Advanced step-by-step reasoning
- **Context7** - Up-to-date library documentation
- **Custom Tool Servers** - Extensible architecture for agent tools

## Development Commands

### Environment Setup
```bash
# Backend
cd backend
python3 -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env  # Configure OpenRouter API key

# Frontend
cd frontend
npm install
```

### Development Mode (Hot Reload)
```bash
# Terminal 1: Frontend dev server
cd frontend
npx ng serve

# Terminal 2: Backend with hot reload
cd backend
source venv/bin/activate
uvicorn main:app --reload
```

### Production Build & Run
```bash
# Build frontend
cd frontend
npx ng build --configuration production

# Run desktop app
cd ../backend
source venv/bin/activate
python main.py
```

### Testing
```bash
cd backend

# Run all tests
pytest tests/ -v

# Run specific test types
pytest tests/ -v -m unit              # Unit tests only
pytest tests/ -v -m integration       # Integration tests only
pytest tests/ -v -m mcp              # MCP tests only

# Run with coverage
pytest tests/ --cov=agents --cov-report=html

# Frontend tests
cd frontend
npm test
```

## Configuration

### Environment Variables (.env)
Key configuration options in `backend/.env`:
- `OPENROUTER_API_KEY` - Required for AI functionality
- `DEFAULT_PLANNING_MODEL` - Primary model for planning (e.g., openrouter/sherlock-think-alpha)
- `ENABLE_MCP_TOOLS` - Enable/disable MCP server integration
- `ENABLE_SEQUENTIAL_THINKING` - Enable advanced reasoning
- `ENABLE_CONTEXT7` - Enable documentation fetching

### Model Configuration
Models are configured in `backend/agents/config/model_config.py` with fallback mechanisms. The system supports OpenRouter's extensive model catalog.

## Key Directories

- `frontend/src/app/services/` - Angular services, including desktop bridge
- `backend/agents/` - AI agent implementations and configuration
- `backend/agents/tools/` - Agent tools including Godot integration
- `backend/api/` - FastAPI route handlers
- `backend/services/` - Backend services for Godot monitoring and execution
- `backend/database/` - SQLite database for session persistence and metrics
- `godot-plugin/addons/godoty/` - Godot Engine plugin files

## Agent Capabilities
- Always run **snyk_code_scan** tool for new first party code that is generated in a Snyk-supported language.
- If any security issues are found based on newly introduced or modified code or dependencies, attempt to fix the issues using the results context from **Snyk**.
- Rescan the code after fixing the issues to ensure that the issues were fixed and that there are no newly introduced issues.
- Repeat this process until no new issues are found.

### Tool Integration
- **File System Operations** - Read, write, and manage files
- **Web Search** - Real-time information retrieval
- **Godot Integration** - Project monitoring and debugging
- **Documentation Fetching** - Context7 integration for latest docs
- **Sequential Thinking** - Advanced problem-solving methodology

### Session Management
- **Conversation Persistence** - Sessions saved to SQLite database
- **Multi-Agent Workflows** - Complex multi-step task execution
- **Metrics Tracking** - Token usage, cost analysis, and performance metrics

## Godot Engine Integration

### Plugin Architecture
- **Dock Panel** - Integrated UI panel within Godot Editor
- **WebSocket Server** - Real-time communication with desktop app
- **Command Executor** - Execute GDScript commands and editor actions
- **Debug Tools** - Scene analysis and debugging utilities

### Development Workflow
1. Run Godoty desktop application
2. Open Godot project with plugin enabled
3. Use dock panel to request AI assistance
4. Agent analyzes project context and provides targeted help

## Database Schema

### Session Management
- Sessions stored in SQLite database (`backend/database/session.db`)
- Hybrid incremental persistence for performance
- Conversation history with agent responses
- Metrics tracking including token usage and costs

### Key Tables
- `chat_sessions` - Session metadata and configuration
- `session_messages` - Conversation history
- `workflow_metrics` - Performance and usage analytics

## Development Guidelines

### Agent Development
- Use Strands Agents framework for new agent implementations
- Implement proper error handling with graceful degradation
- Add comprehensive logging for debugging
- Include unit tests for all agent functionality

### Frontend Development
- Follow Angular architecture patterns
- Use TailwindCSS for styling
- Implement proper TypeScript typing
- Use DesktopService for Python communication

### Backend API Development
- Follow FastAPI conventions with proper HTTP status codes
- Implement async/await patterns for performance
- Use Pydantic for request/response validation
- Add comprehensive error handling

### Testing
- Write unit tests for all new functionality
- Use pytest markers for test categorization
- Mock external dependencies (APIs, file system)
- Include integration tests for API endpoints

## Troubleshooting

### Common Issues
- **Import Errors**: Run pytest from backend directory
- **MCP Server Failures**: Check Node.js availability and MCP configuration
- **Godot Connection**: Verify plugin is enabled and WebSocket port is available
- **Frontend Build**: Clear npm cache with `npm install --cache /tmp/.npm-cache`

### Debug Commands
```bash
# Test MCP availability
uvx mcp-server-sequential-thinking --help
npx -y @context7/mcp-server --help

# Check environment
cd backend && python -c "from dotenv import load_dotenv; load_dotenv(); import os; print('API Key:', bool(os.getenv('OPENROUTER_API_KEY')))"

# Test agent without full app
cd backend && python -c "from agents.planning_agent import PlanningAgent; print('Agent import successful')"
```

## Package Information

### Python Dependencies
Key packages from `backend/requirements.txt`:
- `fastapi==0.115.0` - Web framework
- `strands-agents>=0.2.0` - AI agent framework
- `pywebview==5.3` - Desktop application wrapper
- `mcp>=1.0.0` - Model Context Protocol support
- `sqlalchemy>=2.0.0` - Database ORM

### Node.js Dependencies
Key packages from `frontend/package.json`:
- `@angular/*: ^20.3.0` - Angular framework
- `tailwindcss: ^4.1.17` - CSS framework

## API Documentation

When running, access:
- **Swagger UI**: http://127.0.0.1:8000/docs
- **ReDoc**: http://127.0.0.1:8000/redoc

Key endpoints:
- `GET /api/agent/health` - Agent system status
- `POST /api/agent/plan/stream` - Generate plan with streaming
- `POST /api/agent/reset` - Reset conversation history
- `GET /api/agent/config` - Get agent configuration