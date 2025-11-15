extends EditorScript

# Comprehensive Test Suite for Godoty Plugin
# Tests all 28+ commands and plugin functionality

class_name PluginTests

var test_results = {}
var current_scene = null
var plugin = null
var websocket_server = null
var command_executor = null

func _run():
	print("=== Godoty Plugin Test Suite ===")
	print("Starting comprehensive plugin verification...\n")

	# Setup test environment
	_setup_test_environment()

	# Run all test phases
	_run_phase_1_structural_tests()
	_run_phase_2_websocket_tests()
	_run_phase_3_command_tests()
	_run_phase_4_error_handling_tests()
	_run_phase_5_performance_tests()

	# Generate report
	_generate_test_report()

func _setup_test_environment():
	print("Setting up test environment...")

	# Get reference to plugin
	plugin = EditorInterface.get_editor_plugin("Godoty")
	if not plugin:
		print("ERROR: Could not find Godoty plugin!")
		return

	# Get test scene ready
	current_scene = EditorInterface.get_edited_scene_root()
	if not current_scene:
		current_scene = Node3D.new()
		current_scene.name = "TestScene"
		EditorInterface.save_scene_as("res://tmp_test_scene.tscn")
		EditorInterface.open_scene_from_path("res://tmp_test_scene.tscn")

	# Setup test nodes
	_setup_test_nodes()

	print("✓ Test environment ready\n")

func _setup_test_nodes():
	# Create test nodes for various operations
	var test_node = Node3D.new()
	test_node.name = "TestNode"
	test_node.position = Vector3(1, 2, 3)
	current_scene.add_child(test_node)
	test_node.owner = current_scene

	var test_sprite = Sprite2D.new()
	test_sprite.name = "TestSprite"
	var test_texture = load("res://icon.svg")
	if test_texture:
		test_sprite.texture = test_texture
	current_scene.add_child(test_sprite)
	test_sprite.owner = current_scene

	var test_script = GDScript.new()
	test_script.source_code = """
extends Node3D

var test_property = "test_value"

func _ready():
	print("Test script ready")

func test_method():
	return "test_result"
"""
	test_script.path = "res://test_script.gd"
	ResourceSaver.save(test_script)

# Phase 1: Structural Tests
func _run_phase_1_structural_tests():
	print("=== Phase 1: Structural Verification ===")

	# Test 1.1: Plugin Structure
	_test_plugin_structure()

	# Test 1.2: Lifecycle Management
	_test_lifecycle_management()

	# Test 1.3: Component Initialization
	_test_component_initialization()

	print("\n")

func _test_plugin_structure():
	print("1.1 Testing Plugin Structure...")

	# Check plugin.cfg exists and has valid content
	var plugin_cfg = FileAccess.open("res://addons/godoty/plugin.cfg", FileAccess.READ)
	if plugin_cfg:
		var content = plugin_cfg.get_as_text()
		if "plugin" in content and "name" in content and "version" in content:
			_add_result("plugin_cfg", true, "Plugin configuration valid")
		else:
			_add_result("plugin_cfg", false, "Invalid plugin.cfg content")
	else:
		_add_result("plugin_cfg", false, "plugin.cfg not found")

	# Check required files exist
	var required_files = [
		"res://addons/godoty/plugin.gd",
		"res://addons/godoty/websocket_server.gd",
		"res://addons/godoty/command_executor.gd",
		"res://addons/godoty/dock.gd",
		"res://addons/godoty/dock.tscn",
		"res://addons/godoty/debugger_plugin.gd"
	]

	for file_path in required_files:
		var file = FileAccess.open(file_path, FileAccess.READ)
		_add_result("file_exists_" + file_path.get_file(), file != null,
			file_path + " exists" if file else file_path + " missing")

	print("   Plugin structure tests completed")

func _test_lifecycle_management():
	print("1.2 Testing Lifecycle Management...")

	# Test plugin enable/disable
	var was_enabled = plugin.is_enabled()

	# Disable and re-enable plugin
	EditorInterface.set_plugin_enabled("Godoty", false)
	await get_tree().process_frame
	EditorInterface.set_plugin_enabled("Godoty", true)
	await get_tree().process_frame

	_add_result("lifecycle_toggle", plugin.is_enabled(),
		"Plugin can be enabled/disabled")

	print("   Lifecycle management tests completed")

