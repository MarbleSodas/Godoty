#!/usr/bin/env python3
"""
Build script to bundle RAG server with PyInstaller.
This script should be run before building the Tauri application.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def check_pyinstaller():
    """Check if PyInstaller is installed."""
    try:
        import PyInstaller
        return True
    except ImportError:
        return False

def install_dependencies():
    """Install all required dependencies including PyInstaller."""
    print("Installing Python dependencies...")
    requirements_file = Path(__file__).parent / "rag_requirements.txt"
    
    # Install requirements
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-r", str(requirements_file)
    ])
    
    # Install PyInstaller
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "pyinstaller"
    ])
    
    print("Dependencies installed successfully.")

def build_executable():
    """Build the RAG server executable using PyInstaller."""
    print("Building RAG server executable...")
    
    script_dir = Path(__file__).parent
    spec_file = script_dir / "rag_server.spec"
    
    # Run PyInstaller
    subprocess.check_call([
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        str(spec_file)
    ])
    
    print("Executable built successfully.")

def copy_to_resources():
    """Copy the built executable to the resources directory."""
    print("Copying executable to resources...")

    script_dir = Path(__file__).parent
    dist_dir = script_dir / "dist"
    resources_dir = script_dir / "resources"

    # Create resources directory if it doesn't exist
    resources_dir.mkdir(exist_ok=True)

    # Determine executable name based on platform
    if sys.platform == "win32":
        exe_name = "rag_server.exe"
    else:
        exe_name = "rag_server"

    src_exe = dist_dir / exe_name
    dst_exe = resources_dir / exe_name

    if src_exe.exists():
        shutil.copy2(src_exe, dst_exe)
        print(f"Copied {exe_name} to resources directory.")

        # Make executable on Unix-like systems
        if sys.platform != "win32":
            os.chmod(dst_exe, 0o755)
    else:
        print(f"Error: Executable not found at {src_exe}")
        sys.exit(1)

def cleanup():
    """Clean up build artifacts."""
    print("Cleaning up build artifacts...")
    
    script_dir = Path(__file__).parent
    
    # Remove build and dist directories
    for dir_name in ["build", "dist"]:
        dir_path = script_dir / dir_name
        if dir_path.exists():
            shutil.rmtree(dir_path)
    
    print("Cleanup complete.")

def main():
    """Main build process."""
    print("=" * 60)
    print("RAG Server Bundle Builder")
    print("=" * 60)
    
    # Check if PyInstaller is installed
    if not check_pyinstaller():
        print("PyInstaller not found. Installing dependencies...")
        install_dependencies()
    
    # Build the executable
    build_executable()

    # Copy to resources directory
    copy_to_resources()

    # Cleanup
    cleanup()
    
    print("=" * 60)
    print("Build complete! The RAG server executable is ready.")
    print("=" * 60)

if __name__ == "__main__":
    main()

