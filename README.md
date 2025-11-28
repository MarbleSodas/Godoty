# PyWebView Desktop App

A modern desktop application built with **PyWebView**, **Angular**, **TailwindCSS**, and **FastAPI**.

## Tech Stack

### Frontend
- **Angular 20.3.0** - Modern TypeScript framework
- **TailwindCSS v4** - Utility-first CSS framework
- **TypeScript** - Type-safe development

### Backend
- **FastAPI** - High-performance Python web framework
- **PyWebView** - Cross-platform native webview wrapper
- **Uvicorn** - Lightning-fast ASGI server
- **Strands Agents** - AI agent framework for planning and automation
- **OpenRouter** - Multi-model API integration

## Project Structure

```
Godot-Assistant/
├── frontend/               # Angular application
│   ├── src/
│   │   ├── app/
│   │   │   ├── services/
│   │   │   │   └── desktop.service.ts  # PyWebView API wrapper
│   │   │   ├── app.ts                  # Main component
│   │   │   ├── app.html                # Main template
│   │   │   └── app.config.ts           # App configuration
│   │   ├── styles.scss                 # Global styles
│   │   └── index.html
│   ├── angular.json
│   ├── package.json
│   └── .postcssrc.json                 # PostCSS config
│
├── backend/                # Python backend
│   ├── main.py            # FastAPI app + PyWebView launcher
│   ├── agents/            # AI planning agent
│   │   ├── config/        # Modular configuration
│   │   │   ├── model_config.py    # Model settings
│   │   │   ├── tool_config.py     # Tool & MCP settings
│   │   │   ├── prompts.py         # System prompts
│   │   │   └── validators.py      # Config validation
│   │   ├── models/        # Custom model providers (OpenRouter)
│   │   ├── tools/         # Agent tools (file system, web, Godot, MCP)
│   │   ├── planning_agent.py  # Single planning agent
│   │   └── multi_agent_manager.py  # Session management
│   ├── api/               # API routes
│   │   ├── agent_routes.py    # Agent endpoints
│   │   ├── health_routes.py   # Health endpoints
│   │   └── sse_routes.py      # SSE streaming
│   ├── tests/             # Test suite
│   │   ├── conftest.py        # Shared pytest fixtures
│   │   ├── test_planning_agent.py  # Agent tests
│   │   ├── test_api_endpoints.py   # API tests
│   │   └── README.md          # Testing guide
│   ├── requirements.txt   # Python dependencies
│   ├── .env.example      # Environment template
│   ├── PLANNING_AGENT_README.md  # Agent documentation
│   └── venv/             # Virtual environment
│
└── dist/                  # Angular build output
    └── browser/           # Production files
```

## Setup Instructions

### Prerequisites

