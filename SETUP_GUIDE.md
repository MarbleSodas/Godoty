# Godoty Setup Guide

This guide will help you set up and run the Godoty AI-powered Godot development assistant.

## Prerequisites

Before you begin, make sure you have the following installed:

1. **Godot 4.x** - Download from [godotengine.org](https://godotengine.org/)
2. **Rust** - Install from [rustup.rs](https://rustup.rs/)
3. **Bun** - Install from [bun.sh](https://bun.sh/)
4. **OpenAI API Key** - Get one from [platform.openai.com](https://platform.openai.com/)

## Installation Steps

### 1. Install the Godot Plugin

1. Open your Godot project (or create a new one)
2. Copy the `godot-plugin/addons/godoty` folder to your project's `addons/` directory
3. In Godot, go to **Project → Project Settings → Plugins**
4. Enable the "Godoty AI Assistant" plugin
5. You should see a new dock panel on the right side labeled "Godoty AI Assistant"
6. The plugin will automatically start a WebSocket server on port 9001

### 2. Set Up the Tauri Application

1. Navigate to the `tauri-app` directory:
   ```bash
   cd tauri-app
   ```

2. Install dependencies:
   ```bash
   bun install
   ```

3. Build the Rust backend (first time only):
   ```bash
   bun tauri build --debug
   ```

### 3. Configure Your API Key

1. Start the Tauri app:
   ```bash
   bun tauri dev
   ```

2. In the app's Settings panel (right side), click "Edit" next to "OpenAI API Key"
3. Enter your OpenAI API key (starts with `sk-...`)
4. Click "Save"

## Running the Application

### Start Godot

1. Open your Godot project with the Godoty plugin enabled
2. Make sure you have a scene open in the editor
3. Check the Godoty dock panel - it should show "Server started on port 9001"

### Start the Tauri App

1. In a terminal, navigate to the `tauri-app` directory
2. Run:
   ```bash
   bun tauri dev
   ```

3. The app should open and automatically connect to Godot
4. The status indicator should show "🟢 Connected to Godot"

## Using Godoty

### Example Commands

Once connected, you can type natural language commands in the input box:

1. **Create a 2D Player Character:**
   ```
   Add a 2D player character with a sprite and collision shape
   ```

2. **Create a UI Button:**
   ```
   Create a button labeled "Start Game" in the center of the screen
   ```

3. **Add a Camera:**
   ```
   Add a 2D camera that follows the player
   ```

4. **Create a Complete Scene:**
   ```
   Create a platformer level with a player, ground platform, and a coin to collect
   ```

### How It Works

1. You type a command in natural language
2. The AI processes your request and generates Godot commands
3. Commands are sent via WebSocket to the Godot plugin
4. The plugin executes the commands using the EditorPlugin API
5. You see the results immediately in your Godot scene

### Command History

- All commands are logged in the "Command History" panel
- ✅ Green border = Success
- ❌ Red border = Error
- ⏳ Yellow border = Processing

## Troubleshooting

### "Disconnected" Status

**Problem:** The Tauri app shows "🔴 Disconnected"

**Solutions:**
1. Make sure Godot is running with the plugin enabled
2. Check that the Godoty dock panel shows "Server started on port 9001"
3. Click "Reconnect to Godot" in the Settings panel
4. Restart both Godot and the Tauri app

### "API key not configured" Error

**Problem:** Commands fail with API key error

**Solutions:**
1. Go to Settings panel
2. Click "Edit" next to "OpenAI API Key"
3. Enter your valid API key
4. Click "Save"

### Commands Not Executing

**Problem:** Commands are sent but nothing happens in Godot

**Solutions:**
1. Make sure you have a scene open in Godot
2. Check the Godoty dock panel in Godot for error messages
3. Look at the Godot console (Output tab) for detailed logs
4. Try simpler commands first (e.g., "Create a Node2D named Test")

### WebSocket Connection Fails

**Problem:** Cannot connect to Godot

**Solutions:**
1. Check if port 9001 is already in use by another application
2. Disable firewall temporarily to test
3. Make sure you're running Godot and Tauri on the same machine
4. Check Godot's Output tab for WebSocket server errors

## Advanced Usage

### Custom Node Properties

You can specify properties in your commands:

```
Create a Sprite2D with position (100, 200) and scale (2, 2)
```

### Attaching Scripts

```
Add a CharacterBody2D with a movement script that uses WASD controls
```

### Creating Complete Scenes

```
Create a new scene called "MainMenu" with a background, title label, and start button
```

## Development

### Modifying the AI Prompts

Edit `tauri-app/src-tauri/src/ai.rs` to customize the system prompt and improve AI responses.

### Adding New Commands

1. Add command definition to `protocol/commands.json`
2. Implement handler in `godot-plugin/addons/godoty/command_executor.gd`
3. Update AI system prompt in `tauri-app/src-tauri/src/ai.rs`

### Debugging

**Godot Plugin:**
- Check the Output tab in Godot for logs
- Look for messages starting with "Godoty:"

**Tauri App:**
- Open DevTools in the Tauri window (Ctrl+Shift+I / Cmd+Option+I)
- Check the console for JavaScript errors
- Rust logs appear in the terminal where you ran `bun tauri dev`

## Next Steps

- Experiment with different commands
- Try creating complex game objects
- Provide feedback to improve the AI prompts
- Extend the command protocol with new actions

## Support

For issues and questions:
- Check the troubleshooting section above
- Review the logs in both Godot and Tauri
- Open an issue on the project repository

Happy game development with Godoty! 🎮✨

