# Godot Assistant - Complete Setup Guide

## 🎯 Overview

This guide helps you set up the Godot Assistant with Strands agents, MCP (Model Context Protocol) integration, and improved file system tools. The system includes:

- **Strands Agents Framework** - Advanced AI agent system with streaming capabilities
- **MCP Server Integration** - Sequential thinking and documentation retrieval tools
- **Refactored File System Tools** - Type-safe, well-documented file operations
- **FastAPI Backend** - RESTful API with WebSocket support
- **PyWebView Desktop App** - Native desktop application wrapper

## Step 0: Virtual Environment Setup

### 0.1 Create Virtual Environment

First, create a Python virtual environment to isolate dependencies:

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment (Windows)
source ./venv/Scripts/activate

# Verify activation (should show venv path)
which python
```

### 0.2 Install Dependencies

**Option A: Install from requirements-web-only.txt (Recommended)**

This includes all core dependencies without PyWebView:

```bash
pip install -r requirements-web-only.txt
```

**Option B: Manual installation**

```bash
# Install core dependencies
pip install fastapi uvicorn[standard] httpx aiofiles beautifulsoup4

# Install Strands agents framework
pip install strands-agents

# Optional: PyWebView for desktop app (may require additional setup on some systems)
pip install pywebview==5.3
```

**Note:** PyWebView may have installation issues on some Python versions/systems due to native dependencies. If you encounter build errors, you can still run the application as a web server without the desktop wrapper.

### 0.3 Verify Installation

Test that the core dependencies are working:

```bash
# Test basic imports
python -c "from strands import Agent; from agents.models import OpenRouterModel; print('Core imports successful')"
```

## ✅ Prerequisites Complete!

All core dependencies have been installed successfully. Follow these steps to configure and run the complete system.

## Step 1: Get an OpenRouter API Key

1. Visit [OpenRouter](https://openrouter.ai/)
2. Sign up or log in
3. Navigate to [Keys](https://openrouter.ai/keys)
4. Create a new API key
5. Copy the API key

## Step 2: Configure Environment

Edit the `.env` file in the backend directory:

```bash
nano .env  # or use your preferred editor
```

### 2.1 Add Your OpenRouter API Key

```env
OPENROUTER_API_KEY=sk-or-v1-your-actual-api-key-here
```

**Important:** Replace `your_openrouter_api_key_here` with your actual API key!

### 2.2 Configure Model and Agent Settings

The default model is `openai/gpt-4-turbo`. You can customize it:

```env
# Primary model configuration
DEFAULT_PLANNING_MODEL=anthropic/claude-3.5-sonnet
# Alternative options:
# DEFAULT_PLANNING_MODEL=openai/gpt-4-turbo
# DEFAULT_PLANNING_MODEL=anthropic/claude-3-opus
# DEFAULT_PLANNING_MODEL=google/gemini-pro

# Agent configuration
AGENT_MAX_TOKENS=4000
AGENT_TEMPERATURE=0.7

# System prompt (customize for your specific use case)
SYSTEM_PROMPT="You are a helpful planning assistant for Godot game development. Create detailed, actionable plans."
```

### 2.3 Configure MCP Server Integration

The system includes two MCP servers for enhanced capabilities:

```env
# Sequential Thinking MCP Server - For structured problem-solving
ENABLE_SEQUENTIAL_THINKING=true
SEQUENTIAL_THINKING_COMMAND=npx
SEQUENTIAL_THINKING_ARGS=-y,@modelcontextprotocol/server-sequential-thinking

# Context7 MCP Server - For documentation retrieval
ENABLE_CONTEXT7=true
CONTEXT7_COMMAND=npx
CONTEXT7_ARGS=-y,@upstash/context7-mcp
```

**Note:** MCP servers are automatically managed. No additional setup required.

### 2.4 Security and Performance Settings

```env
# CORS settings (update for production)
CORS_ORIGINS=http://localhost:4200,http://127.0.0.1:4200

# File system security (restrict access to specific directories)
ALLOWED_DIRECTORIES=/Users/eugene/Documents/Github/Godot-Assistant,/tmp

