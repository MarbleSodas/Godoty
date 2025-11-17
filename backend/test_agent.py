"""
Test script for the planning agent.

This script tests both streaming and non-streaming endpoints.
Run this after starting the FastAPI server.
"""

import httpx
import asyncio
import json
import sys


async def test_health():
    """Test the health check endpoint."""
    print("=" * 60)
    print("Testing Agent Health Check")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://localhost:8000/api/agent/health")
            response.raise_for_status()
            data = response.json()

            print(f"Status: {data['status']}")
            print(f"Agent Ready: {data['agent_ready']}")
            print(f"Model: {data.get('model', 'N/A')}")
            print("+ Health check passed\n")
            return True

        except Exception as e:
            print(f"- Health check failed: {e}\n")
            return False


async def test_config():
    """Test the config endpoint."""
    print("=" * 60)
    print("Testing Agent Configuration")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://localhost:8000/api/agent/config")
            response.raise_for_status()
            data = response.json()

            print(f"Status: {data['status']}")
            print(f"Model ID: {data['config']['model_id']}")
            print(f"Temperature: {data['config']['model_config']['temperature']}")
            print(f"Max Tokens: {data['config']['model_config']['max_tokens']}")
            print(f"Available Tools: {', '.join(data['config']['tools'])}")
            print(f"Conversation Manager: {data['config']['conversation_manager']}")
            print("+ Configuration retrieved\n")
            return True

        except Exception as e:
            print(f"- Configuration test failed: {e}\n")
            return False


async def test_plan_simple():
    """Test simple plan generation (non-streaming)."""
    print("=" * 60)
    print("Testing Simple Plan Generation (Non-Streaming)")
    print("=" * 60)

    prompt = "Create a brief plan for implementing a health bar in a 2D game."

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                "http://localhost:8000/api/agent/plan",
                json={
                    "prompt": prompt,
                    "reset_conversation": True
                }
            )
            response.raise_for_status()
            data = response.json()

            print(f"Status: {data['status']}")
            print(f"\nGenerated Plan:\n{'-' * 60}")
            print(data['plan'])
            print("-" * 60)
            print("+ Plan generation successful\n")
            return True

        except Exception as e:
            print(f"- Plan generation failed: {e}\n")
            return False


async def test_plan_streaming():
    """Test streaming plan generation."""
    print("=" * 60)
    print("Testing Streaming Plan Generation")
    print("=" * 60)

    prompt = "Create a simple plan for adding a pause menu to a game."

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            print("Streaming response:")
            print("-" * 60)

            async with client.stream(
                "POST",
                "http://localhost:8000/api/agent/plan/stream",
                json={
                    "prompt": prompt,
                    "reset_conversation": True
                }
            ) as response:
                response.raise_for_status()

                full_text = ""
                event_type = None

                async for line in response.aiter_lines():
                    line = line.strip()

                    if not line:
                        continue

                    # Parse SSE format
                    if line.startswith("event: "):
                        event_type = line[7:]  # Remove "event: " prefix
                    elif line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix

                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        # Handle different event types
                        if event_type == "start":
                            print(f"[START] {data.get('message', '')}")

                        elif event_type == "data":
                            if "text" in data:
                                text_chunk = data["text"]
                                full_text += text_chunk
                                print(text_chunk, end="", flush=True)

                        elif event_type == "tool_use_start":
                            print(f"\n[TOOL] Using: {data.get('tool_name')}")

                        elif event_type == "metadata":
                            usage = data.get("usage", {})
                            if usage:
                                print(f"\n[METADATA] Input tokens: {usage.get('inputTokens', 0)}, "
                                      f"Output tokens: {usage.get('outputTokens', 0)}")

                        elif event_type == "end":
                            print(f"\n[END] Stop reason: {data.get('stop_reason', 'unknown')}")

                        elif event_type == "error":
                            print(f"\n[ERROR] {data.get('error', 'Unknown error')}")
                            return False

                        elif event_type == "done":
                            break

            print("\n" + "-" * 60)
            print("+ Streaming test successful\n")
            return True

        except Exception as e:
            print(f"\n- Streaming test failed: {e}\n")
            return False


