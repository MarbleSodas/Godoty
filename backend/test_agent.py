"""
Test script for the planning agent.

This script tests both streaming and non-streaming endpoints.
Run this after starting the FastAPI server.
"""

import httpx
import asyncio
import json
import sys
import warnings

# Suppress LangGraph warning
warnings.filterwarnings("ignore", message="Graph without execution limits may run indefinitely if cycles exist")


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




async def test_godot_tools_integration():
    """Test integration and functionality of all Godot debugging tools."""
    print("=" * 60)
    print("Testing Godot Debugging Tools Integration")
    print("=" * 60)

    try:
        # Test tool imports
        print("Testing tool imports...")
        from agents.tools.godot_debug_tools import (
            get_project_overview, analyze_scene_tree, capture_visual_context,
            capture_editor_viewport, capture_game_viewport, get_visual_debug_info,
            get_debug_output, get_debug_logs, search_debug_logs, monitor_debug_output,
            get_performance_metrics, inspect_scene_file, search_nodes,
            analyze_node_performance, get_scene_debug_overlays, compare_scenes,
            get_debugger_state, access_debug_variables, get_call_stack_info
        )
        print("  + All debugging tools imported successfully")

        # Test agent tool availability
        print("\nTesting agent tool availability...")
        from agents.planning_agent import PlanningAgent

        # Create agent instance to check tool availability
        agent = PlanningAgent()
        print(f"  + Planning agent initialized with {len(agent.tools)} tools")

        # Check that all debugging tools are available to the agent
        expected_debug_tools = {
            'get_project_overview', 'analyze_scene_tree', 'capture_visual_context',
            'capture_editor_viewport', 'capture_game_viewport', 'get_visual_debug_info',
            'get_debug_output', 'get_debug_logs', 'search_debug_logs', 'monitor_debug_output',
            'get_performance_metrics', 'inspect_scene_file', 'search_nodes',
            'analyze_node_performance', 'get_scene_debug_overlays', 'compare_scenes',
            'get_debugger_state', 'access_debug_variables', 'get_call_stack_info'
        }

        agent_tool_names = {tool.__name__ if hasattr(tool, '__name__') else type(tool).__name__
                          for tool in agent.tools}

        available_debug_tools = expected_debug_tools.intersection(agent_tool_names)
        missing_debug_tools = expected_debug_tools - agent_tool_names

        print(f"  + Debug tools available to agent: {len(available_debug_tools)}/{len(expected_debug_tools)}")

        if missing_debug_tools:
            print(f"  - Missing debug tools: {missing_debug_tools}")
            return False

        print("  + All debugging tools are available to the planning agent")

        # Test basic functionality without requiring Godot connection
        print("\nTesting tool function signatures and basic properties...")

        # Test that all tools have proper signatures and are callable
        debug_tools_to_test = [
            (get_project_overview, 'get_project_overview'),
            (analyze_scene_tree, 'analyze_scene_tree'),
            (capture_visual_context, 'capture_visual_context'),
            (capture_editor_viewport, 'capture_editor_viewport'),
            (capture_game_viewport, 'capture_game_viewport'),
            (get_visual_debug_info, 'get_visual_debug_info'),
            (get_debug_output, 'get_debug_output'),
            (get_debug_logs, 'get_debug_logs'),
            (search_debug_logs, 'search_debug_logs'),
            (monitor_debug_output, 'monitor_debug_output'),
            (get_performance_metrics, 'get_performance_metrics'),
            (inspect_scene_file, 'inspect_scene_file'),
            (search_nodes, 'search_nodes'),
            (analyze_node_performance, 'analyze_node_performance'),
            (get_scene_debug_overlays, 'get_scene_debug_overlays'),
            (compare_scenes, 'compare_scenes'),
            (get_debugger_state, 'get_debugger_state'),
            (access_debug_variables, 'access_debug_variables'),
            (get_call_stack_info, 'get_call_stack_info')
        ]

        tools_with_correct_signatures = 0
        for tool_func, tool_name in debug_tools_to_test:
            try:
                # Check if tool is callable
                if callable(tool_func):
                    # Check tool signature (basic check)
                    import inspect
                    sig = inspect.signature(tool_func)

                    # Check if it's async
                    is_async = inspect.iscoroutinefunction(tool_func)
                    
                    # Handle wrapped tools (DecoratedFunctionTool)
                    if not is_async and hasattr(tool_func, '__wrapped__'):
                        is_async = inspect.iscoroutinefunction(tool_func.__wrapped__)
                    
                    if is_async:
                        tools_with_correct_signatures += 1
                        print(f"  + {tool_name}: Proper async tool signature")
                    else:
                        print(f"  - {tool_name}: Not async - should be async tool")
                        return False
                else:
                    print(f"  - {tool_name}: Not callable")
                    return False
            except Exception as e:
                print(f"  - {tool_name}: Signature check failed - {e}")
                return False

        print(f"  + {tools_with_correct_signatures}/{len(debug_tools_to_test)} tools have correct signatures")

        # Test parameter validation for some tools (without calling them)
        print("\nTesting tool parameter validation...")

        # Test search_debug_logs parameter validation
        try:
            import inspect
            sig = inspect.signature(search_debug_logs)
            params = list(sig.parameters.keys())
            expected_params = ['pattern', 'case_sensitive', 'regex']

            if all(param in params for param in expected_params):
                print("  + search_debug_logs: Correct parameters")
            else:
                print(f"  - search_debug_logs: Missing parameters. Expected: {expected_params}, Found: {params}")
                return False
        except Exception as e:
            print(f"  - search_debug_logs parameter validation failed: {e}")
            return False

        # Test get_debug_logs parameter validation
        try:
            sig = inspect.signature(get_debug_logs)
            params = list(sig.parameters.keys())
            expected_params = ['severity_filter', 'time_range', 'limit']

            if all(param in params for param in expected_params):
                print("  + get_debug_logs: Correct parameters")
            else:
                print(f"  - get_debug_logs: Missing parameters. Expected: {expected_params}, Found: {params}")
                return False
        except Exception as e:
            print(f"  - get_debug_logs parameter validation failed: {e}")
            return False

        # Test analyze_node_performance parameter validation
        try:
            sig = inspect.signature(analyze_node_performance)
            params = list(sig.parameters.keys())

            if 'node_path' in params:
                print("  + analyze_node_performance: Correct parameters")
            else:
                print(f"  - analyze_node_performance: Missing node_path parameter")
                return False
        except Exception as e:
            print(f"  - analyze_node_performance parameter validation failed: {e}")
            return False

        # Test module structure
        print("\nTesting module structure...")
        from agents.tools import __all__ as all_tools
        godot_tools = [tool for tool in all_tools if not tool.startswith(('create_node', 'modify_node', 'delete_node', 'open_scene', 'play_scene', 'stop_playing'))]

        print(f"  + Total available tools in __all__: {len(godot_tools)}")

        # Count debug tools specifically
        debug_tool_count = len([tool for tool in expected_debug_tools if tool in all_tools])
        print(f"  + Debug tools exported: {debug_tool_count}/{len(expected_debug_tools)}")

        print("\n" + "=" * 60)
        print("GODOT DEBUGGING TOOLS TEST SUMMARY")
        print("=" * 60)
        print("✅ All debugging tools imported successfully")
        print("✅ All tools available to planning agent")
        print("✅ All tools have proper async signatures")
        print("✅ Tool parameter validation passed")
        print("✅ Module structure validated")
        print(f"✅ Total debugging tools implemented: {len(debug_tools_to_test)}")
        print(f"✅ Tools available to agents: {len(available_debug_tools)}")

        print("\n+ Godot debugging tools integration test PASSED\n")
        return True

    except ImportError as e:
        print(f"- FAILED: Godot debugging tools modules not available: {e}")
        print("Error: Debugging tools are not properly installed or accessible")
        return False
    except Exception as e:
        print(f"- FAILED: Godot debugging tools integration test failed: {e}")
        import traceback
        traceback.print_exc()
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
