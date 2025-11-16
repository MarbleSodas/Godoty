@tool
extends EditorPlugin

var websocket_server: Node
var command_executor: Node
var dock: Control
var debugger_plugin: EditorDebuggerPlugin
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
	websocket_server.client_connected.connect(_on_client_connected)

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

func _on_client_connected(ws: WebSocketPeer):
	print("Godoty: Client connected; will send project path when socket is open...")
	# Prepare project path payload
	var project_path := ProjectSettings.globalize_path("res://")
	var welcome_message := {
		"type": "project_info",
		"status": "success",
		"data": {"project_path": project_path}
	}
	var json_string := JSON.stringify(welcome_message)
	# Try immediate send if the socket is already open
	if ws.get_ready_state() == WebSocketPeer.STATE_OPEN:
		var err := ws.send_text(json_string)
		if err != OK:
			push_error("Godoty: Failed to send project path: %s" % error_string(err))
		else:
			print("Godoty: Sent project path to client: ", project_path)
		return
	# Otherwise, retry until the socket opens (or times out)
	var timer := Timer.new()
	timer.wait_time = 0.1
	timer.one_shot = false
	add_child(timer)
	var attempts := 0
	timer.timeout.connect(func():
		attempts += 1
		var state := ws.get_ready_state()
		if state == WebSocketPeer.STATE_OPEN:
			var err2 := ws.send_text(json_string)
			if err2 != OK:
				push_error("Godoty: Failed to send project path on retry: %s" % error_string(err2))
			else:
				print("Godoty: Sent project path to client: ", project_path)
			timer.stop()
			timer.queue_free()
		elif state == WebSocketPeer.STATE_CLOSED or attempts >= 50:
			print("Godoty: WebSocket closed or timed out before sending project path")
			timer.stop()
			timer.queue_free()
	)
	timer.start()

func _update_dock_status(message: String):
	if dock and dock.has_method("update_status"):
		dock.update_status(message)

func get_editor_interface() -> EditorInterface:
	return super.get_editor_interface()

func get_undo_redo() -> EditorUndoRedoManager:
	return super.get_undo_redo()

