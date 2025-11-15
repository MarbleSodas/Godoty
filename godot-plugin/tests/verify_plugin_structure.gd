#!/usr/bin/env godot
# Plugin Structure Verification Script
# This script verifies the Godot plugin structure against best practices

extends SceneTree

func _init():
	print("=== Godot Plugin Structure Verification ===\n")

	# Run all verification checks
	_verify_plugin_structure()
	_verify_plugin_lifecycle()
	_verify_required_files()
	_verify_websocket_integration()
	_verify_command_protocol()

	print("\n=== Verification Complete ===")
	quit()

func _verify_plugin_structure():
	print("1. Plugin Structure Verification")
	print("-----------------------------")

	# Check plugin.cfg
	var plugin_cfg_path = "res://addons/godoty/plugin.cfg"
	if FileAccess.file_exists(plugin_cfg_path):
		var file = FileAccess.open(plugin_cfg_path, FileAccess.READ)
		if file:
			var content = file.get_as_text()
			print("✓ plugin.cfg exists")

			# Check required fields
			var required_fields = ["plugin", "name", "description", "author", "version"]
			for field in required_fields:
				if field in content:
					print("  ✓ Has field: " + field)
				else:
					print("  ✗ Missing field: " + field)
		else:
			print("✗ Could not read plugin.cfg")
	else:
		print("✗ plugin.cfg not found")

	# Check main plugin file
	if FileAccess.file_exists("res://addons/godoty/plugin.gd"):
		print("✓ plugin.gd exists")
		var plugin_script = load("res://addons/godoty/plugin.gd")
		if plugin_script:
			print("  ✓ Plugin script loads successfully")
			if plugin_script.can_instantiate():
				print("  ✓ Plugin script can be instantiated")
			else:
				print("  ✗ Plugin script cannot be instantiated")
	else:
		print("✗ plugin.gd not found")

	print("")

func _verify_plugin_lifecycle():
	print("2. Plugin Lifecycle Verification")
	print("--------------------------------")

	# Check if plugin follows EditorPlugin pattern
	var plugin_path = "res://addons/godoty/plugin.gd"
	if FileAccess.file_exists(plugin_path):
		var file = FileAccess.open(plugin_path, FileAccess.READ)
		var content = file.get_as_text()

		if "extends EditorPlugin" in content:
			print("✓ Extends EditorPlugin")
		else:
			print("✗ Does not extend EditorPlugin")

		if "_enter_tree" in content:
			print("✓ Has _enter_tree lifecycle method")
		else:
			print("✗ Missing _enter_tree method")

		if "_exit_tree" in content:
			print("✓ Has _exit_tree lifecycle method")
		else:
			print("✗ Missing _exit_tree method")

		if "has_main_screen" in content:
			print("✓ Has main screen support")
		else:
			print("  - No main screen support (optional)")

	print("")

func _verify_required_files():
	print("3. Required Files Verification")
	print("------------------------------")

	var required_files = {
		"res://addons/godoty/plugin.gd": "Main plugin file",
		"res://addons/godoty/plugin.cfg": "Plugin configuration",
		"res://addons/godoty/websocket_server.gd": "WebSocket server implementation",
		"res://addons/godoty/command_executor.gd": "Command executor",
		"res://addons/godoty/dock.gd": "Dock UI implementation",
		"res://addons/godoty/dock.tscn": "Dock UI scene",
		"res://addons/godoty/debugger_plugin.gd": "Debug plugin"
	}

	for file_path in required_files:
		if FileAccess.file_exists(file_path):
			print("✓ " + required_files[file_path] + " - " + file_path)
		else:
			print("✗ Missing: " + required_files[file_path] + " - " + file_path)

	print("")

func _verify_websocket_integration():
	print("4. WebSocket Integration Verification")
	print("-------------------------------------")

	# Check WebSocket server implementation
	var ws_path = "res://addons/godoty/websocket_server.gd"
	if FileAccess.file_exists(ws_path):
		var file = FileAccess.open(ws_path, FileAccess.READ)
		var content = file.get_as_text()

		if "extends Node" in content:
			print("✓ WebSocket server extends Node")

		if "WebSocketPeer" in content or "TCPServer" in content:
			print("✓ Uses WebSocket/TCPServer")

		if "9001" in content:
			print("✓ Port 9001 configured")
		else:
			print("  - Port 9001 not found (may use different port)")

	# Check WebSocket in Rust backend
	var rust_ws_path = "res://../src-tauri/src/websocket.rs"
	if FileAccess.file_exists(rust_ws_path):
		print("✓ Rust WebSocket client exists")
	else:
		print("  - Rust WebSocket client not found at expected location")

	print("")

func _verify_command_protocol():
	print("5. Command Protocol Verification")
	print("-------------------------------")

	# Check protocol definitions
	var protocol_path = "res://../protocol/commands.json"
	if FileAccess.file_exists(protocol_path):
		print("✓ Protocol definition exists")
		var file = FileAccess.open(protocol_path, FileAccess.READ)
		if file:
			var json = JSON.new()
			var parse_result = json.parse(file.get_as_text())
			if parse_result == OK:
				var data = json.data
				if data is Dictionary:
					var commands = data.get("commands", {})
					print("  ✓ Protocol defines " + str(commands.size()) + " commands")
				else:
					print("  ✗ Invalid protocol format")
			else:
				print("  ✗ Invalid JSON in protocol")
	else:
		print("✗ Protocol definition not found")

	# Check command executor matches protocol
	var executor_path = "res://addons/godoty/command_executor.gd"
	if FileAccess.file_exists(executor_path):
		var file = FileAccess.open(executor_path, FileAccess.READ)
		var content = file.get_as_text()

		# Count implemented commands
		var command_count = 0
		var lines = content.split("\n")
		for line in lines:
			if line.strip_edges().begins_with('\"') and line.contains('":'):
				command_count += 1

		print("✓ Command executor implements " + str(command_count) + " command handlers")

	print("")