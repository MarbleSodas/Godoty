#!/usr/bin/env python3
"""
Quick test script to verify Godot plugin connection functionality.
"""

import asyncio
import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from agents.tools.godot_bridge import get_godot_bridge

async def test_godot_connection():
    """Test basic Godot plugin connection."""
    print("Testing Godot plugin connection...")

    try:
        # Get the bridge instance
        bridge = get_godot_bridge()
        print(f"✅ Bridge instance created successfully")
        print(f"   Target: {bridge.host}:{bridge.port}")

        # Test connection
        print("🔌 Testing WebSocket connection...")
        is_connected = await bridge.connect()

        if is_connected:
            print("✅ Successfully connected to Godot plugin!")

            # Test getting project info
            print("📋 Requesting project info...")
            project_info = await bridge.get_project_info()

            if project_info:
                print(f"✅ Project info retrieved:")
                print(f"   Project Path: {project_info.project_path}")
                print(f"   Project Name: {project_info.project_name}")
                print(f"   Godot Version: {project_info.godot_version}")
                print(f"   Plugin Version: {project_info.plugin_version}")
                print(f"   Is Ready: {project_info.is_ready}")
            else:
                print("⚠️  Could not retrieve project info")

            # Test a simple command
            print("📤 Testing simple command...")
            response = await bridge.send_command("ping")

            if response.success:
                print("✅ Command executed successfully!")
                print(f"   Response: {response.data}")
            else:
                print(f"❌ Command failed: {response.error}")

            # Clean disconnect
            await bridge.disconnect()
            print("🔌 Disconnected gracefully")

        else:
            print("❌ Failed to connect to Godot plugin")
            print(f"   Make sure Godot is running with the Godoty plugin enabled")
            return False

    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("🎉 Godot plugin connection test completed successfully!")
    return True

if __name__ == "__main__":
    print("Godoty Plugin Connection Test")
    print("=" * 40)

    result = asyncio.run(test_godot_connection())

    if result:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Tests failed!")
        sys.exit(1)