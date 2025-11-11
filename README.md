# Godoty - AI-Powered Godot Development Assistant

An intelligent assistant that helps developers create games in Godot using natural language commands.

## Architecture

This project consists of three main components:

### 1. Tauri Application (`tauri-app/`)
- **Frontend**: React + TypeScript UI for user interaction
- **Backend**: Rust backend handling WebSocket client and AI integration
- **Purpose**: Provides the user interface and orchestrates AI processing

### 2. Godot Plugin (`godot-plugin/`)
- **Language**: GDScript
- **Purpose**: WebSocket server running inside Godot Editor
- **Functionality**: Receives commands and manipulates the editor using EditorPlugin API

### 3. Shared Protocol (`protocol/`)
- **Purpose**: Defines the JSON-based command protocol
- **Usage**: Ensures consistent communication between Tauri and Godot

## How It Works

1. **User Input**: Type a natural language command (e.g., "Add a 2D player character with a sprite and collision shape")
2. **AI Processing**: The AI planner agent:
   - Performs RAG search on indexed Godot documentation
   - Formulates an execution plan
   - Generates a series of commands
3. **Command Transmission**: Commands are sent via WebSocket as JSON
4. **Godot Execution**: The plugin receives and executes commands using EditorPlugin API
5. **Feedback**: Success/error messages are sent back to the UI

## Project Structure

```
godoty/
├── tauri-app/          # Tauri application
│   ├── src/            # React frontend
│   ├── src-tauri/      # Rust backend
│   └── package.json
├── godot-plugin/       # Godot editor plugin
│   ├── addons/
│   │   └── godoty/
│   │       ├── plugin.gd
│   │       ├── websocket_server.gd
│   │       └── command_executor.gd
│   └── plugin.cfg
├── protocol/           # Shared protocol definitions
│   └── commands.json
└── README.md
```

## Getting Started

### Prerequisites
- Node.js 18+ and Bun
- Rust 1.70+
- Godot 4.x
- OpenAI API key (or other LLM provider)

### Installation

1. **Install Godot Plugin**
   - Copy `godot-plugin/addons/godoty` to your Godot project's `addons/` folder
   - Enable the plugin in Project Settings → Plugins

2. **Setup Tauri App**
   ```bash
   cd tauri-app
   bun install
   bun tauri dev
   ```

3. **Configure AI**
   - Set your API key in the Tauri app settings
   - The app will automatically index Godot documentation

## Development

### Running in Development Mode

1. Start the Godot Editor with the plugin enabled
2. Run the Tauri app: `cd tauri-app && bun run tauri dev`
3. The app will automatically connect to the Godot plugin

### Debugging
- **Frontend:** Press `Ctrl+Shift+I` (Windows/Linux) or `Cmd+Option+I` (macOS) to open DevTools
- **Backend:** Check terminal output where you ran `bun run tauri dev`
- **WebSocket:** Use DevTools Network tab, filter by "WS"

### Testing

```bash
# Test Tauri app
cd tauri-app
bun test

# Test Godot plugin
# Run Godot with test scenes in godot-plugin/tests/
```



## Command Protocol

Commands are sent as JSON objects via WebSocket:

```json
{
  "action": "create_node",
  "type": "CharacterBody2D",
  "name": "Player",
  "parent": null,
  "properties": {}
}
```

See `protocol/commands.json` for the full specification.

## License

MIT

