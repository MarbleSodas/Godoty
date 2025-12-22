# Tech Stack

## Programming Languages
- **Python 3.11+:** Used for the AI brain sidecar, agent orchestration, and tool execution.
- **TypeScript / JavaScript:** Used for the Vue 3 desktop frontend.
- **Rust:** Used for the Tauri native shell and system-level operations.
- **GDScript:** Used for the Godot Engine editor plugin.

## Frameworks & Libraries
### Backend (AI Brain)
- **FastAPI:** High-performance web framework for the sidecar server.
- **Agno:** Agentic AI framework used for multi-agent orchestration and workflows.
- **LiteLLM:** Universal LLM proxy for model-agnostic API interactions.
- **Pydantic:** Data validation and settings management.

### Frontend (Desktop App)
- **Vue 3:** Modern JavaScript framework for the user interface.
- **Tauri:** Framework for building tiny, fast binaries for all major desktop platforms.
- **Pinia:** State management for the Vue application.
- **Tailwind CSS:** Utility-first CSS framework for styling.

### Godot Integration
- **Godot 4.x:** The primary game engine target.
- **Godoty Connector:** Custom GDScript plugin for editor-to-brain communication.

## Infrastructure & Services
- **Supabase:** Used for user authentication, edge functions, and credit management.
- **WebSockets:** Real-time communication protocol for local system integration.
- **JSON-RPC 2.0:** Message format protocol for all inter-component communication.

## Development & Build Tools
- **Vite:** Next-generation frontend tooling for the Vue app.
- **PyInstaller:** Used to package the Python brain as a standalone binary sidecar.
- **Git:** Version control.
