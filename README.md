# Godoty

Godoty is a powerful, AI-integrated desktop application designed to bridge the gap between AI assistants and the Godot Engine. Built with Tauri and SolidJS, it leverages the Model Context Protocol (MCP) to provide a seamless automation and documentation layer for Godot 4.x.

## 🚀 Overview

Godoty enables AI models to interact directly with the Godot Engine, allowing for:
- **Headless Project Manipulation**: Create scenes, add nodes, and configure properties without opening the editor.
- **Real-time Debugging**: Capture viewport screenshots and debug output from running projects.
- **Deep Documentation Search**: Indexed access to the entire Godot 4.x Class Reference.
- **Desktop Integration**: A modern UI for managing your AI-powered game development workflow.

## ✨ Key Features

- **MCP Integration**: Two specialized MCP servers:
  - `godot`: Tools for launching the editor, running projects, and manipulating `.tscn` files.
  - `godot-doc`: High-performance search for Godot classes, methods, and signals.
- **Headless Operations**: Automate repetitive tasks via GDScript-based sidecar operations.
- **Viewport Capture**: Instant screenshots of running game instances for visual AI analysis.
- **Modern Tech Stack**: Built with Tauri 2.0, SolidJS, Tailwind CSS, and Rust.

## 🛠 Tech Stack

- **Backend**: Rust (Tauri 2.0)
- **Frontend**: SolidJS, TypeScript, Tailwind CSS
- **AI Protocol**: Model Context Protocol (MCP)
- **Scripting**: Bun (monorepo management), Node.js (MCP servers)
- **Engine Support**: Godot 4.x

## ⚙️ Prerequisites

- **Godot Engine 4.x**: Ensure Godot 4.6 (or newer) is installed.
- **Bun**: For dependency management and running scripts.
- **Rust**: For building the Tauri backend.
- **Environment Variables**:
  - `GODOT_PATH`: Path to your Godot executable.
  - `GODOT_DOC_DIR`: Path to the Godot source XML documentation (for indexing).

## 📦 Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-repo/godoty.git
   cd godoty
   ```

2. **Install dependencies**:
   ```bash
   bun install
   ```

3. **Setup environment**:
   Create a `.env` file or export the required variables:
   ```bash
   export GODOT_PATH="/Applications/Godot.app/Contents/MacOS/Godot"
   ```

## 🖥 Development

Run the development environment (Frontend + Tauri):

```bash
bun dev:all
```

To run the Tauri app in isolation:

```bash
bun dev:isolated
```

## 🏗 Building

Build the production desktop application:

```bash
bun build:tauri
```

## 🧩 MCP Tools

Godoty exposes several tools to AI assistants:
- `launch_editor`: Open the Godot editor for a specific project.
- `run_project`: Launch a project with debug output capture.
- `create_scene`: Generate a new `.tscn` file from scratch.
- `capture_viewport`: Take a screenshot of the active game window.
- `godot_search`: Search class references.

## 📄 License

This project is licensed under the MIT License.
