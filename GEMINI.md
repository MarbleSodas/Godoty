# Godoty (Godot-Assistant)

Godoty is a modern desktop application designed to assist with Godot game development using AI agents. It integrates a Python backend (handling AI logic and system operations), an Angular frontend (providing the UI), and a Godot plugin (for direct engine communication).

## Project Architecture

### 1. Backend (`backend/`)
*   **Frameworks**: FastAPI, PyWebView.
*   **AI Core**: Strands Agents framework integrating with OpenRouter.
*   **Agents**:
    *   **Planning Agent**: Generates execution plans, supports streaming (SSE) and MCP (Model Context Protocol) tools like "Sequential Thinking".
    *   **Executor Agent**: Executes tasks.
*   **Key Files**:
    *   `main.py`: Entry point. Starts FastAPI and the PyWebView window.
    *   `agents/planning_agent.py`: Main logic for the planning agent.
    *   `agents/tools/`: Implementation of tools (File system, Web, MCP).
    *   `api/`: FastAPI routes (`agent_routes.py`, etc.).

### 2. Frontend (`frontend/`)
*   **Frameworks**: Angular (Latest), TailwindCSS v4, PrimeNG.
*   **Communication**: Uses `DesktopService` to bridge JavaScript and Python via PyWebView.
*   **Key Files**:
    *   `src/app/services/desktop.service.ts`: Wrapper for Python API calls.
    *   `angular.json`, `package.json`: Standard Angular configuration.

### 3. Godot Plugin (`godot-plugin/`)
*   **Name**: `godoty`.
*   **Path**: `addons/godoty/`.
*   **Function**: Connects the Godot Editor to the assistant via WebSocket.

## Setup & Usage

### Prerequisites
*   Node.js (v18+) & npm/yarn.
*   Python (3.11+).
*   Godot 4.3+.

### Installation

1.  **Frontend**:
    ```bash
    cd frontend
    npm install
    ```

2.  **Backend**:
    ```bash
    cd backend
    python3 -m venv venv
    source venv/bin/activate  # or venv\Scripts\activate on Windows
    pip install -r requirements.txt
    cp .env.example .env      # Configure OPENROUTER_API_KEY here
    ```

### Running the Application

**Option 1: Integrated Desktop Mode (Recommended)**
1.  Build the frontend:
    ```bash
    cd frontend
    npx ng build
    ```
2.  Run the backend (which launches the window):
    ```bash
    cd ../backend
    source venv/bin/activate
    python main.py
    ```

**Option 2: Development Mode (Split)**
1.  **Terminal 1 (Frontend)**:
    ```bash
    cd frontend
    npx ng serve
    ```
2.  **Terminal 2 (Backend)**:
    ```bash
    cd backend
    source venv/bin/activate
    uvicorn main:app --reload
    ```

### Testing
The backend uses `pytest`:
```bash
cd backend
pytest tests/
```

## Key Concepts
*   **MCP (Model Context Protocol)**: The backend supports MCP to extend agent capabilities with tools like "Sequential Thinking" and "Context7" (docs fetching). These are configured in `.env` and `agents/tools/mcp_tools.py`.
*   **Streaming**: The agent API supports Server-Sent Events (SSE) for real-time feedback during plan generation.
*   **PyWebView**: Acts as the bridge between the Angular UI and the Python system backend.
