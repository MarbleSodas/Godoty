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

### Debugging the Godot Plugin

- Use `print()` statements in GDScript
- Check Godot's Output tab
- Enable verbose logging in the plugin

## Working on the Tauri App

### Frontend Development

The frontend is built with Angular and TypeScript.

**Running in development mode:**
```bash
cd tauri-app
bun run tauri dev
```

This command will:
1. Start the Angular dev server on `http://localhost:4200`
2. Launch the Tauri application window
3. Enable hot-reload for both frontend and backend changes

**Key files:**
- `src/app/` - Angular application components
- `src/main.ts` - Application entry point
- `src/styles.css` - Global styles
- `angular.json` - Angular configuration

**Adding new UI features:**
1. Create a new component using Angular CLI: `bun run ng generate component my-component`
2. Import and use it in your app module or standalone components
3. Add styles in the component's CSS file

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

### Debugging the Tauri Application

#### Development Mode Debugging

**1. Running in Debug Mode:**
```bash
cd tauri-app
bun run tauri dev
```

This runs the app with:
- Debug symbols enabled
- Console logging active
- Hot-reload for instant feedback
- DevTools available

**2. Frontend Debugging (Angular):**

Open the browser DevTools in the Tauri window:
- **Windows/Linux:** Press `Ctrl + Shift + I` or `F12`
- **macOS:** Press `Cmd + Option + I`

The DevTools provide:
- **Console:** View JavaScript logs, errors, and warnings
- **Network:** Monitor API calls and WebSocket connections
- **Elements:** Inspect DOM and styles
- **Sources:** Set breakpoints in TypeScript code
- **Application:** View local storage and session data

**3. Backend Debugging (Rust):**

Rust logs appear in the terminal where you ran `bun run tauri dev`.

Add debug logging in your Rust code:
```rust
println!("Debug: {}", variable);
eprintln!("Error: {}", error);
```

For structured logging, use the `log` crate:
```rust
use log::{info, warn, error, debug};

info!("Application started");
debug!("Processing command: {:?}", command);
error!("Failed to connect: {}", err);
```

**4. WebSocket Debugging:**

Monitor WebSocket connections:
- Open DevTools → Network tab
- Filter by "WS" (WebSocket)
- Click on the connection to see messages
- View sent/received frames in real-time

**5. Debugging with VS Code:**

Create `.vscode/launch.json`:
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "type": "lldb",
      "request": "launch",
      "name": "Tauri Development Debug",
      "cargo": {
        "args": [
          "build",
          "--manifest-path=./src-tauri/Cargo.toml",
          "--no-default-features"
        ]
      },
      "preLaunchTask": "ui:dev"
    },
    {
      "type": "lldb",
      "request": "launch",
      "name": "Tauri Production Debug",
      "cargo": {
        "args": [
          "build",
          "--release",
          "--manifest-path=./src-tauri/Cargo.toml"
        ]
      },
      "preLaunchTask": "ui:build"
    }
  ]
}
```

Install the required VS Code extensions:
- [rust-analyzer](https://marketplace.visualstudio.com/items?itemName=rust-lang.rust-analyzer)
- [CodeLLDB](https://marketplace.visualstudio.com/items?itemName=vadimcn.vscode-lldb)
- [Tauri](https://marketplace.visualstudio.com/items?itemName=tauri-apps.tauri-vscode)

Set breakpoints in Rust code and press `F5` to start debugging.

#### Production Build Debugging

**1. Build in Debug Mode:**
```bash
cd tauri-app
bun run tauri build --debug
```

This creates a debug build with:
- Debug symbols included
- Optimizations disabled
- Faster compilation
- Larger binary size

The output will be in `src-tauri/target/debug/bundle/`

**2. Build in Release Mode:**
```bash
cd tauri-app
bun run tauri build
```

This creates an optimized production build in `src-tauri/target/release/bundle/`

**3. Testing the Built Application:**

After building, test the standalone application:
- **Windows:** Run the `.exe` from `src-tauri/target/release/bundle/nsis/`
- **macOS:** Open the `.app` from `src-tauri/target/release/bundle/macos/`
- **Linux:** Run the AppImage from `src-tauri/target/release/bundle/appimage/`

**4. Debugging Production Issues:**

Enable logging in production builds by setting environment variables:

**Windows (PowerShell):**
```powershell
$env:RUST_LOG="debug"
.\tauri-app.exe
```

**macOS/Linux:**
```bash
RUST_LOG=debug ./tauri-app
```

View logs:
- **Windows:** Check `%APPDATA%\com.godoty.app\logs\`
- **macOS:** Check `~/Library/Logs/com.godoty.app/`
- **Linux:** Check `~/.local/share/com.godoty.app/logs/`

#### Common Debugging Scenarios

**1. Application Won't Start:**
- Check terminal for Rust compilation errors
- Verify Angular dev server started on port 4200
- Check for port conflicts
- Review `tauri.conf.json` configuration

**2. Frontend Not Loading:**
- Verify `beforeDevCommand` in `tauri.conf.json` is correct
- Check that `devUrl` points to `http://localhost:4200`
- Ensure Angular dev server is running
- Check browser console for errors

**3. Backend Commands Failing:**
- Check Rust terminal output for errors
- Verify command is registered in `invoke_handler`
- Check command name matches between frontend and backend
- Review parameter types and serialization

**4. WebSocket Connection Issues:**
- Verify Godot plugin is running
- Check firewall settings
- Confirm port 9001 is not blocked
- Review WebSocket frames in DevTools

**5. Build Failures:**
- Clear build cache: `cd src-tauri && cargo clean`
- Update dependencies: `bun install && cargo update`
- Check Rust version: `rustc --version` (should be 1.70+)
- Verify all required system dependencies are installed

#### Performance Profiling

**1. Frontend Performance:**
- Use Chrome DevTools Performance tab
- Record and analyze runtime performance
- Check for memory leaks in Memory tab
- Use Lighthouse for overall performance audit

**2. Backend Performance:**
- Use `cargo flamegraph` for CPU profiling
- Add timing logs around critical sections
- Monitor memory usage with system tools
- Use `cargo bench` for benchmarking

#### Useful Commands

```bash
# Check Rust code for errors without building
cd tauri-app/src-tauri
cargo check

# Run Rust tests
cargo test

# Format Rust code
cargo fmt

# Lint Rust code
cargo clippy

# Build frontend only
cd tauri-app
bun run build

# Run Angular tests
bun run test

# Clean all build artifacts
cd src-tauri
cargo clean
cd ..
rm -rf dist node_modules
bun install
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