# Performance tuning
MAX_CONCURRENT_REQUESTS=10
REQUEST_TIMEOUT=120
```

## Step 3: Verify Setup and Dependencies

### 3.1 Check Basic Imports

```bash
python test_imports.py
```

You should see:
```
✓ ALL IMPORTS SUCCESSFUL!
```

### 3.2 Verify MCP Server Installation

```bash
# Check if npx is available
npx --version

# Test MCP server connectivity
python test_mcp_integration.py
```

Expected output:
```
✅ Sequential thinking MCP server connected! (1 tool available)
✅ Context7 MCP server connected! (2 tools available)
```

### 3.3 Test Refactored File System Tools

```bash
python test_refactored_tools.py
```

This tests the improved type safety and error handling:
```
🔧 Testing Refactored File System Tools
🎉 ALL TESTS COMPLETED SUCCESSFULLY! 🎉
```

## Step 4: Start the Application

### 4.1 Standard Startup

```bash
# Make sure virtual environment is activated first
source ./venv/Scripts/activate

# Run the application
python main.py
```

This will:
1. **Initialize MCP servers** (sequential-thinking and context7)
2. **Start FastAPI server** on http://127.0.0.1:8000
3. **Open PyWebView window** with your desktop application (if installed)
4. **Enable planning agent** with streaming capabilities
5. **Load refactored file system tools** with improved error handling

### 4.2 Web-Only Startup (if PyWebView installation failed)

If you encountered issues installing PyWebView, you can run the application as a web server only:

```bash
# Make sure virtual environment is activated first
source ./venv/Scripts/activate

# Run only the FastAPI server
python -c "
import uvicorn
from api.agent_router import app
uvicorn.run(app, host='127.0.0.1', port=8000)
"
```

This will start the FastAPI server on http://127.0.0.1:8000 without the desktop wrapper.

### 4.3 Startup Sequence Details

You'll see output similar to:
```
🔧 Godot Assistant Starting Up...
✅ MCP servers initialized: sequential-thinking (1 tools), context7 (2 tools)
🚀 FastAPI server starting on http://127.0.0.1:8000
📱 PyWebView window opening...
✨ Planning agent ready with model: anthropic/claude-3.5-sonnet
```

## Step 5: Comprehensive Testing

### 5.1 Test the Planning Agent

Once the server is running, open a new terminal:

```bash
# In a new terminal window
cd backend
source venv/bin/activate
python test_agent.py
```

This comprehensive test suite includes:
- ✅ **Health check** - Verify agent and API status
- ✅ **Configuration verification** - Check all settings
- ✅ **Non-streaming plan generation** - Basic functionality
- ✅ **Streaming plan generation** - Real-time response testing
- ✅ **MCP integration testing** - Verify external tools work
- ✅ **Conversation reset** - Memory management testing

### 5.2 Test File System Tools

```bash
python test_refactored_tools.py
```

Tests the improved file system capabilities:
- ✅ **Type safety verification** - Proper TypedDict usage
- ✅ **Error handling** - Comprehensive error scenarios
- ✅ **Documentation examples** - Working examples from docstrings
- ✅ **Metadata and logging** - Enhanced debugging information

### 5.3 Test MCP Integration

```bash
python test_mcp_integration.py
```

Validates the external tool integration:
- ✅ **Sequential thinking server** - Structured problem-solving
- ✅ **Context7 server** - Documentation retrieval
- ✅ **Tool management** - Dynamic loading and cleanup

## Available API Endpoints

Once the server is running, you can access:

### Documentation
- **Swagger UI:** http://127.0.0.1:8000/docs - Interactive API documentation
- **ReDoc:** http://127.0.0.1:8000/redoc - Alternative API documentation
- **OpenAPI Spec:** http://127.0.0.1:8000/openapi.json - Machine-readable spec

### Planning Agent Endpoints

#### Core Agent Operations
- `GET /api/agent/health` - Check agent status and configuration
- `GET /api/agent/config` - Get current agent configuration
- `POST /api/agent/plan` - Generate plan (non-streaming response)
- `POST /api/agent/plan/stream` - Generate plan with real-time streaming
- `POST /api/agent/reset` - Reset conversation context

#### Example cURL Commands

**Basic Plan Generation:**
```bash
curl -X POST http://localhost:8000/api/agent/plan \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a plan for building a 2D platformer game in Godot",
    "reset_conversation": false
  }'
