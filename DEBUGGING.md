# Debugging Guide for Godoty Tauri Application

This guide provides comprehensive debugging instructions for the Godoty Tauri application.

## Table of Contents

- [Development Environment Setup](#development-environment-setup)
- [Running in Debug Mode](#running-in-debug-mode)
- [Frontend Debugging (Angular)](#frontend-debugging-angular)
- [Backend Debugging (Rust)](#backend-debugging-rust)
- [WebSocket Debugging](#websocket-debugging)
- [IDE Integration](#ide-integration)
- [Production Build Debugging](#production-build-debugging)
- [Common Issues and Solutions](#common-issues-and-solutions)
- [Performance Profiling](#performance-profiling)

## Development Environment Setup

### Required Tools

1. **Rust** (1.70+)
   ```bash
   rustc --version
   cargo --version
   ```

2. **Bun**
   ```bash
   bun --version
   ```

3. **Tauri CLI**
   ```bash
   cd tauri-app
   bun run tauri --version
   ```

4. **VS Code Extensions** (Recommended)
   - [rust-analyzer](https://marketplace.visualstudio.com/items?itemName=rust-lang.rust-analyzer)
   - [CodeLLDB](https://marketplace.visualstudio.com/items?itemName=vadimcn.vscode-lldb)
   - [Tauri](https://marketplace.visualstudio.com/items?itemName=tauri-apps.tauri-vscode)
   - [Angular Language Service](https://marketplace.visualstudio.com/items?itemName=Angular.ng-template)

## Running in Debug Mode

### Development Mode

Start the application in development mode with hot-reload:

```bash
cd tauri-app
bun run tauri dev
```

This command:
1. Starts the Angular dev server on `http://localhost:4200`
2. Compiles the Rust backend with debug symbols
3. Launches the Tauri window
4. Enables hot-reload for both frontend and backend

### What Happens During `tauri dev`

1. **Frontend Build:**
   - Runs `bun run start` (defined in `tauri.conf.json` → `beforeDevCommand`)
   - Starts Angular dev server
   - Serves on `http://localhost:4200`

2. **Backend Build:**
   - Compiles Rust code in `src-tauri/`
   - Includes debug symbols
   - Links against Tauri runtime

3. **Application Launch:**
   - Opens Tauri window
   - Loads frontend from dev server
   - Establishes IPC bridge between frontend and backend

## Frontend Debugging (Angular)

### Opening DevTools

**Windows/Linux:**
- Press `Ctrl + Shift + I`
- Or press `F12`

**macOS:**
- Press `Cmd + Option + I`

### DevTools Panels

#### Console Tab
- View `console.log()` output
- See JavaScript errors and warnings
- Execute JavaScript commands
- Monitor Angular zone activity

Example logging:
```typescript
console.log('User input:', userInput);
console.error('Failed to connect:', error);
console.warn('API key not configured');
```

#### Network Tab
- Monitor HTTP requests
- View WebSocket connections
- Inspect request/response headers
- Check timing and performance

To filter WebSocket traffic:
1. Open Network tab
2. Click "WS" filter
3. Click on connection to see frames

#### Sources Tab
- Set breakpoints in TypeScript code
- Step through code execution
- Inspect variables
- View call stack

To debug TypeScript:
1. Open Sources tab
2. Navigate to `webpack://` → `.` → `src`
3. Find your TypeScript file
4. Click line number to set breakpoint

#### Application Tab
- View Local Storage
- Inspect Session Storage
- Check IndexedDB
- View cookies

#### Elements Tab
- Inspect DOM structure
- View computed styles
- Edit HTML/CSS live
- Debug Angular components

### Angular-Specific Debugging

**Enable Angular DevTools:**
1. Install [Angular DevTools](https://chrome.google.com/webstore/detail/angular-devtools/ienfalfjdbdpebioblfackkekamfmbnh) extension
2. Open DevTools
3. Look for "Angular" tab

**Component Inspection:**
- View component tree
- Inspect component properties
- Monitor change detection
- Profile performance

**Debug Mode:**
Angular runs in development mode by default, providing:
- Detailed error messages
- Change detection warnings
- Template binding errors

## Backend Debugging (Rust)

### Console Logging

Rust logs appear in the terminal where you ran `bun run tauri dev`.

**Basic Logging:**
```rust
println!("Debug: {}", variable);
eprintln!("Error: {}", error);
```

**Structured Logging:**

Add to `Cargo.toml`:
```toml
[dependencies]
log = "0.4"
env_logger = "0.11"
```

Use in code:
```rust
use log::{info, warn, error, debug};

fn main() {
    env_logger::init();
    
    info!("Application started");
    debug!("Processing command: {:?}", command);
    warn!("Connection unstable");
    error!("Failed to connect: {}", err);
}
```

Set log level:
```bash
# Windows PowerShell
$env:RUST_LOG="debug"
bun run tauri dev

# macOS/Linux
RUST_LOG=debug bun run tauri dev
```

### Debugging Tauri Commands

**Add Debug Output:**
```rust
#[tauri::command]
async fn my_command(param: String) -> Result<String, String> {
    println!("Command called with param: {}", param);
    
    // Your logic here
    let result = process_param(&param);
    
    println!("Command result: {:?}", result);
    Ok(result)
}
```

**Error Handling:**
```rust
#[tauri::command]
async fn connect_to_godot() -> Result<String, String> {
    match establish_connection().await {
        Ok(conn) => {
            println!("✓ Connected successfully");
            Ok("Connected".to_string())
        }
        Err(e) => {
            eprintln!("✗ Connection failed: {}", e);
            Err(format!("Connection error: {}", e))
        }
    }
}
```

### Using Rust Debugger

**With VS Code:**

1. Create `.vscode/launch.json`:
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
          "--manifest-path=./tauri-app/src-tauri/Cargo.toml",
          "--no-default-features"
        ]
      },
      "preLaunchTask": "ui:dev"
    }
  ]
}
```

2. Create `.vscode/tasks.json`:
```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "ui:dev",
      "type": "shell",
      "command": "bun",
      "args": ["run", "start"],
      "options": {
        "cwd": "${workspaceFolder}/tauri-app"
      },
      "isBackground": true
    }
  ]
}
```

3. Set breakpoints in Rust code
4. Press `F5` to start debugging
5. Use debug controls to step through code

**Breakpoint Features:**
- Step over (`F10`)
- Step into (`F11`)
- Step out (`Shift + F11`)
- Continue (`F5`)
- View variables
- Inspect call stack
- Evaluate expressions

## WebSocket Debugging

### Monitor WebSocket in DevTools

1. Open DevTools (`Ctrl+Shift+I` / `Cmd+Option+I`)
2. Go to Network tab
3. Filter by "WS" (WebSocket)
4. Click on the WebSocket connection
5. View "Messages" tab to see frames

### WebSocket Frame Inspection

**Sent Frames (Green):**
- Commands sent from Tauri to Godot
- JSON command structure
- Timestamps

**Received Frames (Red):**
- Responses from Godot
- Success/error messages
- Execution results

### Backend WebSocket Logging

Add logging to WebSocket code:

```rust
// In websocket.rs
println!("→ Sending to Godot: {}", message);
println!("← Received from Godot: {}", response);
```

### Common WebSocket Issues

**Connection Refused:**
- Verify Godot is running
- Check plugin is enabled
- Confirm port 9001 is open

**Connection Drops:**
- Check network stability
- Review timeout settings
- Monitor for errors in Godot Output tab

**Messages Not Received:**
- Verify JSON format
- Check message size limits
- Review protocol implementation

## IDE Integration

### VS Code Configuration

**Recommended Settings** (`.vscode/settings.json`):
```json
{
  "rust-analyzer.cargo.features": "all",
  "rust-analyzer.checkOnSave.command": "clippy",
  "editor.formatOnSave": true,
  "[rust]": {
    "editor.defaultFormatter": "rust-lang.rust-analyzer"
  },
  "[typescript]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  }
}
```

**Keyboard Shortcuts:**
- `F5` - Start debugging
- `Ctrl+Shift+B` - Run build task
- `Ctrl+`` - Toggle terminal
- `Ctrl+Shift+M` - View problems

### Debugging Tasks

Create `.vscode/tasks.json` for common tasks:
```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "tauri dev",
      "type": "shell",
      "command": "bun",
      "args": ["run", "tauri", "dev"],
      "options": {
        "cwd": "${workspaceFolder}/tauri-app"
      },
      "problemMatcher": []
    },
    {
      "label": "cargo check",
      "type": "shell",
      "command": "cargo",
      "args": ["check"],
      "options": {
        "cwd": "${workspaceFolder}/tauri-app/src-tauri"
      },
      "problemMatcher": ["$rustc"]
    }
  ]
}
```

## Production Build Debugging

### Debug Build

Create a debug build with symbols:

```bash
cd tauri-app
bun run tauri build --debug
```

**Output Location:**
- Windows: `src-tauri/target/debug/bundle/nsis/`
- macOS: `src-tauri/target/debug/bundle/macos/`
- Linux: `src-tauri/target/debug/bundle/appimage/`

**Characteristics:**
- Includes debug symbols
- No optimizations
- Larger binary size
- Slower execution
- Better for debugging

### Release Build

Create an optimized production build:

```bash
cd tauri-app
bun run tauri build
```

**Output Location:**
- Windows: `src-tauri/target/release/bundle/nsis/`
- macOS: `src-tauri/target/release/bundle/macos/`
- Linux: `src-tauri/target/release/bundle/appimage/`

**Characteristics:**
- Optimized code
- Smaller binary size
- Faster execution
- Harder to debug

### Enabling Logs in Production

**Windows (PowerShell):**
```powershell
$env:RUST_LOG="info"
.\tauri-app.exe
```

**macOS/Linux:**
```bash
RUST_LOG=info ./tauri-app
```

**Log Levels:**
- `error` - Only errors
- `warn` - Warnings and errors
- `info` - Informational messages
- `debug` - Detailed debugging
- `trace` - Very verbose

### Log File Locations

**Windows:**
```
%APPDATA%\com.godoty.app\logs\
```

**macOS:**
```
~/Library/Logs/com.godoty.app/
```

**Linux:**
```
~/.local/share/com.godoty.app/logs/
```

## Common Issues and Solutions

### Application Won't Start

**Symptom:** Application fails to launch or crashes immediately

**Solutions:**

1. **Check Rust compilation:**
   ```bash
   cd tauri-app/src-tauri
   cargo check
   ```

2. **Verify Angular dev server:**
   ```bash
   cd tauri-app
   bun run start
   # Should start on http://localhost:4200
   ```

3. **Check for port conflicts:**
   ```bash
   # Windows
   netstat -ano | findstr :4200

   # macOS/Linux
   lsof -i :4200
   ```

4. **Review configuration:**
   - Check `tauri.conf.json` for correct paths
   - Verify `beforeDevCommand` and `devUrl` settings

5. **Clear build cache:**
   ```bash
   cd tauri-app/src-tauri
   cargo clean
   cd ..
   rm -rf dist node_modules
   bun install
   ```

### Frontend Not Loading

**Symptom:** Tauri window opens but shows blank screen or loading error

**Solutions:**

1. **Check DevTools console:**
   - Press `Ctrl+Shift+I` / `Cmd+Option+I`
   - Look for JavaScript errors

2. **Verify dev server is running:**
   - Should see "Angular Live Development Server is listening on localhost:4200"
   - Try accessing `http://localhost:4200` in a browser

3. **Check `tauri.conf.json`:**
   ```json
   {
     "build": {
       "beforeDevCommand": "bun run start",
       "devUrl": "http://localhost:4200"
     }
   }
   ```

4. **Rebuild frontend:**
   ```bash
   cd tauri-app
   rm -rf dist
   bun run build
   ```

### Backend Commands Failing

**Symptom:** Frontend calls to Rust commands fail or timeout

**Solutions:**

1. **Verify command registration:**
   ```rust
   // In src-tauri/src/lib.rs
   .invoke_handler(tauri::generate_handler![
       my_command,  // Make sure your command is listed here
   ])
   ```

2. **Check command signature:**
   ```rust
   #[tauri::command]
   async fn my_command(param: String) -> Result<String, String> {
       // Implementation
   }
   ```

3. **Verify frontend call:**
   ```typescript
   import { invoke } from '@tauri-apps/api/core';

   // Command name must match exactly
   const result = await invoke<string>('my_command', { param: 'value' });
   ```

4. **Add debug logging:**
   ```rust
   #[tauri::command]
   async fn my_command(param: String) -> Result<String, String> {
       println!("Command called with: {}", param);
       // ...
   }
   ```

5. **Check error messages:**
   - Look in terminal for Rust errors
   - Check DevTools console for frontend errors

### WebSocket Connection Issues

**Symptom:** Cannot connect to Godot or connection drops

**Solutions:**

1. **Verify Godot is running:**
   - Plugin should be enabled
   - Check Godoty dock panel shows "Server started on port 9001"

2. **Check firewall:**
   - Allow connections on port 9001
   - Temporarily disable firewall to test

3. **Test port availability:**
   ```bash
   # Windows
   netstat -ano | findstr :9001

   # macOS/Linux
   lsof -i :9001
   ```

4. **Review WebSocket code:**
   - Check connection URL: `ws://localhost:9001`
   - Verify error handling
   - Add connection retry logic

5. **Monitor in DevTools:**
   - Network tab → WS filter
   - Check connection status
   - View error messages

### Build Failures

**Symptom:** `bun run tauri build` fails

**Solutions:**

1. **Update dependencies:**
   ```bash
   cd tauri-app
   bun install
   cd src-tauri
   cargo update
   ```

2. **Check Rust version:**
   ```bash
   rustc --version
   # Should be 1.70 or higher
   ```

3. **Install system dependencies:**

   **Windows:**
   - Install [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
   - Install [WebView2](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)

   **macOS:**
   ```bash
   xcode-select --install
   ```

   **Linux (Ubuntu/Debian):**
   ```bash
   sudo apt update
   sudo apt install libwebkit2gtk-4.1-dev \
     build-essential \
     curl \
     wget \
     file \
     libssl-dev \
     libayatana-appindicator3-dev \
     librsvg2-dev
   ```

4. **Clean and rebuild:**
   ```bash
   cd tauri-app/src-tauri
   cargo clean
   cd ..
   bun run tauri build
   ```

5. **Check disk space:**
   - Rust builds require significant disk space
   - Ensure at least 5GB free

### Hot Reload Not Working

**Symptom:** Changes don't appear without manual restart

**Solutions:**

1. **Frontend hot reload:**
   - Angular dev server should auto-reload
   - Check terminal for compilation errors
   - Try manual refresh: `Ctrl+R` / `Cmd+R`

2. **Backend hot reload:**
   - Rust changes require restart
   - Stop (`Ctrl+C`) and restart `bun run tauri dev`
   - Consider using `cargo-watch` for auto-restart

3. **Clear cache:**
   ```bash
   # Clear Angular cache
   rm -rf .angular

   # Clear Rust cache
   cd src-tauri
   cargo clean
   ```

## Performance Profiling

### Frontend Performance

**Chrome DevTools Performance Tab:**

1. Open DevTools → Performance tab
2. Click Record (●)
3. Interact with the application
4. Click Stop
5. Analyze the flame graph

**Key Metrics:**
- FPS (Frames Per Second)
- CPU usage
- Memory allocation
- Long tasks

**Angular-Specific Profiling:**

1. Install Angular DevTools extension
2. Open Angular tab → Profiler
3. Click Record
4. Perform actions
5. Stop and analyze change detection cycles

**Memory Profiling:**

1. DevTools → Memory tab
2. Take heap snapshot
3. Perform actions
4. Take another snapshot
5. Compare to find memory leaks

### Backend Performance

**Cargo Flamegraph:**

Install:
```bash
cargo install flamegraph
```

Profile:
```bash
cd tauri-app/src-tauri
cargo flamegraph
```

This generates an interactive SVG showing CPU time per function.

**Timing Logs:**

Add timing to critical sections:
```rust
use std::time::Instant;

let start = Instant::now();
// Your code here
let duration = start.elapsed();
println!("Operation took: {:?}", duration);
```

**Benchmarking:**

Create benchmarks in `src-tauri/benches/`:
```rust
use criterion::{black_box, criterion_group, criterion_main, Criterion};

fn benchmark_function(c: &mut Criterion) {
    c.bench_function("my_function", |b| {
        b.iter(|| my_function(black_box(42)))
    });
}

criterion_group!(benches, benchmark_function);
criterion_main!(benches);
```

Run:
```bash
cargo bench
```

## Useful Commands Reference

### Development

```bash
# Start development mode
cd tauri-app
bun run tauri dev

# Start only frontend
bun run start

# Build frontend
bun run build

# Run frontend tests
bun run test
```

### Rust/Cargo

```bash
cd tauri-app/src-tauri

# Check for errors without building
cargo check

# Build in debug mode
cargo build

# Build in release mode
cargo build --release

# Run tests
cargo test

# Format code
cargo fmt

# Lint code
cargo clippy

# Update dependencies
cargo update

# Clean build artifacts
cargo clean

# View dependency tree
cargo tree
```

### Tauri

```bash
cd tauri-app

# Development mode
bun run tauri dev

# Build debug
bun run tauri build --debug

# Build release
bun run tauri build

# Show Tauri info
bun run tauri info

# Generate icons
bun run tauri icon path/to/icon.png
```

### Debugging

```bash
# Enable Rust logging
RUST_LOG=debug bun run tauri dev

# Enable verbose Rust logging
RUST_LOG=trace bun run tauri dev

# Check Rust version
rustc --version

# Check Cargo version
cargo --version

# Check Tauri CLI version
bun run tauri --version

# Check system info
bun run tauri info
```

## Additional Resources

### Documentation

- [Tauri Documentation](https://tauri.app/v1/guides/)
- [Tauri API Reference](https://tauri.app/v1/api/js/)
- [Angular Documentation](https://angular.dev/)
- [Rust Book](https://doc.rust-lang.org/book/)
- [Cargo Book](https://doc.rust-lang.org/cargo/)

### Debugging Tools

- [Chrome DevTools](https://developer.chrome.com/docs/devtools/)
- [rust-analyzer](https://rust-analyzer.github.io/)
- [CodeLLDB](https://github.com/vadimcn/vscode-lldb)
- [Angular DevTools](https://angular.io/guide/devtools)

### Community

- [Tauri Discord](https://discord.com/invite/tauri)
- [Tauri GitHub Discussions](https://github.com/tauri-apps/tauri/discussions)
- [Rust Users Forum](https://users.rust-lang.org/)
- [Angular Community](https://angular.io/resources)

## Tips and Best Practices

1. **Always check both frontend and backend logs** when debugging issues
2. **Use TypeScript strict mode** to catch errors early
3. **Enable Rust clippy** for better code quality
4. **Test in production builds** before releasing
5. **Monitor WebSocket connections** in DevTools
6. **Keep dependencies updated** but test thoroughly
7. **Use structured logging** instead of println!
8. **Profile before optimizing** to find real bottlenecks
9. **Write tests** for critical functionality
10. **Document debugging steps** for recurring issues

---

For more information, see:
- [DEVELOPMENT.md](DEVELOPMENT.md) - General development guide
- [SETUP_GUIDE.md](SETUP_GUIDE.md) - Initial setup instructions
- [README.md](README.md) - Project overview