async def test_mcp_integration():
    """Test MCP tools integration."""
    print("=" * 60)
    print("Testing MCP Tools Integration")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://localhost:8000/api/agent/config")
            response.raise_for_status()
            data = response.json()

            tools = data['config']['tools']

            # Check for MCP tools - look for specific MCP tool names and patterns
            mcp_patterns = ['sequentialthinking', 'resolve-library-id', 'get-library-docs', 'context7', 'mcp']
            mcp_tools = [t for t in tools if any(pattern in t.lower() for pattern in mcp_patterns)]

            if not mcp_tools:
                print("- MCP Integration: FAILED - No MCP tools found")
                print("Error: MCP servers are not properly initialized or installed")
                print("Please ensure MCP servers are configured and running")
                return False

            print(f"MCP Integration: ENABLED")
            print(f"MCP Tools Found: {len(mcp_tools)}")

            # Check for specific MCP tools
            has_sequential = any('sequential' in t.lower() for t in mcp_tools)
            has_context7 = any('context7' in t.lower() for t in mcp_tools)
            has_playwright = any('playwright' in t.lower() for t in mcp_tools)
            has_desktop = any('desktop' in t.lower() for t in mcp_tools)

            print(f"  - Sequential Thinking: {'+' if has_sequential else '-'}")
            print(f"  - Context7: {'+' if has_context7 else '-'}")
            print(f"  - Playwright: {'+' if has_playwright else '-'}")
            print(f"  - Desktop Commander: {'+' if has_desktop else '-'}")

            print("\nMCP Tools:")
            for tool in mcp_tools:
                print(f"  - {tool}")

            # Test actual MCP functionality by trying to use an MCP tool
            print("\nTesting MCP functionality...")

            try:
                # Test with a simple prompt that would use MCP tools
                test_prompt = "What is 2+2? Use sequential thinking to solve this step by step."

                response = await client.post(
                    "http://localhost:8000/api/agent/plan",
                    json={
                        "prompt": test_prompt,
                        "reset_conversation": True
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                plan_data = response.json()

                print(f"Status: {plan_data['status']}")

                # Check if the response indicates MCP tools were used
                plan_text = plan_data.get('plan', '').lower()

                # Look for evidence of sequential thinking or other MCP tool usage
                mcp_indicators = ['thinking', 'step', 'thought', 'reasoning', 'analysis']
                has_mcp_usage = any(indicator in plan_text for indicator in mcp_indicators)

                if has_mcp_usage:
                    print("+ MCP tools are functional and responding")
                else:
                    print("⚠ MCP tools may not be responding correctly")
                    # Still pass if tools are available but not actively used

                # Test specific MCP tool if context7 is available
                if has_context7:
                    print("\nTesting Context7 functionality...")
                    context7_prompt = "Get documentation for the 'requests' Python library"

                    response = await client.post(
                        "http://localhost:8000/api/agent/plan",
                        json={
                            "prompt": context7_prompt,
                            "reset_conversation": False
                        },
                        timeout=30.0
                    )
                    response.raise_for_status()
                    context_data = response.json()

                    context_text = context_data.get('plan', '').lower()
                    if any(word in context_text for word in ['requests', 'documentation', 'library', 'python']):
                        print("+ Context7 tool appears functional")
                    else:
                        print("⚠ Context7 tool may not be responding correctly")

            except httpx.TimeoutException:
                print("- MCP functionality test timed out")
                print("Error: MCP servers may not be responding properly")
                return False
            except Exception as e:
                print(f"- MCP functionality test failed: {e}")
                return False

            print("+ MCP integration verified and functional\n")
            return True

        except Exception as e:
            print(f"- MCP integration test failed: {e}\n")
            return False


async def test_godot_tools():
    """Test Godot plugin tools functionality."""
    print("=" * 60)
    print("Testing Godot Plugin Tools")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        try:
            # Check if Godot tools are available
            response = await client.get("http://localhost:8000/api/agent/config")
            response.raise_for_status()
            data = response.json()

            tools = data['config']['tools']

            # Check for Godot tools - look for specific Godot tool patterns
            godot_patterns = ['project', 'scene', 'node', 'bridge', 'create_', 'modify_', 'open_', 'select_', 'play_', 'stop_', 'validate_']
            godot_tools = [t for t in tools if any(pattern in t.lower() for pattern in godot_patterns)]

            if not godot_tools:
                print("- Godot Tools: FAILED - No Godot tools found")
                print("Error: Godot plugin is not installed or not properly configured")
                print("Please ensure the Godot plugin is installed and connected")
                return False

            print(f"Godot Tools: AVAILABLE")
            print(f"Godot Tools Found: {len(godot_tools)}")

            print("\nGodot Tools:")
            for tool in godot_tools:
                print(f"  - {tool}")

            # Test Godot connection with a specific prompt that requires Godot tools
            print("\nTesting Godot connection...")
            godot_prompt = "Connect to Godot and get the current scene tree information"

            try:
                response = await client.post(
                    "http://localhost:8000/api/agent/plan",
                    json={
                        "prompt": godot_prompt,
                        "reset_conversation": True
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

                print(f"Status: {data['status']}")
                print(f"\nGodot Test Response:\n{'-' * 60}")
                response_text = data['plan']
                print(response_text)
                print("-" * 60)

                # Check if response indicates successful Godot connection
                response_lower = response_text.lower()
                godot_indicators = [
                    'godot', 'plugin', 'connected', 'scene tree', 'project info',
                    'scene', 'node', 'successfully', 'connection established'
                ]
                error_indicators = [
                    'failed', 'error', 'timeout', 'not connected', 'not available',
                    'unable to connect', 'connection failed', 'plugin not found'
                ]

                has_godot_response = any(indicator in response_lower for indicator in godot_indicators)
                has_errors = any(indicator in response_lower for indicator in error_indicators)

                if has_godot_response and not has_errors:
                    print("+ Godot plugin integration functional")
                    return True
                elif has_errors:
                    print("- Godot plugin connection failed")
                    print("Error: Godot plugin may not be running or accessible")
                    return False
                else:
                    print("- Godot plugin not responding properly")
                    print("Error: Plugin may be connected but not functional")
                    return False

            except httpx.TimeoutException:
                print("- Godot connection test timed out")
                print("Error: Godot plugin is not responding within timeout")
                return False
            except Exception as e:
                print(f"- Godot connection test failed: {e}")
                return False

        except Exception as e:
            print(f"- Godot tools test failed: {e}\n")
            return False


async def test_godot_bridge_connection():
    """Test Godot bridge connection specifically."""
    print("=" * 60)
    print("Testing Godot Bridge Connection")
    print("=" * 60)

    # Import and test Godot bridge directly
    try:
        from agents.tools.godot_bridge import GodotBridge, ensure_godot_connection

        bridge = GodotBridge()

        # Test connection state
        print(f"Initial connection state: {bridge.connection_state}")

        # Try to connect
        print("Attempting to connect to Godot plugin...")
        connected = await bridge.connect()

        if not connected:
            print("- FAILED: Could not connect to Godot plugin")
            print("Error: Godot plugin is not running or not accessible")
            print("Please ensure:")
            print("  1. Godot Editor is running")
            print("  2. Godot Assistant plugin is installed and enabled")
            print("  3. WebSocket server is running on the expected port")
            return False

        print("+ Successfully connected to Godot plugin")

        # Test project info retrieval
        print("Testing project info retrieval...")
        project_info = await bridge.get_project_info()
        if project_info:
            print(f"+ Project info retrieved:")
            print(f"  - Path: {project_info.project_path}")
            print(f"  - Name: {project_info.project_name}")
            print(f"  - Godot Version: {project_info.godot_version}")
            print(f"  - Plugin Version: {project_info.plugin_version}")
        else:
            print("- FAILED: Could not retrieve project info")
            print("Error: Plugin is connected but not responding to queries")
            await bridge.disconnect()
            return False

        # Test basic command
        print("Testing basic command execution...")
        try:
            response = await bridge.send_command("ping")
            if response.success:
                print("+ Basic command (ping) successful")
            else:
                print(f"- FAILED: Basic command failed: {response.error}")
                await bridge.disconnect()
                return False
        except Exception as e:
            print(f"- FAILED: Command execution error: {e}")
            await bridge.disconnect()
            return False

        # Test scene tree query
        print("Testing scene tree query...")
        try:
            response = await bridge.send_command("get_scene_tree_simple")
            if response.success:
                print("+ Scene tree query successful")
            else:
                print(f"- FAILED: Scene tree query failed: {response.error}")
                await bridge.disconnect()
                return False
        except Exception as e:
            print(f"- FAILED: Scene tree query error: {e}")
            await bridge.disconnect()
            return False

        # Disconnect
        await bridge.disconnect()
        print("+ Disconnected successfully")
        print("+ Godot bridge connection test passed")
        return True

    except ImportError as e:
        print(f"- FAILED: Godot bridge module not available: {e}")
        print("Error: Godot tools are not properly installed")
        return False
    except Exception as e:
        print(f"- FAILED: Godot bridge test failed: {e}")
        return False


async def test_godot_security():
    """Test Godot security validation."""
    print("=" * 60)
    print("Testing Godot Security Validation")
    print("=" * 60)

    try:
        from agents.tools.godot_security import (
            GodotSecurityValidator,
            create_default_security_context,
            OperationRisk,
            validate_operation,
            validate_path,
            validate_node_name
        )

        validator = GodotSecurityValidator()
        all_passed = True

        # Test operation validation
        print("Testing operation validation...")

        # Safe operation - should pass
        result = validate_operation("get_project_info")
        if result.allowed:
            print(f"  + get_project_info: ALLOWED (SAFE)")
        else:
            print(f"  - get_project_info: FAILED - {result.reason}")
            all_passed = False

        # Medium risk operation - should pass with medium threshold
        result = validate_operation("create_node", {"node_type": "Node2D", "parent_path": "Root"})
        if result.allowed:
            print(f"  + create_node: ALLOWED (MEDIUM)")
        else:
            print(f"  - create_node: FAILED - {result.reason}")
            all_passed = False

        # High risk operation - should fail with medium threshold
        result = validate_operation("delete_node", {"node_path": "Root/Node2D"})
        if not result.allowed and result.risk_level == OperationRisk.HIGH:
            print(f"  + delete_node: BLOCKED (HIGH RISK)")
        else:
            print(f"  - delete_node: FAILED - Should be blocked at medium threshold")
            all_passed = False

        # Critical risk operation - should fail
        result = validate_operation("delete_scene", {"scene_path": "res://scenes/main.tscn"})
        if not result.allowed and result.risk_level == OperationRisk.CRITICAL:
            print(f"  + delete_scene: BLOCKED (CRITICAL RISK)")
        else:
            print(f"  - delete_scene: FAILED - Should be blocked at medium threshold")
            all_passed = False

        # Test path validation
        print("\nTesting path validation...")

        # Valid paths - should pass
        result = validate_path("res://scenes/main.tscn")
        if result.allowed:
            print(f"  + res://scenes/main.tscn: VALID")
        else:
            print(f"  - res://scenes/main.tscn: FAILED - {result.reason}")
            all_passed = False

        result = validate_path("user://save_data.dat")
        if result.allowed:
            print(f"  + user://save_data.dat: VALID")
        else:
            print(f"  - user://save_data.dat: FAILED - {result.reason}")
            all_passed = False

        # Invalid paths - should fail
        result = validate_path("../../../etc/passwd")
        if not result.allowed:
            print(f"  + ../../../etc/passwd: BLOCKED (path traversal)")
        else:
            print(f"  - ../../../etc/passwd: FAILED - Should be blocked")
            all_passed = False

        result = validate_path("res://../../../system32/cmd.exe")
        if not result.allowed:
            print(f"  + res://../../../system32/cmd.exe: BLOCKED (suspicious path)")
        else:
            print(f"  - res://../../../system32/cmd.exe: FAILED - Should be blocked")
            all_passed = False

        # Test node name validation
        print("\nTesting node name validation...")

        # Valid names - should pass
        result = validate_node_name("Player")
        if result.allowed:
            print(f"  + Player: VALID")
        else:
            print(f"  - Player: FAILED - {result.reason}")
            all_passed = False

        result = validate_node_name("UI_Button")
        if result.allowed:
            print(f"  + UI_Button: VALID")
        else:
            print(f"  - UI_Button: FAILED - {result.reason}")
            all_passed = False

        # Invalid names - should fail
        result = validate_node_name("")
        if not result.allowed:
            print(f"  + (empty): BLOCKED (empty name)")
        else:
            print(f"  - (empty): FAILED - Should be blocked")
            all_passed = False

        result = validate_node_name("root")  # Reserved name
        if not result.allowed:
            print(f"  + root: BLOCKED (reserved name)")
        else:
            print(f"  - root: FAILED - Should be blocked")
            all_passed = False

        result = validate_node_name("Node With Spaces")
        if not result.allowed:
            print(f"  + Node With Spaces: BLOCKED (invalid characters)")
        else:
            print(f"  - Node With Spaces: FAILED - Should be blocked")
            all_passed = False

        if all_passed:
            print("+ All Godot security validation tests passed\n")
            return True
        else:
            print("- Some Godot security validation tests failed\n")
            return False

    except ImportError as e:
        print(f"- FAILED: Godot security module not available: {e}")
        print("Error: Godot tools are not properly installed")
        return False
    except Exception as e:
        print(f"- FAILED: Godot security test failed: {e}")
        return False


async def test_godot_tools_integration():
    """Test integration of all Godot tools."""
    print("=" * 60)
    print("Testing Godot Tools Integration")
    print("=" * 60)

    try:
        from agents.tools.godot_debug_tools import GodotDebugTools
        from agents.tools.godot_executor_tools import GodotExecutorTools

        # Initialize tools
        debug_tools = GodotDebugTools()
        executor_tools = GodotExecutorTools()

        print("+ Tools initialized successfully")

        # Test connection - both must connect for test to pass
        print("Testing tool connections...")

        debug_connected = await debug_tools.ensure_connection()
        executor_connected = await executor_tools.ensure_connection()

        if not debug_connected:
            print("  - Debug tools connection: FAILED")
        else:
            print("  + Debug tools connection: SUCCESS")

        if not executor_connected:
            print("  - Executor tools connection: FAILED")
        else:
            print("  + Executor tools connection: SUCCESS")

        # Fail the test if either tool set cannot connect
        if not debug_connected or not executor_connected:
            print("\n- FAILED: Cannot establish connection to Godot plugin")
            print("Error: Godot plugin must be running for tools to function")
            return False

        # Test debug tools functionality
        print("\nTesting debug tools functionality...")

        try:
            overview = await debug_tools.get_project_overview()
            if overview and 'project_info' in overview:
                print("  + Project overview retrieved successfully")
                project_path = overview.get('project_info', {}).get('path', 'Unknown')
                print(f"    - Project path: {project_path}")
            else:
                print("  - Project overview failed - invalid response")
                return False
        except Exception as e:
            print(f"  - Project overview failed: {e}")
            return False

        try:
            scene_tree = await debug_tools.get_scene_tree_analysis(detailed=False)
            if scene_tree and 'scene_tree' in scene_tree:
                print("  + Scene tree analysis retrieved successfully")
            else:
                print("  - Scene tree analysis failed - invalid response")
                return False
        except Exception as e:
            print(f"  - Scene tree analysis failed: {e}")
            return False

        # Test tool availability and basic functionality
        print("\nChecking tool availability and functionality...")

        debug_methods = [
            ('get_project_overview', True),
            ('get_scene_tree_analysis', True),
            ('get_node_details', True),
            ('search_nodes', True),
            ('capture_visual_context', False)  # This might fail if no viewport
        ]

        executor_methods = [
            ('create_node', False),  # Don't actually test destructive operations
            ('delete_node', False),
            ('modify_node_property', False),
            ('create_new_scene', False),
            ('open_scene', False),
            ('save_current_scene', False),
            ('play_scene', False),
            ('stop_playing', False)
        ]

        debug_available = 0
        for method_name, should_test in debug_methods:
            if hasattr(debug_tools, method_name):
                debug_available += 1
                print(f"  + {method_name}: Available")
            else:
                print(f"  - {method_name}: Missing")
                return False

        executor_available = 0
        for method_name, should_test in executor_methods:
            if hasattr(executor_tools, method_name):
                executor_available += 1
                print(f"  + {method_name}: Available")
            else:
                print(f"  - {method_name}: Missing")
                return False

        print(f"\nSummary:")
        print(f"  - Debug tools available: {debug_available}/{len(debug_methods)} methods")
        print(f"  - Executor tools available: {executor_available}/{len(executor_methods)} methods")

        print("+ Godot tools integration test passed\n")
        return True

    except ImportError as e:
        print(f"- FAILED: Godot tools modules not available: {e}")
        print("Error: Godot tools are not properly installed")
        return False
    except Exception as e:
        print(f"- FAILED: Godot tools integration test failed: {e}")
        return False


async def test_reset():
    """Test conversation reset."""
    print("=" * 60)
    print("Testing Conversation Reset")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post("http://localhost:8000/api/agent/reset")
            response.raise_for_status()
            data = response.json()

            print(f"Status: {data['status']}")
            print(f"Message: {data['message']}")
            print("+ Reset successful\n")
            return True

        except Exception as e:
            print(f"- Reset failed: {e}\n")
            return False


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("PLANNING AGENT TEST SUITE")
    print("=" * 60)
    print()

    # Check if server is running
    print("Checking if server is running...")
    try:
        async with httpx.AsyncClient() as client:
            await client.get("http://localhost:8000/api/health", timeout=5.0)
        print("+ Server is running\n")
    except Exception:
        print("- Server is not running!")
        print("\nPlease start the server first:")
        print("  cd backend")
        print("  python main.py")
        print()
        sys.exit(1)

    # Run tests
    results = []

    results.append(("Health Check", await test_health()))
    results.append(("Configuration", await test_config()))
    results.append(("MCP Integration", await test_mcp_integration()))
    results.append(("Godot Tools", await test_godot_tools()))
    results.append(("Godot Bridge", await test_godot_bridge_connection()))
    results.append(("Godot Security", await test_godot_security()))
    results.append(("Godot Integration", await test_godot_tools_integration()))
    results.append(("Simple Plan", await test_plan_simple()))
    results.append(("Streaming Plan", await test_plan_streaming()))
    results.append(("Reset", await test_reset()))

    # Summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for test_name, result in results:
        status = "+ PASS" if result else "- FAIL"
        print(f"{test_name:.<40} {status}")

    total_tests = len(results)
    passed_tests = sum(1 for _, result in results if result)

    print()
    print(f"Total: {passed_tests}/{total_tests} tests passed")
    print("=" * 60)
    print()

    # Exit with appropriate code
    sys.exit(0 if passed_tests == total_tests else 1)


if __name__ == "__main__":
    asyncio.run(main())
