# Godoty

**Local-first AI assistant for the Godot Engine** — A desktop app with sidecar AI brain + headless editor plugin that brings agentic AI assistance directly into your game development workflow.

## Features

- 🤖 **Multi-Agent Team**: Lead Developer, GDScript Coder, Systems Architect, and Observer agents working together
- 👁️ **Deep Editor Integration**: Screenshots, scene tree analysis, script introspection via Godot plugin
- �️ **Modern Desktop App**: Beautiful Tauri + Vue 3 interface for chat and confirmations
- �🔒 **Human-in-the-Loop (HITL)**: All file modifications require explicit user approval
- 🔌 **Model Agnostic**: Works with any LLM via LiteLLM (OpenAI, Claude, Ollama, etc.)
- 📊 **Token Tracking**: Monitor and budget your LLM usage with credit balance display

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User's Desktop                               │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                     Tauri Application                          │  │
│  │  ┌─────────────────┐     ┌─────────────────────────────────┐  │  │
│  │  │   Vue Frontend  │────►│   Python Brain (Sidecar)        │  │  │
│  │  │   - Chat UI     │     │   - Agent Orchestration         │  │  │
│  │  │   - Auth Login  │ WS  │   - Tool Execution              │  │  │
│  │  │   - HITL Dialog │◄────│   - Virtual Key Forwarding      │  │  │
│  │  │   - Model Select│     │   - Model Selection             │  │  │
│  │  │   - Credit View │     └─────────────────────────────────┘  │  │
│  │  └─────────────────┘                                          │  │
│  └───────────────────────────────────────────────────────────────┘  │
│           │                        │                                 │
│           │ HTTPS                  │ WebSocket                       │
│           ▼                        ▼                                 │
│  ┌─────────────────┐    ┌─────────────────────────────────────────┐ │
│  │ Supabase Edge   │    │             Godot Editor                 │ │
│  │ Functions       │    │  ┌───────────────────────────────────┐  │ │
│  │ - Generate Key  │    │  │  Godoty Connector Plugin (Headless)│  │ │
│  │ - Get Balance   │    │  │  - Screenshot capture              │  │ │
│  └─────────────────┘    │  │  - Scene tree introspection       │  │ │
│                         │  │  - File read/write                 │  │ │
│                         │  └───────────────────────────────────┘  │ │
│                         └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- **Node.js 18+** — For the Vue frontend
- **Rust** — For the Tauri native shell ([Install Rust](https://rustup.rs/))
- **Python 3.11+** — For the AI brain sidecar
- **Godot 4.x** — The game engine

## Quick Start (Development)

### 1. Clone and Setup

```bash
git clone https://github.com/MarbleSodas/Godoty.git
cd Godoty
```

### 2. Setup Python Brain

```bash
cd brain
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 3. Configure Environment

Create a `.env` file in the `desktop/` directory (you can copy from `.env.example` if available):

```bash
cd ../desktop
# Create .env file with your Supabase credentials:
cat > .env << 'EOF'
VITE_SUPABASE_URL=your-supabase-url
VITE_SUPABASE_ANON_KEY=your-supabase-anon-key
EOF
```

**For development without Supabase**, you can configure the brain directly with environment variables:

```bash
# Configure your LLM (choose one approach):

# Option A: LiteLLM proxy
export GODOTY_LITELLM_BASE_URL="http://localhost:4000"
export GODOTY_MODEL="gpt-4o"
export GODOTY_API_KEY="your-api-key"

# Option B: Local models via Ollama
export GODOTY_LITELLM_BASE_URL="http://localhost:11434"
export GODOTY_MODEL="ollama/llama3"
```

### 4. Install Desktop Dependencies

```bash
cd desktop
npm install
```

### 5. Run the Desktop App (Development Mode)

```bash
npm run tauri dev
```

This will:
- Start the Vite dev server for hot-reloading
- Build and run the Tauri application
- Spawn the Python brain as a sidecar process

### 6. Install the Godot Plugin

1. Copy the `godot/addons/godoty_connector` folder to your Godot project's `addons/` directory
2. Open your project in Godot 4.x
3. Go to **Project → Project Settings → Plugins**
4. Enable **Godoty Connector**

The plugin will automatically connect to the brain on port 8000.

## Alternative: Run Brain Standalone

For development/debugging, you can run the brain server separately:

```bash
cd brain
source .venv/bin/activate
python run_brain.py --host 127.0.0.1 --port 8000 --reload
```

Health check: http://127.0.0.1:8000/health

## Usage

### Chat Interface

Use the Godoty desktop app to:
- Ask questions about GDScript and Godot APIs
- Request code generation or modifications
- Get help debugging issues
- Plan complex features

### Example Prompts

```
"How do I implement a smooth camera follow in 2D?"

"Analyze my current scene tree for common issues"

"Create a basic inventory system with Resources"

"Fix the null reference error in my player script"
```

### HITL Confirmation

When Godoty wants to modify your project (files, settings, nodes), a confirmation dialog will appear in the desktop app showing:
- What action is being proposed
- Preview of the changes
- Approve/Deny buttons

You can also edit the proposed changes before approving.

## Configuration

### Environment Variables (Brain)

| Variable | Description | Default |
|----------|-------------|---------|
| `GODOTY_LITELLM_BASE_URL` | LiteLLM proxy URL | `http://localhost:4000` |
| `GODOTY_MODEL` | Model identifier | `gpt-4o` |
| `GODOTY_API_KEY` | API key for the model | `sk-godoty` |

### Environment Variables (Desktop)

| Variable | Description |
|----------|-------------|
| `VITE_SUPABASE_URL` | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase anonymous key |

### Godot Project Settings

You can override the brain URL in your Godot project:

```
godoty/server_url = "ws://192.168.1.100:8000/ws"
```

## Building for Production

### 1. Build the Python Sidecar

First, build the Python brain as a standalone executable:

```bash
./scripts/build-sidecar.sh
```

This creates a binary at `desktop/src-tauri/binaries/godoty-brain-<target-triple>`.

### 2. Build the Desktop App

```bash
cd desktop
npm run tauri build
```

This creates:
- **macOS**: `.dmg` and `.app`
- **Windows**: `.msi` and `.exe`
- **Linux**: `.deb`, `.rpm`, and `.AppImage`

## Development

### Running Tests

```bash
cd brain
source .venv/bin/activate
pytest -v
```

### Project Structure

```
Godoty/
├── brain/                      # Python AI brain (sidecar)
│   ├── app/
│   │   ├── main.py             # FastAPI server with WebSocket
│   │   ├── agents/             # Agno agent team definitions
│   │   ├── protocol/           # JSON-RPC message handling
│   │   └── tools/              # Agent tools
│   ├── supabase/               # Edge functions for auth/keys
│   ├── run_brain.py            # Entry point for PyInstaller
│   └── pyproject.toml
│
├── desktop/                    # Tauri + Vue 3 desktop app
│   ├── src/                    # Vue frontend source
│   │   ├── components/         # Vue components (ChatPanel, etc.)
│   │   ├── views/              # Page views (Login, Main, Settings)
│   │   ├── stores/             # Pinia stores (auth, brain)
│   │   └── lib/                # Utilities (Supabase, LiteLLM keys)
│   ├── src-tauri/              # Tauri Rust source
│   │   ├── src/                # Rust code (main.rs, sidecar.rs)
│   │   └── binaries/           # Bundled sidecar executables
│   └── package.json
│
├── godot/addons/godoty_connector/  # Godot plugin (headless)
│   ├── godoty_connector.gd     # Main plugin script
│   └── plugin.cfg              # Plugin configuration
│
├── prompts/                    # Agent system prompts
│   ├── lead.yaml               # Lead Developer agent prompt
│   ├── coder.yaml              # GDScript Coder prompt
│   ├── architect.yaml          # Systems Architect prompt
│   └── observer.yaml           # Observer agent prompt
│
├── scripts/                    # Build scripts
│   ├── build-sidecar.sh        # Build Python sidecar for Tauri
│   └── deploy-edge-functions.sh
│
├── docs/
│   └── protocol.md             # Full protocol specification
│
└── tests/                      # Additional tests
```

### Adding New Tools

1. Define the tool function in `brain/app/agents/tools/`
2. Add the corresponding handler in `godot/addons/godoty_connector/godoty_connector.gd`
3. Update the protocol documentation in `docs/protocol.md`

## Deploying Edge Functions (Optional)

For production with Supabase authentication:

1. Install Supabase CLI and link your project:
```bash
brew install supabase/tap/supabase
supabase login
supabase link --project-ref <your-project-id>
```

2. Set your secrets:
```bash
supabase secrets set LITELLM_MASTER_KEY=sk-your-master-key
supabase secrets set LITELLM_URL=https://your-litellm-proxy.up.railway.app
```

3. Deploy Edge Functions:
```bash
./scripts/deploy-edge-functions.sh
```

## Troubleshooting

### Sidecar won't start
- Check if port 8000 is available
- Verify the binary exists in `desktop/src-tauri/binaries/`
- Check the console for Python errors
- Try running the brain standalone to debug

### Auth not working
- Verify `.env` has correct Supabase credentials
- Check Supabase dashboard for auth settings
- Ensure redirect URL is configured in Supabase

### Godot not connecting
- Make sure the Godoty plugin is enabled in Godot
- Check that the brain server is running on port 8000
- Verify WebSocket URL in Godot project settings

## Roadmap

- [ ] **RAG Integration**: Embed Godot documentation for accurate answers
- [ ] **pgvector Memory**: Persistent conversation history
- [ ] **Code Evaluation**: LLM-as-a-judge for quality validation
- [ ] **Multi-scene Support**: Work across multiple open scenes
- [ ] **Asset Browser Integration**: Image and resource understanding

## License

MIT

## Contributing

Contributions welcome! Please read the architectural document for design decisions.
