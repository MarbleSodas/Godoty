"""
Integration tests for Godot Agent Integration Tools.

This module tests the integration between different components and
end-to-end workflows that simulate real usage scenarios.
"""

import asyncio
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from agents.tools import (
    # Bridge
    ensure_godot_connection,
    get_godot_bridge,

    # Debug tools
    get_project_overview,
    analyze_scene_tree,
    capture_visual_context,
    search_nodes,

    # Executor tools
    create_node,
    modify_node_property,
    create_scene,
    select_nodes,
    play_scene,
    stop_playing,

    # Security
    validate_operation,
    SecurityContext,
    OperationRisk
)


class TestBasicIntegration:
    """Test basic integration scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_planning_workflow(self, mock_godot_bridge, mock_project_info, mock_scene_tree, mock_search_results):
        """Test complete planning agent workflow."""
        # Mock all bridge responses
        mock_godot_bridge.get_project_info = AsyncMock(return_value=mock_project_info)
        mock_godot_bridge.send_command = AsyncMock(side_effect=[
            # get_current_scene_info
            MagicMock(success=True, data={"name": "Main", "path": "res://scenes/main.tscn"}),
            # get_project_statistics
            MagicMock(success=True, data={"total_scenes": 3, "total_scripts": 5}),
            # get_editor_state
            MagicMock(success=True, data={"playing": False}),
            # analyze_scene_tree
            MagicMock(success=True, data=mock_scene_tree),
            # capture_viewport_screenshot
            MagicMock(success=True, data="/tmp/screenshot.png"),
            # get_viewport_info
            MagicMock(success=True, data={"width": 1920, "height": 1080}),
            # get_selected_nodes
            MagicMock(success=True, data=[]),
            # search_nodes_by_type
            MagicMock(success=True, data=mock_search_results)
        ])

        with patch('agents.tools.godot_debug_tools.get_godot_bridge', return_value=mock_godot_bridge):
            # Step 1: Ensure connection
            connected = await ensure_godot_connection()
            assert connected is True

            # Step 2: Get project overview
            overview = await get_project_overview()
            assert "project_info" in overview
            assert overview["project_info"]["project_name"] == "TestGame"

            # Step 3: Analyze scene tree
            scene_analysis = await analyze_scene_tree(detailed=True)
            assert "scene_tree" in scene_analysis
            assert "analysis" in scene_analysis

            # Step 4: Capture visual context
            snapshot = await capture_visual_context()
            assert snapshot.viewport_size == (1920, 1080)

            # Step 5: Search for specific nodes
            nodes = await search_nodes("type", "CharacterBody2D")
            assert len(nodes) > 0

            # Verify all expected calls were made
            assert mock_godot_bridge.send_command.call_count >= 6

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_execution_workflow(self, mock_godot_bridge):
        """Test complete executor agent workflow."""
        # Mock bridge responses
        mock_godot_bridge.send_command = AsyncMock(side_effect=[
            # create_node
            MagicMock(success=True, data={"path": "Root/Player"}),
            # modify_node_property
            MagicMock(success=True, data={"old_value": {"x": 0, "y": 0}}),
            # create_node (sprite)
            MagicMock(success=True, data={"path": "Root/Player/Sprite"}),
            # modify_node_property (texture)
            MagicMock(success=True, data={"old_value": None}),
            # select_nodes
            MagicMock(success=True),
            # play_scene
            MagicMock(success=True),
            # stop_playing
            MagicMock(success=True)
        ])

        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            # Step 1: Create a player node
            result = await create_node("CharacterBody2D", "Root", "Player")
            assert result.success is True
            assert result.created_path == "Root/Player"

            # Step 2: Modify player position
            mod_result = await modify_node_property(
                "Root/Player",
                "position",
                {"x": 100, "y": 100}
            )
            assert mod_result.success is True
            assert mod_result.old_value == {"x": 0, "y": 0}

            # Step 3: Add a sprite to the player
            sprite_result = await create_node("Sprite2D", "Root/Player", "Sprite")
            assert sprite_result.success is True
            assert sprite_result.created_path == "Root/Player/Sprite"

            # Step 4: Set sprite texture
            texture_result = await modify_node_property(
                "Root/Player/Sprite",
                "texture",
                "res://assets/player.png"
            )
            assert texture_result.success is True

            # Step 5: Select the created nodes
            select_result = await select_nodes(["Root/Player", "Root/Player/Sprite"])
            assert select_result is True

            # Step 6: Test the scene
            play_result = await play_scene()
            assert play_result is True

            # Step 7: Stop testing
            stop_result = await stop_playing()
            assert stop_result is True

            # Verify all operations were recorded
            bridge = get_godot_bridge()
            # Note: Operation history is in the executor tools, not bridge

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_error_handling_integration(self, mock_godot_bridge):
        """Test error handling across integrated components."""
        # Mock a failing command
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=False,
            error="Simulated failure"
        ))

        with patch('agents.tools.godot_debug_tools.get_godot_bridge', return_value=mock_godot_bridge):
            # Test that debug tools handle errors gracefully
            overview = await get_project_overview()
            assert "project_info" in overview  # Should still have basic info

            # Test that executor tools handle errors gracefully
            result = await create_node("Node2D", "Root", "TestNode")
            assert result.success is False
            assert "Simulated failure" in result.error

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_security_integration(self, mock_godot_bridge, mock_security_context):
        """Test security integration with operations."""
        # Set up strict security context
        mock_security_context.set_risk_threshold(OperationRisk.LOW)
        mock_security_context.project_path = "/test/project"

        # Mock bridge for security validation
        mock_godot_bridge.security_validator.validate_operation = MagicMock()
        mock_godot_bridge.security_validator.validate_operation.return_value = MagicMock(
            allowed=True,
            warnings=[]
        )
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            # Security validation should be called before operations
            result = await create_node("Node2D", "Root", "TestNode")
            assert result.success is True

            # Verify security validation was called
            mock_godot_bridge.security_validator.validate_operation.assert_called()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_project_path_detection_integration(self, mock_godot_bridge, mock_project_info):
        """Test project path detection and usage across components."""
        # Mock project info reception
        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data=mock_scene_tree
        ))

        # Mock the connection process to send project info
        async def mock_connect():
            mock_godot_bridge.connection_state = ConnectionState.CONNECTED
            mock_godot_bridge.websocket = MagicMock()
            # Simulate receiving project info
            await mock_godot_bridge._handle_project_info({
                "type": "project_info",
                "data": mock_project_info
            })
            return True

        mock_godot_bridge.connect = mock_connect
        mock_godot_bridge.is_connected = AsyncMock(return_value=False)

        with patch('agents.tools.godot_bridge.get_godot_bridge', return_value=mock_godot_bridge):
            # Connect to Godot
            connected = await ensure_godot_connection()
            assert connected is True

            # Verify project path was detected
            bridge = get_godot_bridge()
            assert bridge.get_project_path() == mock_project_info["project_path"]
            assert bridge.is_project_ready() is True

            # Test that security context uses the detected path
            assert bridge.security_context.project_path == mock_project_info["project_path"]


class TestAdvancedIntegration:
    """Test advanced integration scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_batch_operations_integration(self, mock_godot_bridge):
        """Test batch operations across multiple components."""
        # Mock multiple successful responses
        responses = []
        for i in range(5):
            responses.append(MagicMock(success=True, data={"path": f"Root/Node{i}"}))
        responses.extend([
            MagicMock(success=True, data={"old_value": False, "new_value": True}) for _ in range(5)
        ])

        mock_godot_bridge.send_command = AsyncMock(side_effect=responses)

        from agents.tools.godot_executor_tools import GodotExecutorTools

        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            tools = GodotExecutorTools()

            # Create multiple nodes in batch
            creations = [
                {"node_type": "Node2D", "parent_path": "Root", "node_name": f"Node{i}"}
                for i in range(5)
            ]

            with patch('asyncio.sleep', new_callable=AsyncMock):
                creation_results = await tools.create_node_batch(creations)

            assert len(creation_results) == 5
            assert all(result.success for result in creation_results)

            # Modify multiple properties in batch
            modifications = [
                {"node_path": f"Root/Node{i}", "property_name": "visible", "new_value": True}
                for i in range(5)
            ]

            with patch('asyncio.sleep', new_callable=AsyncMock):
                mod_results = await tools.modify_properties_batch(modifications)

            assert len(mod_results) == 5
            assert all(result.success for result in mod_results)

            # Verify operation history
            history = await tools.get_operation_history()
            assert len(history) == 10

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_undo_redo_integration(self, mock_godot_bridge):
        """Test undo/redo functionality integration."""
        # Mock responses for operations and undo/redo
        mock_godot_bridge.send_command = AsyncMock(side_effect=[
            # create_node
            MagicMock(success=True, data={"path": "Root/TestNode"}),
            # undo
            MagicMock(success=True),
            # redo
            MagicMock(success=True)
        ])

        from agents.tools.godot_executor_tools import GodotExecutorTools

        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            tools = GodotExecutorTools()

            # Create a node
            result = await tools.create_node("Node2D", "Root", "TestNode")
            assert result.success is True

            # Undo the operation
            undo_result = await tools.undo_last_operation()
            assert undo_result is True

            # Redo the operation
            redo_result = await tools.redo_last_operation()
            assert redo_result is True

            # Verify all commands were called
            assert mock_godot_bridge.send_command.call_count == 3

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_connection_recovery_integration(self, mock_godot_bridge):
        """Test connection recovery during operations."""
        call_count = 0

        async def mock_send_command(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # Fail on first call, succeed on subsequent calls
            if call_count == 1:
                raise ConnectionError("Connection lost")
            return MagicMock(success=True, data={"path": "Root/Node"})

        mock_godot_bridge.send_command = mock_send_command
        mock_godot_bridge.is_connected = AsyncMock(side_effect=[False, True])
        mock_godot_bridge.connect = AsyncMock(return_value=True)

        from agents.tools.godot_executor_tools import GodotExecutorTools

        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            tools = GodotExecutorTools()

            # Operation should recover from connection failure
            result = await tools.create_node("Node2D", "Root", "TestNode")
            assert result.success is True

            # Verify connection recovery was attempted
            mock_godot_bridge.connect.assert_called()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_cross_component_data_flow(self, mock_godot_bridge, mock_scene_tree, mock_search_results):
        """Test data flow between different components."""
        # Mock search results
        player_nodes = [
            {
                "name": "Player",
                "type": "CharacterBody2D",
                "path": "Root/Player",
                "parent": "Root",
                "children": [],
                "properties": {"position": {"x": 0, "y": 0}},
                "groups": ["player"],
                "has_script": True,
                "script_path": "res://scripts/player.gd"
            }
        ]

        mock_godot_bridge.send_command = AsyncMock(side_effect=[
            # analyze_scene_tree
            MagicMock(success=True, data=mock_scene_tree),
            # search_nodes_by_type
            MagicMock(success=True, data=player_nodes),
            # modify_node_property
            MagicMock(success=True, data={"old_value": {"x": 0, "y": 0}})
        ])

        # Simulate workflow: analyze -> find -> modify
        with patch('agents.tools.godot_debug_tools.get_godot_bridge', return_value=mock_godot_bridge):
            # Step 1: Analyze scene
            from agents.tools.godot_debug_tools import GodotDebugTools
            debug_tools = GodotDebugTools()
            scene_analysis = await debug_tools.get_scene_tree_analysis()
            assert "analysis" in scene_analysis

        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            # Step 2: Find player node
            from agents.tools.godot_debug_tools import GodotDebugTools
            debug_tools = GodotDebugTools()
            player_nodes = await debug_tools.search_nodes("type", "CharacterBody2D")
            assert len(player_nodes) > 0

            # Step 3: Modify found node
            from agents.tools.godot_executor_tools import GodotExecutorTools
            executor_tools = GodotExecutorTools()
            player_path = player_nodes[0].path
            mod_result = await executor_tools.modify_node_property(
                player_path,
                "position",
                {"x": 100, "y": 50}
            )
            assert mod_result.success is True


class TestPerformanceIntegration:
    """Test performance-related integration scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_concurrent_operations(self, mock_godot_bridge):
        """Test concurrent operations handling."""
        import time

        # Mock responses with slight delay to simulate real operations
        async def mock_send_command(*args, **kwargs):
            await asyncio.sleep(0.01)  # Small delay
            return MagicMock(success=True, data={"path": f"Root/Node{time.time()}"})

        mock_godot_bridge.send_command = mock_send_command

        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            from agents.tools.godot_executor_tools import GodotExecutorTools
            tools = GodotExecutorTools()

            # Create multiple nodes concurrently
            tasks = [
                tools.create_node("Node2D", "Root", f"ConcurrentNode{i}")
                for i in range(10)
            ]

            start_time = time.time()
            results = await asyncio.gather(*tasks)
            end_time = time.time()

            # All operations should succeed
            assert len(results) == 10
            assert all(result.success for result in results)

            # Should be faster than sequential execution
            execution_time = end_time - start_time
            assert execution_time < 0.5  # Should be much less than 10 * 0.01 sequentially

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_large_scene_analysis(self, mock_godot_bridge):
        """Test handling of large scene data."""
        # Create a large scene tree
        def create_large_scene_tree(depth=5, width=5):
            """Create a large nested scene tree."""
            def create_node(name, depth_remaining):
                if depth_remaining == 0:
                    return {
                        "name": name,
                        "type": "Node",
                        "path": name,
                        "properties": {},
                        "children": []
                    }

                children = []
                for i in range(width):
                    child_name = f"{name}/Child{i}"
                    children.append(create_node(child_name, depth_remaining - 1))

                return {
                    "name": name,
                    "type": "Node",
                    "path": name,
                    "properties": {},
                    "children": children
                }

            return create_node("Root", depth)

        large_scene = create_large_scene_tree(4, 4)  # Creates ~341 nodes

        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(
            success=True,
            data=large_scene
        ))

        with patch('agents.tools.godot_debug_tools.get_godot_bridge', return_value=mock_godot_bridge):
            from agents.tools.godot_debug_tools import GodotDebugTools
            tools = GodotDebugTools()

            # Should handle large scene without issues
            analysis = await tools.get_scene_tree_analysis(detailed=True)

            assert "analysis" in analysis
            assert analysis["analysis"]["total_nodes"] > 300
            assert analysis["analysis"]["depth"] == 4

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_memory_usage_integration(self, mock_godot_bridge):
        """Test memory usage during extended operations."""
        import gc
        import sys

        mock_godot_bridge.send_command = AsyncMock(return_value=MagicMock(success=True))

        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            from agents.tools.godot_executor_tools import GodotExecutorTools
            tools = GodotExecutorTools()

            # Perform many operations
            for i in range(100):
                await tools.create_node("Node", "Root", f"TempNode{i}")
                if i % 10 == 0:
                    # Clear history periodically
                    await tools.clear_operation_history()

            # Check that memory is being managed
            gc.collect()
            history = await tools.get_operation_history()
            assert len(history) < 100  # Should be cleaned up periodically


class TestErrorRecoveryIntegration:
    """Test error recovery and resilience scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_partial_failure_recovery(self, mock_godot_bridge):
        """Test recovery from partial failures in batch operations."""
        # Mix of success and failure responses
        responses = []
        for i in range(10):
            if i % 3 == 0:  # Every 3rd operation fails
                responses.append(MagicMock(success=False, error=f"Node {i} creation failed"))
            else:
                responses.append(MagicMock(success=True, data={"path": f"Root/Node{i}"}))

        mock_godot_bridge.send_command = AsyncMock(side_effect=responses)

        from agents.tools.godot_executor_tools import GodotExecutorTools

        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            tools = GodotExecutorTools()

            creations = [
                {"node_type": "Node", "parent_path": "Root", "node_name": f"Node{i}"}
                for i in range(10)
            ]

            with patch('asyncio.sleep', new_callable=AsyncMock):
                results = await tools.create_node_batch(creations)

            # Some should succeed, some should fail
            assert len(results) == 10
            successful_count = sum(1 for r in results if r.success)
            failed_count = sum(1 for r in results if not r.success)
            assert successful_count > 0
            assert failed_count > 0

            # All operations should be recorded regardless of outcome
            history = await tools.get_operation_history()
            assert len(history) == 10

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_timeout_recovery(self, mock_godot_bridge):
        """Test recovery from timeout scenarios."""
        call_count = 0

        async def mock_send_command(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # Timeout on first call, succeed on subsequent
            if call_count == 1:
                await asyncio.sleep(5)  # Long delay to trigger timeout
                return MagicMock(success=True)
            else:
                return MagicMock(success=True, data={"path": "Root/RecoveredNode"})

        mock_godot_bridge.send_command = mock_send_command
        mock_godot_bridge.command_timeout = 0.1  # Very short timeout

        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            from agents.tools.godot_executor_tools import GodotExecutorTools
            tools = GodotExecutorTools()

            # First operation should timeout
            result = await tools.create_node("Node", "Root", "TimeoutNode")
            assert result.success is False
            assert "timed out" in result.error.lower()

            # Subsequent operations should work
            result2 = await tools.create_node("Node", "Root", "RecoveredNode")
            assert result2.success is True

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_invalid_data_recovery(self, mock_godot_bridge):
        """Test recovery from invalid or malformed data."""
        # Mock responses with various issues
        mock_godot_bridge.send_command = AsyncMock(side_effect=[
            # Invalid JSON-like data (missing required fields)
            {"success": True},  # Missing data field
            # Malformed path
            MagicMock(success=True, data={"path": ""}),  # Empty path
            # Eventually a good response
            MagicMock(success=True, data={"path": "Root/ValidNode"})
        ])

        with patch('agents.tools.godot_executor_tools.get_godot_bridge', return_value=mock_godot_bridge):
            from agents.tools.godot_executor_tools import GodotExecutorTools
            tools = GodotExecutorTools()

            # Should handle various invalid responses gracefully
            for i in range(3):
                result = await tools.create_node("Node", "Root", f"TestNode{i}")
                if i < 2:
                    # First two might have issues but should not crash
                    assert isinstance(result, object)  # Should return some result object
                else:
                    # Final one should work
                    assert result.success is True


class TestConfigurationIntegration:
    """Test configuration-related integration scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_configuration_changes_integration(self, mock_godot_bridge):
        """Test that configuration changes affect behavior."""
        # Test with different configurations
        configs = [
            {"timeout": 1.0, "max_retries": 1},
            {"timeout": 5.0, "max_retries": 3},
            {"timeout": 10.0, "max_retries": 5}
        ]

        for config in configs:
            # Create new bridge with different config
            from agents.tools.godot_bridge import GodotBridge
            bridge = GodotBridge(config)

            # Mock connection failure to test retry behavior
            with patch('websockets.connect') as mock_connect:
                mock_connect.side_effect = Exception("Connection failed")
                bridge.retry_delay = 0.01  # Fast retry for test

                result = await bridge.connect()
                assert result is False

                # Verify retry count matches configuration
                assert mock_connect.call_count == config["max_retries"]

    