```

**Streaming Plan Generation:**
```bash
curl -X POST http://localhost:8000/api/agent/plan/stream \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Design a character controller for a 3D RPG",
    "reset_conversation": false
  }' \
  --no-buffer
```

**Health Check:**
```bash
curl -X GET http://localhost:8000/api/agent/health
```

## Stripe E2E Testing (Local Development)

### Prerequisites

1. **Stripe CLI** - Install from https://stripe.com/docs/stripe-cli
2. **Supabase CLI** - Install from https://supabase.com/docs/guides/cli
3. **Test credentials** - Stripe test API keys and webhook secret

### Setup Steps

#### 1. Start Supabase Locally

```bash
# From the project root (where supabase/ folder exists)
cd /path/to/Godoty
supabase start
```

This will output local credentials including the service role key.

#### 2. Configure Environment

Copy the example file and fill in your values:

```bash
cp backend/.env.e2e.local.example backend/.env.e2e.local
```

Edit `backend/.env.e2e.local`:
```env
SUPABASE_URL=http://localhost:54321
SUPABASE_SERVICE_ROLE_KEY=<from supabase start output>
STRIPE_WEBHOOK_URL=http://localhost:54321/functions/v1/stripe-webhook
STRIPE_WEBHOOK_SECRET=<from stripe listen output>
STRIPE_API_VERSION=2025-11-17.clover
```

#### 3. Serve Edge Functions Locally

```bash
# In a new terminal
supabase functions serve --env-file ./supabase/.env.local
```

#### 4. Start Stripe Webhook Forwarding

```bash
# In a new terminal
stripe listen --forward-to http://localhost:54321/functions/v1/stripe-webhook
```

Copy the webhook signing secret (starts with `whsec_`) to your `.env.e2e.local`.

#### 5. Run E2E Tests

```bash
cd backend
source venv/bin/activate  # or venv/Scripts/activate on Windows

# Load the E2E environment
export $(cat .env.e2e.local | xargs)

# Run Stripe E2E tests
pytest tests/test_stripe_e2e.py -v -m e2e --capture=no
```

### Running Webhook Unit Tests

```bash
# From supabase/functions/stripe-webhook/
deno test --allow-env --allow-net index.test.ts
```

### Credit Mapping (Bonus Structure)

The webhook maps payment amounts to credits with bonuses:

| Payment | Base Credits | Bonus | Total Credits |
|---------|--------------|-------|---------------|
| $5.00   | 5            | 0%    | 5 credits     |
| $10.00  | 10           | 20%   | 12 credits    |
| $20.00  | 20           | 25%   | 25 credits    |

### Desktop Integration Endpoints

#### PyWebView Integration
- `GET /api/desktop/system-info` - Get system information
- `POST /api/desktop/save-file` - Save file using native dialogs
- `GET /api/desktop/version` - Get application version

### MCP Server Status

The system automatically manages MCP servers. You can check their status:
```bash
# Check active MCP tools in logs
# Look for messages like:
# ✅ MCP servers initialized: sequential-thinking (1 tools), context7 (2 tools)
```

## Troubleshooting

### 🔑 API Key Issues

#### "Warning: OPENROUTER_API_KEY is not set"
- Make sure you've edited the `.env` file
- Verify the API key is correct (starts with `sk-or-v1-`)
- Restart the application after changing `.env`

#### "Invalid API key" or authentication errors
- Check your OpenRouter account: https://openrouter.ai/keys
- Verify you have available credits
- Ensure the key hasn't expired

### 🤖 Model Issues

#### "Model not found" or "Invalid model"
- Check available models: https://openrouter.ai/models
- Update `DEFAULT_PLANNING_MODEL` in `.env`
- Some models require special access or credits

#### High costs/token usage
- Reduce `AGENT_MAX_TOKENS` in `.env` (try 2000-3000)
- Use cheaper models like `anthropic/claude-3-haiku`
- Reset conversation more frequently with `/api/agent/reset`

### 🔌 MCP Server Issues

#### "Failed to initialize MCP server"
- Check that Node.js/npm is installed: `npx --version`
- Verify internet connection for package download
- Check MCP server configuration in `.env`

#### "MCP server not responding"
- Restart the application
- Check network connectivity
- Verify server arguments in configuration

### 🌐 Network Issues

#### "Connection refused" or "Network error"
- Check your internet connection
- Verify OpenRouter is accessible: https://openrouter.ai/
- Check firewall/proxy settings

#### "Port 8000 already in use"
```bash
# Find process using port 8000
lsof -i :8000
# Kill the process
kill -9 <PID>
# Or use different port in main.py
```

### 📁 File System Issues

#### "Permission denied" errors
- Check file/directory permissions
- Update `ALLOWED_DIRECTORIES` in `.env`
- Run with appropriate user permissions

#### "File not found" errors
- Verify file paths are correct
- Use absolute paths when possible
- Check working directory

### 🖥️ Desktop App Issues

#### PyWebView window not opening
- Install system dependencies:
  - macOS: `brew install python-tk`
  - Ubuntu: `sudo apt-get install python3-tk`
  - Windows: Usually included with Python

#### Window appears blank
- Check browser console for errors
- Verify FastAPI server is running
- Check CORS settings in `.env`

## Development and Debugging

### 🔍 Debug Mode

Enable detailed logging:
```bash
# Set log level in .env
LOG_LEVEL=DEBUG