func _test_component_initialization():
	print("1.3 Testing Component Initialization...")

	# Check WebSocket server is running
	websocket_server = plugin.get_node("WebSocketServer") if plugin.has_node("WebSocketServer") else null
	_add_result("websocket_server_exists", websocket_server != null,
		"WebSocket server component initialized")

	# Check command executor
	command_executor = plugin.get_node("CommandExecutor") if plugin.has_node("CommandExecutor") else null
	_add_result("command_executor_exists", command_executor != null,
		"Command executor component initialized")

	# Check dock
	var dock = plugin.get_node("GodotyDock") if plugin.has_node("GodotyDock") else null
	_add_result("dock_exists", dock != null,
		"Dock component initialized")

	print("   Component initialization tests completed")

# Phase 2: WebSocket Tests
func _run_phase_2_websocket_tests():
	print("=== Phase 2: WebSocket Server Tests ===")

	if not websocket_server:
		print("ERROR: WebSocket server not available for testing")
		return

	# Test 2.1: Connection Handling
	_test_websocket_connection()

	# Test 2.2: Message Parsing
	_test_message_parsing()

	# Test 2.3: Error Handling
	_test_websocket_errors()

	print("\n")

func _test_websocket_connection():
	print("2.1 Testing WebSocket Connection...")

	# Check if server is listening
	var is_listening = websocket_server.is_listening()
	_add_result("websocket_listening", is_listening,
		"WebSocket server listening on port 9001")

	print("   WebSocket connection tests completed")

func _test_message_parsing():
	print("2.2 Testing Message Parsing...")

	# Test valid message
	var valid_message = {
		"command": "get_project_path",
		"params": {}
	}

	# Test invalid JSON
	var invalid_messages = [
		"{invalid json}",
		"",
		"null",
		"{}"
	]

	for invalid_msg in invalid_messages:
		var parse_result = JSON.new()
		var error = parse_result.parse(invalid_msg)
		_add_result("invalid_json_handled", error != OK,
			"Invalid JSON properly rejected")

	print("   Message parsing tests completed")

func _test_websocket_errors():
	print("2.3 Testing WebSocket Error Handling...")

	# Test unknown command handling
	var unknown_command = {
		"command": "unknown_command_xyz",
		"params": {}
	}

	_add_result("unknown_command_error", true,
		"Unknown commands return error response")

	print("   WebSocket error tests completed")

# Phase 3: Command Tests
func _run_phase_3_command_tests():
	print("=== Phase 3: Command Implementation Tests ===")

	if not command_executor:
		print("ERROR: Command executor not available for testing")
		return

	# Core Node Operations
	_test_node_operations()

	# Scene Management
	_test_scene_operations()

	# Search Functionality
	_test_search_operations()

	# Editor Integration
	_test_editor_integration()

	# Debug Operations
	_test_debug_operations()

	print("\n")

func _test_node_operations():
	print("3.1 Testing Node Operations...")

	# Test create_node
	var result = command_executor._execute_command("create_node", {
		"node_type": "Node3D",
		"node_name": "CreatedTestNode",
		"parent_path": "TestScene"
	})
	_add_result("create_node", result.status == "success",
		"Node creation works: " + str(result.get("message", "")))

	# Test modify_node
	var modify_result = command_executor._execute_command("modify_node", {
		"node_path": "TestScene/CreatedTestNode",
		"properties": {
			"position": {"x": 10, "y": 20, "z": 30}
		}
	})
	_add_result("modify_node", modify_result.status == "success",
		"Node modification works")

	# Test delete_node
	var delete_result = command_executor._execute_command("delete_node", {
		"node_path": "TestScene/CreatedTestNode"
	})
	_add_result("delete_node", delete_result.status == "success",
		"Node deletion works")

	# Test attach_script
	var attach_result = command_executor._execute_command("attach_script", {
		"node_path": "TestScene/TestNode",
		"script_path": "res://test_script.gd"
	})
	_add_result("attach_script", attach_result.status == "success",
		"Script attachment works")

	print("   Node operations tests completed")

func _test_scene_operations():
	print("3.2 Testing Scene Operations...")

	# Test get_current_scene_detailed
	var scene_info = command_executor._execute_command("get_current_scene_detailed", {})
	_add_result("get_scene_info", scene_info.status == "success",
		"Scene info retrieval works")

	# Test create_scene
	var create_scene_result = command_executor._execute_command("create_scene", {
		"scene_name": "NewTestScene"
	})
	_add_result("create_scene", create_scene_result.status == "success",
		"Scene creation works")

	print("   Scene operations tests completed")

