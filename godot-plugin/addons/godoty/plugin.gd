@tool
extends EditorPlugin

var websocket_server: Node
var command_executor: Node
var dock: Control
var debugger_plugin: EditorDebuggerPlugin
var inspector_plugin: Node
const WEBSOCKET_PORT = 9001

func _enter_tree():
	print("Godoty AI Assistant: Initializing...")


	# Create WebSocket server
	websocket_server = preload("res://addons/godoty/websocket_server.gd").new()
	websocket_server.port = WEBSOCKET_PORT
	add_child(websocket_server)

	# Create command executor
	command_executor = preload("res://addons/godoty/command_executor.gd").new()
	command_executor.editor_plugin = self
	add_child(command_executor)

	# Create inspector/visual capture helper
	var InspectorPlugin := preload("res://addons/godoty/inspector_plugin.gd")
	inspector_plugin = InspectorPlugin.new()
	add_child(inspector_plugin)
	if inspector_plugin and inspector_plugin.has_method("set_editor_plugin"):
		inspector_plugin.call("set_editor_plugin", self)
	# Wire into command executor
	if command_executor:
		command_executor.inspector_plugin = inspector_plugin


	# Create and register debugger plugin for capturing output
	var DebuggerPlugin = preload("res://addons/godoty/debugger_plugin.gd")
	debugger_plugin = DebuggerPlugin.new()
	add_debugger_plugin(debugger_plugin)
	command_executor.debugger_plugin = debugger_plugin
	# Forward debug logs to dock
	if debugger_plugin:
		debugger_plugin.log_message.connect(_on_debug_message)

	# Connect signals
	websocket_server.command_received.connect(_on_command_received)

	# Create dock UI
	dock = preload("res://addons/godoty/dock.tscn").instantiate()
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, dock)
	dock.status_changed.connect(_on_status_changed)

	# Start server
	websocket_server.start_server()
	_update_dock_status("Server started on port %d" % WEBSOCKET_PORT)
	print("Godoty AI Assistant: Ready!")




func _exit_tree():
	print("Godoty AI Assistant: Shutting down...")


	# Stop server
	if websocket_server:
		websocket_server.stop_server()
		websocket_server.queue_free()

	# Unregister debugger plugin
	if debugger_plugin:
		remove_debugger_plugin(debugger_plugin)
		debugger_plugin = null

	# Clean up
	if inspector_plugin:
		inspector_plugin.queue_free()

	if command_executor:
		command_executor.queue_free()

	# Remove dock
	if dock:
		remove_control_from_docks(dock)

		dock.queue_free()
	print("Godoty AI Assistant: Stopped")




func _on_command_received(command: Dictionary):
	print("Godoty: Received command: ", command)

	_update_dock_status("Executing: %s" % command.get("action", "unknown"))

	# Execute command (await if it's async)
	var result = await command_executor.execute_command(command)

	# Send response back
	websocket_server.send_response(result)

	# Update dock
	if result.status == "success":
		_update_dock_status("✓ %s" % result.get("message", "Success"))
	else:
		_update_dock_status("✗ %s" % result.get("message", "Error"))

func _on_status_changed(status: String):
	print("Godoty Status: ", status)

func _on_debug_message(entry: Dictionary):
	var msg := "[Dbg] %s — %s" % [entry.get("message", ""), str(entry.get("data", []))]
	_update_dock_status(msg)

func _update_dock_status(message: String):
	if dock and dock.has_method("update_status"):
		dock.update_status(message)

func get_editor_interface() -> EditorInterface:
	return super.get_editor_interface()

func get_undo_redo() -> EditorUndoRedoManager:
	return super.get_undo_redo()

