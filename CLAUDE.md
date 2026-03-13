# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is **Godoty** - a fork of Godot Engine 4.6.1 with AI/LLM integration capabilities. It is a cross-platform 2D/3D game engine written in C++ with a modular architecture.

## Build System

The project uses **SCons** as its build system (Python-based).

### Common Build Commands

```bash
# Build editor (default)
scons -j$(nproc)

# Build for specific platform
scons platform=macos -j$(nproc)
scons platform=linuxbsd -j$(nproc)
scons platform=windows -j$(nproc)

# Build with specific target
scons target=editor          # Default - includes editor
scons target=template_release  # Export templates
scons target=template_debug    # Debug export templates

# Build with specific modules disabled
scons module_text_server_fb_enabled=no

# Clean build
scons -c
```

### Development Setup

1. Install Python 3.8+ and SCons
2. For macOS: Install Xcode Command Line Tools
3. For Linux: Install development headers (see platform/*/detect.py for requirements)

## Code Architecture

The engine follows a layered architecture:

- **core/** - Base classes, math, data structures, threading, file I/O
- **scene/** - Scene tree system, nodes, resources, animations
- **servers/** - Rendering, physics, audio, navigation (backend systems)
- **editor/** - Editor UI, import system, build pipelines
- **drivers/** - Rendering drivers (OpenGL, Vulkan, etc.)
- **platform/** - Platform-specific code (macOS, Linux, Windows, Android, iOS, Web)
- **modules/** - Optional modules (GDScript, C#, GodotY AI agent, etc.)
- **main/** - Entry point, main loop
- **tests/** - Unit tests

### Custom AI Agent Module

This fork includes a custom `ai_agent` module (`modules/ai_agent/`) that provides:
- LLM integration (MiniMax as default provider)
- AI agent sessions with tool/function calling
- Context collection system
- Editor UI integration

Key classes in `modules/ai_agent/`:
- `AIAgentSession` - Manages AI chat sessions
- `AIToolRegistry` - Registers AI-callable tools (36+ tools available)
- `AIConversation` - Handles message history and context

## Code Style

The project follows specific style guidelines enforced by pre-commit:

- **C++**: Clang-format (see `.clang-format`)
- **Python**: ruff-format + mypy type checking
- **GLSL**: Custom clang-format style

### Running Code Formatting

```bash
# Format C++ code
clang-format -i <file>

# Format Python code
ruff format <file>
ruff check --fix <file>

# Run all pre-commit hooks
pre-commit run --all-files
```

## Testing

Unit tests are located in `tests/` directory.

```bash
# Build and run tests (after building the editor)
./bin/godot --test --headless
```

## Key Files

- `SConstruct` - Main build configuration
- `platform/*/detect.py` - Platform detection and build options
- `core/core_bind.h/cpp` - Core API bindings
- `scene/main/scene_main_loop.cpp` - Scene system initialization
- `editor/editor_node.cpp` - Main editor class

## Git Workflow

- Branch: `godot-fork` (main development branch)
- Commits should follow conventional format (e.g., "Add feature", "Fix bug")
- Use `git pull --rebase` to avoid merge commits
- Reference issues in PRs using GitHub keywords (Fixes #1234)