# Or run with environment variable
LOG_LEVEL=DEBUG python main.py
```

### 🧪 Test Individual Components

```bash
# Test just the file system tools
python test_refactored_tools.py

# Test just MCP integration
python test_mcp_integration.py

# Test just basic imports
python test_imports.py

# Test full agent functionality
python test_agent.py
```

### 📊 Performance Monitoring

Monitor application performance:
```bash
# Check resource usage
htop  # or Activity Monitor on macOS

# Monitor API calls in logs
tail -f app.log | grep "API\|MCP\|ERROR"
```

## Next Steps

### 🚀 Quick Start
1. **Test basic functionality** - Run the included test suites
2. **Try different prompts** - Experiment with various planning scenarios
3. **Explore MCP tools** - Test sequential thinking and documentation retrieval

### 🔧 Customization
1. **Add Godot-specific tools** - Extend the file system tools for game development
2. **Customize system prompt** - Tailor to your specific use case
3. **Add more MCP servers** - Integrate additional external services
4. **Create custom agents** - Build specialized agents for different tasks

### 🌐 Production Deployment
1. **Security hardening** - Review CORS settings and access controls
2. **Performance optimization** - Add caching and connection pooling
3. **Monitoring setup** - Implement logging and alerting
4. **Frontend integration** - Connect Angular or other frontend frameworks

## Documentation Resources

### 📚 Project Documentation
- **📋 Planning Agent Guide:** `PLANNING_AGENT_README.md`
- **🔧 Refactoring Summary:** `REFACTORING_SUMMARY.md`
- **🛠️ MCP Integration Guide:** `MCP_INTEGRATION_README.md`

### 🌐 External Documentation
- **🤖 Strands Agents:** https://strandsagents.com/
- **🔗 OpenRouter API:** https://openrouter.ai/docs
- **📡 MCP Protocol:** https://modelcontextprotocol.io/
- **⚡ FastAPI:** https://fastapi.tiangolo.com/
- **📱 PyWebView:** https://pywebview.flowrl.com/

### 🧪 Testing and Development
- **🔍 API Testing:** http://127.0.0.1:8000/docs (Swagger UI)
- **📊 OpenAPI Spec:** http://127.0.0.1:8000/openapi.json
- **🔧 Type Checking:** `mypy agents/` (if mypy is installed)

## Community and Support

### 💬 Getting Help
If you encounter issues:
1. **Check console logs** - Look for detailed error messages
2. **Run test suites** - Isolate the problem component
3. **Review documentation** - Check relevant documentation files
4. **Verify configuration** - Ensure `.env` settings are correct

### 🐛 Reporting Issues
When reporting issues, include:
- Operating system and Python version
- Complete error messages and stack traces
- Configuration from `.env` (remove sensitive data)
- Steps to reproduce the problem

---

## 🎉 You're All Set!

**Your Godot Assistant is ready to use!**

1. ✅ Add your OpenRouter API key to `.env`
2. ✅ Run `python main.py` to start the application
3. ✅ Test with the provided test suites
4. ✅ Start building amazing Godot projects with AI assistance!

**Need help?** Check the documentation above or run the test suites to diagnose issues.
