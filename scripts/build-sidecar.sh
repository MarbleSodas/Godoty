#!/bin/bash
# Build script for Godoty Brain Python sidecar
# This creates a standalone executable using PyInstaller

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BRAIN_DIR="$PROJECT_ROOT/brain"
DESKTOP_DIR="$PROJECT_ROOT/desktop"
OUTPUT_DIR="$DESKTOP_DIR/src-tauri/binaries"

echo "🧠 Building Godoty Brain sidecar..."

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

# Navigate to brain directory
cd "$BRAIN_DIR"

# Activate virtual environment
if [ -d ".venv" ]; then
    echo "🐍 Activating virtual environment..."
    source .venv/bin/activate
else
    echo "❌ No .venv found. Please create a venv first:"
    echo "   cd brain && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Verify we're using the correct Python
echo "🐍 Using Python: $(which python3) ($(python3 --version))"

# Determine target triple based on OS
get_target_triple() {
    local OS=$(uname -s)
    local ARCH=$(uname -m)
    
    case "$OS" in
        Darwin)
            case "$ARCH" in
                x86_64) echo "x86_64-apple-darwin" ;;
                arm64) echo "aarch64-apple-darwin" ;;
                *) echo "unknown-apple-darwin" ;;
            esac
            ;;
        Linux)
            case "$ARCH" in
                x86_64) echo "x86_64-unknown-linux-gnu" ;;
                aarch64) echo "aarch64-unknown-linux-gnu" ;;
                *) echo "unknown-unknown-linux-gnu" ;;
            esac
            ;;
        MINGW*|MSYS*|CYGWIN*)
            echo "x86_64-pc-windows-msvc"
            ;;
        *)
            echo "unknown-unknown-unknown"
            ;;
    esac
}

TARGET_TRIPLE=$(get_target_triple)
echo "📦 Target: $TARGET_TRIPLE"

# Check if PyInstaller is installed in the venv
if ! command -v pyinstaller &> /dev/null; then
    echo "📥 Installing PyInstaller in venv..."
    pip install pyinstaller
fi

# Build with PyInstaller
echo "🔨 Building with PyInstaller..."
pyinstaller \
    --onefile \
    --name "godoty-brain-$TARGET_TRIPLE" \
    --add-data "app:app" \
    --hidden-import=app \
    --hidden-import=app.main \
    --hidden-import=app.agents \
    --hidden-import=app.protocol \
    --hidden-import=app.tools \
    --hidden-import=uvicorn.logging \
    --hidden-import=uvicorn.protocols.http \
    --hidden-import=uvicorn.protocols.websockets \
    --hidden-import=uvicorn.protocols.http.auto \
    --hidden-import=uvicorn.protocols.websockets.auto \
    --hidden-import=uvicorn.lifespan.on \
    --hidden-import=uvicorn.lifespan.off \
    --hidden-import=agno \
    --hidden-import=litellm \
    --hidden-import=tiktoken \
    --hidden-import=tiktoken_ext \
    --hidden-import=tiktoken_ext.openai_public \
    --collect-all agno \
    --collect-all litellm \
    --collect-all tiktoken \
    --collect-data tiktoken_ext.openai_public \
    --clean \
    --noconfirm \
    run_brain.py

# Move to Tauri binaries directory
echo "📁 Moving binary to Tauri binaries directory..."
mv "dist/godoty-brain-$TARGET_TRIPLE" "$OUTPUT_DIR/"

# Make executable
chmod +x "$OUTPUT_DIR/godoty-brain-$TARGET_TRIPLE"

# Clean up
rm -rf build dist *.spec

echo "✅ Build complete: $OUTPUT_DIR/godoty-brain-$TARGET_TRIPLE"
