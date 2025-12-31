# Godoty Desktop Application

Tauri + Vue 3 desktop application for the Godoty AI assistant.

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
           │                                   │
           │ Master Key (secure)               │ Virtual Key (limited)
           ▼                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    LiteLLM Proxy (Railway)                          │
│   - Virtual Key Validation                                          │
│   - API Key Storage (OpenAI/Anthropic) - NEVER EXPOSED              │
│   - Per-User Budget Enforcement ($5 default)                        │
│   - Model Restrictions                                               │
│   - Rate Limiting & Cost Tracking                                   │
└─────────────────────────────────────────────────────────────────────┘
```

## Security Architecture

**Why Virtual Keys?** The LITELLM_MASTER_KEY cannot be stored in the desktop app—anyone could decompile the app and steal it. Instead, we use Supabase Edge Functions as a secure middleman:

1. **User logs in** via Supabase Auth (JWT issued)
2. **Desktop calls Edge Function** with JWT to request a Virtual Key
3. **Edge Function validates JWT**, calls LiteLLM with the hidden Master Key
4. **LiteLLM issues a Virtual Key** with:
   - User-specific `$5.00` budget limit
   - 30-day expiration
   - Model restrictions (GPT-4o, Claude 3.5 Sonnet, etc.)
5. **Virtual Key cached locally** and used for all LLM requests
6. **If budget exhausted**, the key stops working—Master Key remains safe

See [brain/supabase/functions/](../brain/supabase/functions/) for Edge Function implementations.

## Features

### Model Selection
Users can select their preferred model from the chat input area:
- GPT-4o (OpenAI)
- GPT-4o Mini (OpenAI)
- Claude 3.5 Sonnet (Anthropic)
- Claude 3.5 Haiku (Anthropic)

### Credit Balance Display
Real-time credit balance shown in the chat panel:
- Remaining credits (color-coded: green/yellow/red)
- Maximum budget
- Refresh button to update balance

## Prerequisites

- Node.js 18+
- Rust (for Tauri)
- Python 3.11+ (for development/building sidecar)

## Development Setup

1. Install dependencies:
```bash
npm install
```

2. Create `.env` file from template:
```bash
cp .env.example .env
# Edit .env with your Supabase credentials
```

3. Run in development mode:
```bash
npm run tauri dev
```

This will:
- Start the Vite dev server
- Build and run the Tauri application
- Spawn the Python brain sidecar

## Building

### Build the Python Sidecar

First, build the Python brain as a standalone executable:

```bash
cd ..
./scripts/build-sidecar.sh
```

This creates a binary at `src-tauri/binaries/godoty-brain-<target-triple>`.

### Build the Desktop App

```bash
npm run tauri build
```

This creates:
- macOS: `.dmg` and `.app`
- Windows: `.msi` and `.exe`
- Linux: `.deb`, `.rpm`, and `.AppImage`

## Project Structure

```
desktop/
├── src/                    # Vue frontend source
│   ├── components/         # Vue components
│   │   ├── ChatPanel.vue   # Main chat with model selector & credits
│   │   ├── ConfirmationDialog.vue
│   │   ├── ConnectionStatus.vue
│   │   ├── MessageBubble.vue
│   │   └── Sidebar.vue
│   ├── views/              # Page views
│   │   ├── LoginView.vue
│   │   ├── MainView.vue
│   │   └── SettingsView.vue
│   ├── stores/             # Pinia stores
│   │   ├── auth.ts         # Supabase auth + virtual key management
│   │   └── brain.ts        # Brain connection & state
│   ├── lib/
│   │   ├── supabase.ts     # Supabase client
│   │   └── litellmKeys.ts  # Virtual key service (fetch, cache, expiry)
│   └── router/
│       └── index.ts        # Vue Router config
├── src-tauri/              # Tauri Rust source
│   ├── src/
│   │   ├── main.rs         # Tauri entry point
│   │   └── sidecar.rs      # Python sidecar management
│   ├── binaries/           # Bundled executables
│   └── tauri.conf.json     # Tauri configuration
└── package.json
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `VITE_SUPABASE_URL` | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase anonymous key |

## How It Works

1. **Startup**: Tauri spawns the Python brain as a sidecar process
2. **Auth**: User logs in via Supabase (email/password or OAuth)
3. **Key Generation**: Desktop requests a Virtual Key from Supabase Edge Function
4. **Connection**: Vue frontend connects to brain via WebSocket
5. **Godot**: Godot plugin connects to the same brain
6. **Chat**: User messages flow: Vue → Brain → LiteLLM Proxy (with Virtual Key) → AI
7. **Tools**: Brain calls Godot tools for perception/actuation
8. **HITL**: Confirmation requests route to Vue for user approval
9. **Credits**: Balance auto-refreshes after each message

## Deploying Edge Functions

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

4. Apply database migration:
```bash
cd brain/supabase
supabase db push
```

## Troubleshooting

### Sidecar won't start
- Check if port 8000 is available
- Verify the binary exists in `src-tauri/binaries/`
- Check console for Python errors

### Auth not working
- Verify `.env` has correct Supabase credentials
- Check Supabase dashboard for auth settings
- Ensure redirect URL is configured in Supabase

### Godot not connecting
- Make sure Godoty plugin is enabled in Godot
- Check that brain server is running on port 8000
- Verify WebSocket URL in Godot project settings