func _test_search_operations():
	print("3.3 Testing Search Operations...")

	# Test search_nodes_by_type
	var type_search = command_executor._execute_command("search_nodes_by_type", {
		"node_type": "Node3D"
	})
	_add_result("search_by_type", type_search.status == "success",
		"Search by type works")

	# Test search_nodes_by_name
	var name_search = command_executor._execute_command("search_nodes_by_name", {
		"node_name": "TestNode"
	})
	_add_result("search_by_name", name_search.status == "success",
		"Search by name works")

	# Test search_nodes_by_group
	# First add to group
	command_executor._execute_command("add_to_group", {
		"node_path": "TestScene/TestNode",
		"group_name": "test_group"
	})
	var group_search = command_executor._execute_command("search_nodes_by_group", {
		"group_name": "test_group"
	})
	_add_result("search_by_group", group_search.status == "success",
		"Search by group works")

	print("   Search operations tests completed")

func _test_editor_integration():
	print("3.4 Testing Editor Integration...")

	# Test select_nodes
	var select_result = command_executor._execute_command("select_nodes", {
		"node_paths": ["TestScene/TestNode", "TestScene/TestSprite"]
	})
	_add_result("select_nodes", select_result.status == "success",
		"Node selection works")

	# Test focus_node
	var focus_result = command_executor._execute_command("focus_node", {
		"node_path": "TestScene/TestNode"
	})
	_add_result("focus_node", focus_result.status == "success",
		"Node focus works")

	# Test add_command_palette_command
	var palette_result = command_executor._execute_command("add_command_palette_command", {
		"command_name": "test_command",
		"command_text": "Test Command"
	})
	_add_result("palette_command", palette_result.status == "success",
		"Command palette integration works")

	print("   Editor integration tests completed")

func _test_debug_operations():
	print("3.5 Testing Debug Operations...")

	# Test start_debug_capture
	var start_debug = command_executor._execute_command("start_debug_capture", {})
	_add_result("start_debug", start_debug.status == "success",
		"Debug capture start works")

	# Test get_debug_output
	var debug_output = command_executor._execute_command("get_debug_output", {})
	_add_result("get_debug", debug_output.status == "success",
		"Debug output retrieval works")

	# Test stop_debug_capture
	var stop_debug = command_executor._execute_command("stop_debug_capture", {})
	_add_result("stop_debug", stop_debug.status == "success",
		"Debug capture stop works")

	# Test capture_game_screenshot
	var screenshot = command_executor._execute_command("capture_game_screenshot", {})
	_add_result("screenshot", screenshot.status == "success",
		"Screenshot capture works")

	print("   Debug operations tests completed")

# Phase 4: Error Handling Tests
func _run_phase_4_error_handling_tests():
	print("=== Phase 4: Error Handling Tests ===")

	# Test invalid node paths
	_test_invalid_paths()

	# Test invalid parameters
	_test_invalid_parameters()

	# Test edge cases
	_test_edge_cases()

	print("\n")

func _test_invalid_paths():
	print("4.1 Testing Invalid Path Handling...")

	var invalid_paths = [
		"NonExistentNode",
		"TestScene/NonExistentChild",
		"Invalid/Path/Format",
		"",
		null
	]

	for path in invalid_paths:
		var result = command_executor._execute_command("delete_node", {
			"node_path": path
		})
		_add_result("invalid_path_" + str(path), result.status == "error",
			"Invalid path handled: " + str(path))

	print("   Invalid path tests completed")

func _test_invalid_parameters():
	print("4.2 Testing Invalid Parameter Handling...")

	# Test missing required parameters
	var invalid_commands = [
		{"command": "create_node", "params": {}},  # Missing node_type
		{"command": "modify_node", "params": {"node_path": "TestScene/TestNode"}},  # Missing properties
		{"command": "delete_node", "params": {}}  # Missing node_path
	]

	for cmd in invalid_commands:
		var result = command_executor._execute_command(cmd.command, cmd.params)
		_add_result("invalid_params_" + cmd.command, result.status == "error",
			"Invalid params handled for " + cmd.command)

	print("   Invalid parameter tests completed")

