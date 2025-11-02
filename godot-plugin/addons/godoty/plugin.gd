@tool
extends EditorPlugin

var websocket_server: Node
var command_executor: Node
var dock: Control

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
	
	# Clean up
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
	
	# Execute command
	var result = command_executor.execute_command(command)
	
	# Send response back
	websocket_server.send_response(result)
	
	# Update dock
	if result.status == "success":
		_update_dock_status("✓ %s" % result.get("message", "Success"))
	else:
		_update_dock_status("✗ %s" % result.get("message", "Error"))

func _on_status_changed(status: String):
	print("Godoty Status: ", status)

func _update_dock_status(message: String):
	if dock and dock.has_method("update_status"):
		dock.update_status(message)

func get_editor_interface() -> EditorInterface:
	return get_editor_interface()

func get_undo_redo() -> EditorUndoRedoManager:
	return get_undo_redo()

