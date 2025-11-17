"""
Basic usage examples for Godot Agent Integration Tools.

This script demonstrates fundamental operations and error handling patterns
for working with Godot projects through the agent tools.
"""

import asyncio
import logging
from typing import List

# Import the main tools
from agents.tools import (
    # Connection and bridge
    ensure_godot_connection,
    get_godot_bridge,

    # Debug tools for planning
    get_project_overview,
    analyze_scene_tree,
    capture_visual_context,
    search_nodes,

    # Executor tools for actions
    create_node,
    modify_node_property,
    create_scene,
    open_scene,
    select_nodes,
    play_scene,
    stop_playing,

    # Data classes
    CreationResult,
    ModificationResult,
    NodeInfo,
    VisualSnapshot
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def basic_connection_example():
    """Demonstrate basic connection management."""
    logger.info("=== Basic Connection Example ===")

    try:
        # Ensure connection to Godot
        connected = await ensure_godot_connection()
        if not connected:
            logger.error("Failed to connect to Godot plugin")
            return False

        logger.info("Successfully connected to Godot plugin")

        # Get bridge instance and check project status
        bridge = get_godot_bridge()
        project_path = bridge.get_project_path()
        logger.info(f"Current project path: {project_path}")

        return True

    except Exception as e:
        logger.error(f"Connection error: {e}")
        return False


async def project_analysis_example():
    """Demonstrate project analysis capabilities."""
    logger.info("\n=== Project Analysis Example ===")

    try:
        # Get comprehensive project overview
        logger.info("Getting project overview...")
        overview = await get_project_overview()

        project_info = overview['project_info']
        logger.info(f"Project: {project_info['name']}")
        logger.info(f"Path: {project_info['path']}")
        logger.info(f"Godot Version: {project_info['godot_version']}")

        # Analyze current scene
        logger.info("Analyzing current scene...")
        scene_analysis = await analyze_scene_tree(detailed=True)

        analysis = scene_analysis['analysis']
        logger.info(f"Scene has {analysis['total_nodes']} nodes")
        logger.info(f"Scene depth: {analysis['depth']}")
        logger.info(f"Complexity score: {analysis['complexity_score']}")

        # Show recommendations
        if scene_analysis['recommendations']:
            logger.info("Recommendations:")
            for rec in scene_analysis['recommendations']:
                logger.info(f"  - {rec}")

        # Capture visual context
        logger.info("Capturing visual context...")
        snapshot: VisualSnapshot = await capture_visual_context()

        if snapshot.screenshot_path:
            logger.info(f"Screenshot saved to: {snapshot.screenshot_path}")
        logger.info(f"Viewport size: {snapshot.viewport_size}")
        logger.info(f"Selected nodes: {snapshot.selected_nodes}")

        return True

    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return False


async def node_operations_example():
    """Demonstrate node creation and modification."""
    logger.info("\n=== Node Operations Example ===")

    try:
        # Search for existing nodes
        logger.info("Searching for Node2D nodes...")
        nodes = await search_nodes("type", "Node2D")
        logger.info(f"Found {len(nodes)} Node2D nodes")

        if nodes:
            logger.info("Node2D nodes found:")
            for node in nodes[:5]:  # Show first 5
                logger.info(f"  - {node.name} ({node.type}) at {node.path}")

        # Create a new node
        logger.info("Creating a new Node2D...")
        result: CreationResult = await create_node(
            node_type="Node2D",
            parent_path="Root",
            node_name="TestNode"
        )

        if result.success:
            logger.info(f"Successfully created node: {result.created_path}")

            # Modify the new node's position
            logger.info("Modifying node position...")
            mod_result: ModificationResult = await modify_node_property(
                node_path=result.created_path,
                property_name="position",
                new_value={"x": 100, "y": 100}
            )

            if mod_result.success:
                logger.info(f"Changed position from {mod_result.old_value} to {mod_result.new_value}")
            else:
                logger.error(f"Failed to modify position: {mod_result.error}")

        else:
            logger.error(f"Failed to create node: {result.error}")

        return result.success

    except Exception as e:
        logger.error(f"Node operations error: {e}")
        return False


async def scene_management_example():
    """Demonstrate scene creation and management."""
    logger.info("\n=== Scene Management Example ===")

    try:
        # Create a new scene
        logger.info("Creating a new scene...")
        result: CreationResult = await create_scene(
            scene_name="TestScene",
            root_node_type="Node2D",
            save_path="res://test_scene.tscn"
        )

        if result.success:
            logger.info(f"Successfully created scene: {result.created_path}")

            # Add some nodes to the new scene
            logger.info("Adding nodes to the scene...")

            # Create a sprite
            sprite_result = await create_node(
                node_type="Sprite2D",
                parent_path="Root",
                node_name="TestSprite"
            )

            if sprite_result.success:
                logger.info(f"Created sprite: {sprite_result.created_path}")

            # Create a label
            label_result = await create_node(
                node_type="Label",
                parent_path="Root",
                node_name="TestLabel"
            )

            if label_result.success:
                logger.info(f"Created label: {label_result.created_path}")

                # Modify the label text
                text_result = await modify_node_property(
                    node_path=label_result.created_path,
                    property_name="text",
                    new_value="Hello from Agent!"
                )

                if text_result.success:
                    logger.info("Set label text successfully")

        else:
            logger.error(f"Failed to create scene: {result.error}")

        return result.success

    except Exception as e:
        logger.error(f"Scene management error: {e}")
        return False


async def playback_control_example():
    """Demonstrate scene playback control."""
    logger.info("\n=== Playback Control Example ===")

    try:
        # Start playing the current scene
        logger.info("Starting scene playback...")
        if await play_scene():
            logger.info("Scene started playing")

            # Let it run for a moment
            await asyncio.sleep(2)

            # Stop playing
            logger.info("Stopping scene playback...")
            if await stop_playing():
                logger.info("Scene stopped playing")

            return True
        else:
            logger.error("Failed to start scene playback")
            return False

    except Exception as e:
        logger.error(f"Playback control error: {e}")
        return False


async def selection_example():
    """Demonstrate node selection."""
    logger.info("\n=== Selection Example ===")

    try:
        # Search for nodes to select
        nodes = await search_nodes("type", "Node2D")

        if nodes:
            # Select the first few nodes
            node_paths = [node.path for node in nodes[:3]]
            logger.info(f"Selecting nodes: {node_paths}")

            if await select_nodes(node_paths):
                logger.info("Successfully selected nodes")

                # Focus on the first node
                if await focus_node(node_paths[0]):
                    logger.info(f"Focused on: {node_paths[0]}")

            return True
        else:
            logger.info("No Node2D nodes found to select")
            return True

    except Exception as e:
        logger.error(f"Selection error: {e}")
        return False


async def error_handling_example():
    """Demonstrate proper error handling."""
    logger.info("\n=== Error Handling Example ===")

    try:
        # Try to create a node with invalid parent
        logger.info("Testing error handling with invalid parent...")
        result: CreationResult = await create_node(
            node_type="Sprite2D",
            parent_path="NonExistent/Path",
            node_name="ErrorTest"
        )

        if not result.success:
            logger.info(f"Expected error caught: {result.error}")
        else:
            logger.warning("Unexpected success with invalid parent")

        # Try to modify non-existent node
        logger.info("Testing error handling with non-existent node...")
        mod_result: ModificationResult = await modify_node_property(
            node_path="NonExistent/Node",
            property_name="visible",
            new_value=False
        )

        if not mod_result.success:
            logger.info(f"Expected error caught: {mod_result.error}")
        else:
            logger.warning("Unexpected success with non-existent node")

        return True

    except Exception as e:
        logger.error(f"Unexpected error in error handling example: {e}")
        return False


async def main():
    """Run all examples."""
    logger.info("Starting Godot Tools Basic Usage Examples")
    logger.info("=" * 50)

    examples = [
        basic_connection_example,
        project_analysis_example,
        node_operations_example,
        scene_management_example,
        playback_control_example,
        selection_example,
        error_handling_example
    ]

    results = []
    for example in examples:
        try:
            result = await example()
            results.append(result)
        except Exception as e:
            logger.error(f"Example {example.__name__} failed: {e}")
            results.append(False)

    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("Example Summary:")
    for i, (example, result) in enumerate(zip(examples, results)):
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{i+1}. {example.__name__}: {status}")

    passed = sum(results)
    total = len(results)
    logger.info(f"\nTotal: {passed}/{total} examples passed")

    return passed == total


if __name__ == "__main__":
    # Run the examples
    success = asyncio.run(main())
    exit(0 if success else 1)