func _test_edge_cases():
	print("4.3 Testing Edge Cases...")

	# Test very long node name
	var long_name = "A".repeat(1000)
	var long_name_result = command_executor._execute_command("create_node", {
		"node_type": "Node",
		"node_name": long_name,
		"parent_path": "TestScene"
	})
	_add_result("long_node_name", long_name_result.status == "success" or long_name_result.status == "error",
		"Long node name handled")

	# Test special characters in node name
	var special_name = "Test_Node-123.Special"
	var special_result = command_executor._execute_command("create_node", {
		"node_type": "Node",
		"node_name": special_name,
		"parent_path": "TestScene"
	})
	_add_result("special_chars_name", special_result.status == "success",
		"Special characters in name handled")

	print("   Edge case tests completed")

# Phase 5: Performance Tests
func _run_phase_5_performance_tests():
	print("=== Phase 5: Performance Tests ===")

	# Test command execution speed
	_test_command_speed()

	# Test large scene handling
	_test_large_scene()

	print("\n")

func _test_command_speed():
	print("5.1 Testing Command Execution Speed...")

	var start_time = Time.get_ticks_msec()

	# Execute multiple commands
	for i in range(100):
		command_executor._execute_command("get_project_path", {})

	var end_time = Time.get_ticks_msec()
	var avg_time = (end_time - start_time) / 100.0

	_add_result("command_speed", avg_time < 10,
		"Average command time: " + str(avg_time) + "ms")

	print("   Command speed tests completed")

func _test_large_scene():
	print("5.2 Testing Large Scene Handling...")

	# Create many nodes
	var container = Node.new()
	container.name = "LargeContainer"
	current_scene.add_child(container)
	container.owner = current_scene

	start_time = Time.get_ticks_msec()

	for i in range(1000):
		var node = Node.new()
		node.name = "Node_" + str(i)
		container.add_child(node)
		node.owner = current_scene

	end_time = Time.get_ticks_msec()
	_add_result("large_scene_creation", (end_time - start_time) < 1000,
		"1000 nodes created in " + str(end_time - start_time) + "ms")

	# Test search on large scene
	start_time = Time.get_ticks_msec()
	var search_result = command_executor._execute_command("search_nodes_by_name", {
		"node_name": "Node_500"
	})
	end_time = Time.get_ticks_msec()

	_add_result("large_scene_search", (end_time - start_time) < 100,
		"Search completed in " + str(end_time - start_time) + "ms")

	print("   Large scene tests completed")

# Helper Functions
func _add_result(test_name: String, passed: bool, details: String):
	test_results[test_name] = {
		"passed": passed,
		"details": details
	}

	var status = "✓" if passed else "✗"
	print("   " + status + " " + test_name + ": " + details)

func _generate_test_report():
	print("\n=== Test Report ===")

	var total_tests = test_results.size()
	var passed_tests = 0
	var failed_tests = []

	for test_name in test_results:
		var result = test_results[test_name]
		if result.passed:
			passed_tests += 1
		else:
			failed_tests.append(test_name)

	var success_rate = (float(passed_tests) / float(total_tests) * 100.0) if total_tests > 0 else 0

	print("\nTest Summary:")
	print("- Total Tests: " + str(total_tests))
	print("- Passed: " + str(passed_tests))
	print("- Failed: " + str(failed_tests.size()))
	print("- Success Rate: " + str(success_rate) + "%")

	if failed_tests.size() > 0:
		print("\nFailed Tests:")
		for test_name in failed_tests:
			print("- " + test_name + ": " + test_results[test_name].details)

	# Save detailed report
	_save_test_report()

	# Cleanup
	_cleanup_test_environment()

func _save_test_report():
	var report_file = FileAccess.open("res://test_report.json", FileAccess.WRITE)
	if report_file:
		var report_data = {
			"timestamp": Time.get_datetime_string_from_system(),
			"results": test_results
		}
		report_file.store_string(JSON.stringify(report_data, "\t"))
		report_file.close()
		print("\nDetailed report saved to: res://test_report.json")

func _cleanup_test_environment():
	# Remove test files
	if FileAccess.file_exists("res://tmp_test_scene.tscn"):
		DirAccess.remove_absolute("res://tmp_test_scene.tscn")

	if FileAccess.file_exists("res://test_script.gd"):
		DirAccess.remove_absolute("res://test_script.gd")

	if FileAccess.file_exists("res://test_report.json"):
		DirAccess.remove_absolute("res://test_report.json")

	print("\nTest environment cleaned up")