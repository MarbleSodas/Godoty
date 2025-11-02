# Development Guide

This guide is for developers who want to contribute to or extend Godoty.

## Architecture Overview

### Components

1. **Godot Plugin (GDScript)**
   - WebSocket server listening on port 9001
   - Command executor using EditorPlugin API
   - UI dock for status and logs

2. **Tauri Application**
   - React + TypeScript frontend
   - Rust backend with WebSocket client
   - AI integration with OpenAI

3. **Communication Protocol**
   - JSON-based command protocol
   - Defined in `protocol/commands.json`

### Data Flow

```
User Input → AI Processing → Command Generation → WebSocket → Godot Plugin → Editor Manipulation
                                                                    ↓
                                                              Response/Feedback
```

## Project Structure

```
godoty/
├── godot-plugin/           # Godot editor plugin
│   └── addons/godoty/
│       ├── plugin.gd       # Main plugin entry point
│       ├── websocket_server.gd  # WebSocket server
│       ├── command_executor.gd  # Command execution logic
│       ├── dock.gd         # UI dock script
│       └── dock.tscn       # UI dock scene
│
├── tauri-app/              # Tauri application
│   ├── src/                # React frontend
│   │   ├── components/     # React components
│   │   ├── App.tsx         # Main app component
│   │   └── main.tsx        # Entry point
│   │
│   └── src-tauri/          # Rust backend
│       └── src/
│           ├── lib.rs      # Main Tauri setup
│           ├── websocket.rs # WebSocket client
│           ├── ai.rs       # AI processing
│           └── storage.rs  # Configuration storage
│
└── protocol/               # Shared protocol
    └── commands.json       # Command definitions
```

## Development Setup

### Prerequisites

- Godot 4.x
- Rust 1.70+
- Bun
- Git

### Initial Setup

1. Clone the repository
2. Install Tauri dependencies:
   ```bash
   cd tauri-app
   bun install
   ```

3. Build Rust dependencies:
   ```bash
   bun tauri build --debug
   ```

## Working on the Godot Plugin

### Testing Changes

1. Copy the plugin to a test Godot project
2. Enable the plugin in Project Settings
3. Check the Output tab for logs
4. Test commands from the Tauri app

### Adding New Commands

1. **Define the command** in `protocol/commands.json`:
   ```json
   {
     "action": "my_new_command",
     "param1": "value",
     "param2": 123
   }
   ```

2. **Implement the handler** in `command_executor.gd`:
   ```gdscript
   func execute_command(command: Dictionary) -> Dictionary:
       var action = command.get("action", "")
       
       match action:
           "my_new_command":
               return _my_new_command(command)
           # ... other commands
   
   func _my_new_command(command: Dictionary) -> Dictionary:
       # Implementation here
       return {
           "status": "success",
           "message": "Command executed"
       }
   ```

3. **Update the AI prompt** in `tauri-app/src-tauri/src/ai.rs` to include the new command

### Debugging

- Use `print()` statements in GDScript
- Check Godot's Output tab
- Enable verbose logging in the plugin

## Working on the Tauri App

### Frontend Development

The frontend is built with React and TypeScript.

**Running in development mode:**
```bash
cd tauri-app
bun tauri dev
```

**Key files:**
- `src/App.tsx` - Main application component
- `src/components/` - Reusable React components
- `src/*.css` - Component styles

**Adding new UI features:**
1. Create a new component in `src/components/`
2. Import and use it in `App.tsx`
3. Add styles in a corresponding `.css` file

### Backend Development

The backend is written in Rust.

**Key files:**
- `src-tauri/src/lib.rs` - Main Tauri setup and commands
- `src-tauri/src/websocket.rs` - WebSocket client
- `src-tauri/src/ai.rs` - AI processing
- `src-tauri/src/storage.rs` - Configuration storage

**Adding new Tauri commands:**

1. Define the command in `lib.rs`:
   ```rust
   #[tauri::command]
   async fn my_command(param: String) -> Result<String, String> {
       // Implementation
       Ok("Success".to_string())
   }
   ```

2. Register it in the `invoke_handler`:
   ```rust
   .invoke_handler(tauri::generate_handler![
       my_command,
       // ... other commands
   ])
   ```

3. Call it from the frontend:
   ```typescript
   import { invoke } from "@tauri-apps/api/core";
   
   const result = await invoke<string>("my_command", { param: "value" });
   ```

### AI Integration

The AI processing is handled in `src-tauri/src/ai.rs`.

**Customizing the AI prompt:**

Edit the `system_prompt` in the `process_input` method to:
- Add new command types
- Improve command generation
- Add examples for better results

**Switching AI providers:**

Currently uses OpenAI. To use a different provider:
1. Update the API endpoint in `ai.rs`
2. Modify the request/response format
3. Update the API key storage if needed

## Testing

### Manual Testing

1. **Test WebSocket Connection:**
   - Start Godot with plugin enabled
   - Start Tauri app
   - Check connection status

2. **Test Commands:**
   - Try each command type
   - Verify results in Godot
   - Check error handling

3. **Test UI:**
   - Test all buttons and inputs
   - Verify status updates
   - Check command history

### Automated Testing

Currently, the project doesn't have automated tests. Contributions welcome!

**Potential test areas:**
- Command parsing and validation
- WebSocket communication
- AI prompt generation
- UI component rendering

## Building for Production

### Tauri App

```bash
cd tauri-app
bun tauri build
```

This creates platform-specific installers in `src-tauri/target/release/bundle/`

### Godot Plugin

The plugin is distributed as source code. Users copy it to their projects.

## Contributing

### Code Style

**GDScript:**
- Use tabs for indentation
- Follow Godot's naming conventions
- Add comments for complex logic

**TypeScript/React:**
- Use 2 spaces for indentation
- Use functional components with hooks
- Add TypeScript types for all props

**Rust:**
- Follow Rust standard style (use `cargo fmt`)
- Add error handling with `Result`
- Document public functions

### Pull Request Process

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request with a clear description

## Future Enhancements

### Planned Features

- [ ] RAG integration with Godot documentation
- [ ] Support for more AI providers (Anthropic, local models)
- [ ] Visual node editor integration
- [ ] Script generation and editing
- [ ] Asset management
- [ ] Multi-scene operations
- [ ] Undo/redo support
- [ ] Command templates and presets

### Ideas for Contribution

- Add more command types
- Improve AI prompts
- Create example projects
- Write documentation
- Add automated tests
- Improve error messages
- Add keyboard shortcuts
- Create video tutorials

## Resources

- [Godot Documentation](https://docs.godotengine.org/)
- [Tauri Documentation](https://tauri.app/)
- [React Documentation](https://react.dev/)
- [Rust Documentation](https://doc.rust-lang.org/)

## Getting Help

- Check existing issues on GitHub
- Read the setup and troubleshooting guides
- Ask questions in discussions

Happy coding! 🚀