- **Node.js** (v18 or higher) - [Download](https://nodejs.org/)
- **Python** (3.11 or higher) - [Download](https://www.python.org/)
- **npm** or **yarn** - Package manager for Node.js

### 1. Frontend Setup

Navigate to the frontend directory and install dependencies:

```bash
cd frontend
npm install --cache /tmp/.npm-cache
```

### 2. Backend Setup

Navigate to the backend directory and set up Python environment:

```bash
cd ../backend

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Build the Frontend

Build the Angular application for production:

```bash
cd ../frontend
npx ng build --configuration production
```

The build output will be in `../dist/browser/`.

## Running the Application

### Development Mode

**Option 1: Run Frontend and Backend Separately**

Terminal 1 - Run Angular dev server:
```bash
cd frontend
npx ng serve
# Access at http://localhost:4200
```

Terminal 2 - Run FastAPI backend:
```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload
```

**Option 2: Run Integrated Desktop App**

```bash
# Make sure Angular is built first
cd frontend
npx ng build

# Run the desktop app
cd ../backend
source venv/bin/activate
python main.py
```

### Production Mode

1. Build the frontend:
```bash
cd frontend
npx ng build --configuration production
```

2. Run the desktop application:
```bash
cd ../backend
source venv/bin/activate
python main.py
```

The application will:
1. Start the FastAPI server on `http://127.0.0.1:8000`
2. Open a PyWebView window displaying the Angular app
3. Enable JavaScript-Python communication via `window.pywebview.api`

## Features

### JavaScript-Python Communication

The `DesktopService` in Angular provides seamless communication with Python:

```typescript
// In Angular component
constructor(private desktop: DesktopService) {}

// Call Python methods
this.desktop.getSystemInfo().subscribe(info => {
  console.log(info);
});
```

### Python API Methods

Available methods in `backend/main.py`:

- `get_system_info()` - Returns platform, version, and system details
- `save_file(data)` - Save files with native dialogs
- `open_file_dialog()` - Open file selection dialogs

### FastAPI Endpoints

RESTful API endpoints:

- `GET /api/health` - Health check endpoint
- `GET /api/data` - Sample data endpoint
- `POST /api/echo` - Echo test endpoint

### Planning Agent (NEW!)

The application includes an AI-powered planning agent built with Strands Agents and OpenRouter:

- **Streaming responses** via Server-Sent Events
- **Tool calling** with file system and web search capabilities
- **Custom OpenRouter integration** supporting multiple models
- **RESTful API** for plan generation

#### Quick Start

1. Copy the environment template:
   ```bash
   cd backend
   cp .env.example .env
   ```

2. Add your OpenRouter API key to `.env`:
   ```env
   OPENROUTER_API_KEY=your_api_key_here
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Test the agent:
   ```bash
   python test_agent.py
   ```

#### Planning Agent Endpoints

- `GET /api/agent/health` - Check agent status
- `POST /api/agent/plan` - Generate plan (non-streaming)
- `POST /api/agent/plan/stream` - Generate plan with streaming
- `POST /api/agent/reset` - Reset conversation history
- `GET /api/agent/config` - Get agent configuration

#### Example Usage

```bash
curl -X POST http://localhost:8000/api/agent/plan/stream \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a plan for building a 2D platformer in Godot",
    "reset_conversation": false
  }' \
  --no-buffer
```

For detailed documentation, see [backend/PLANNING_AGENT_README.md](backend/PLANNING_AGENT_README.md)

## Testing

The backend includes a comprehensive test suite using pytest:

```bash
cd backend

# Run all tests
pytest tests/ -v

# Run only unit tests (fast)
pytest tests/ -v -m unit

# Run only integration tests
pytest tests/ -v -m integration

# Run with coverage
pytest tests/ --cov=agents --cov-report=html
```

For more details, see [backend/tests/README.md](backend/tests/README.md)

## Development Workflow

### Adding New Features

1. **Frontend (Angular)**:
   - Add components in `frontend/src/app/`
   - Style with TailwindCSS utilities
   - Call Python methods via `DesktopService`

2. **Backend (Python)**:
   - Add API routes to `main.py`
   - Expose Python methods in `DesktopApi` class
   - Handle file operations, system calls, etc.

### Hot Reload

- **Angular**: Use `npx ng serve` for instant frontend updates
- **FastAPI**: Use `uvicorn main:app --reload` for backend changes

## Packaging for Distribution

### Using PyInstaller

```bash
cd backend
source venv/bin/activate
pip install pyinstaller

# Create executable
pyinstaller --onefile --windowed \
  --add-data "../dist/browser:dist/browser" \
  main.py
```

The executable will be in `backend/dist/`.

## Troubleshooting

### NPM Cache Issues

If you encounter npm cache permission errors:
```bash
npm install --cache /tmp/.npm-cache
```

### PyWebView Window Not Opening

Make sure:
1. Angular app is built (`dist/browser/` exists)
2. Virtual environment is activated
3. All Python dependencies are installed

### FastAPI Not Serving Static Files

Verify:
1. `dist/browser/index.html` exists
2. Path in `main.py` points to correct directory

## API Documentation

Once the app is running, access FastAPI auto-generated docs at:
- **Swagger UI**: http://127.0.0.1:8000/docs
- **ReDoc**: http://127.0.0.1:8000/redoc

## Resources

- [Angular Documentation](https://angular.dev)
- [TailwindCSS Documentation](https://tailwindcss.com)
- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [PyWebView Documentation](https://pywebview.flowrl.com)

## License

This project is licensed under the MIT License.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

Built with ❤️ using Angular, TailwindCSS, FastAPI, and PyWebView
