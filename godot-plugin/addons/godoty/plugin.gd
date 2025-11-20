@tool
extends EditorPlugin

const WEBSOCKET_PORT = 9001
const DOCK_SCENE = preload("res://addons/godoty/dock.tscn")

var websocket_server
var command_executor
var dock: Control
var debugger_plugin: EditorDebuggerPlugin

func _enter_tree() -> void:
	print("Godoty AI Assistant: Initializing...")

	_initialize_components()
	_connect_signals()
	_add_dock()
	websocket_server.start_server()

	_update_status("Server started on port %d" % WEBSOCKET_PORT)
	print("Godoty AI Assistant: Ready!")




func _exit_tree() -> void:
	print("Godoty AI Assistant: Shutting down...")
	_cleanup_components()
	print("Godoty AI Assistant: Stopped")

# Private methods
func _initialize_components() -> void:
	websocket_server = preload("res://addons/godoty/websocket_server.gd").new()
	websocket_server.port = WEBSOCKET_PORT
	add_child(websocket_server)

	command_executor = preload("res://addons/godoty/command_executor.gd").new()
	command_executor.editor_plugin = self
	add_child(command_executor)

	debugger_plugin = preload("res://addons/godoty/debugger_plugin.gd").new()
	add_debugger_plugin(debugger_plugin)
	command_executor.debugger_plugin = debugger_plugin

func _connect_signals() -> void:
	websocket_server.command_received.connect(_on_command_received)
	websocket_server.client_connected.connect(_on_client_connected)

	if debugger_plugin:
		debugger_plugin.log_message.connect(_on_debug_message)

func _add_dock() -> void:
	dock = DOCK_SCENE.instantiate()
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, dock)
	if dock.has_signal("status_changed"):
		dock.status_changed.connect(_on_status_changed)

func _cleanup_components() -> void:
	if websocket_server:
		websocket_server.stop_server()
		websocket_server.queue_free()

	if debugger_plugin:
		remove_debugger_plugin(debugger_plugin)

	if command_executor:
		command_executor.queue_free()

	if dock:
		remove_control_from_docks(dock)
		dock.queue_free()




# Signal handlers
func _on_command_received(command: Dictionary) -> void:
	print("Godoty: Received command: ", command)
	_update_status("Executing: %s" % command.get("action", "unknown"))

	var result = await command_executor.execute_command(command)
	
	# Ensure response has the correct type and matches the command ID
	result["type"] = "command_response"
	result["id"] = command.get("id")
	
	websocket_server.send_response(result)

	var status_symbol := "✓" if result.get("status") == "success" else "✗"
	_update_status("%s %s" % [status_symbol, result.get("message", "Done")])

func _on_status_changed(status: String) -> void:
	print("Godoty Status: ", status)

func _on_debug_message(entry: Dictionary) -> void:
	var msg := "[Dbg] %s — %s" % [entry.get("message", ""), str(entry.get("data", []))]
	_update_status(msg)

func _on_client_connected(ws: WebSocketPeer) -> void:
	print("Godoty: Client connected")
	_send_project_info(ws)

# Helper methods
func _update_status(message: String) -> void:
	if dock and dock.has_method("update_status"):
		dock.update_status(message)

func _send_project_info(ws: WebSocketPeer) -> void:
	var project_path := ProjectSettings.globalize_path("res://")

	# Get Godot version info
	var version_info := Engine.get_version_info()
	var godot_version := "%d.%d.%d" % [version_info.major, version_info.minor, version_info.patch]
	if version_info.status:
		godot_version += "-%s" % version_info.status

	# Get project settings
	var project_settings := {
		"name": ProjectSettings.get_setting("application/config/name", "Unknown"),
		"main_scene": ProjectSettings.get_setting("application/run/main_scene", ""),
		"viewport_width": ProjectSettings.get_setting("display/window/size/viewport_width", 1920),
		"viewport_height": ProjectSettings.get_setting("display/window/size/viewport_height", 1080),
		"renderer": ProjectSettings.get_setting("rendering/renderer/rendering_method", "forward_plus")
	}

	var message := {
		"type": "project_info",
		"status": "success",
		"data": {
			"project_path": project_path,
			"godot_version": godot_version,
			"plugin_version": "0.1.0",
			"project_settings": project_settings
		}
	}

	var json_string := JSON.stringify(message)

	# Send immediately if ready, otherwise retry
	if ws.get_ready_state() == WebSocketPeer.STATE_OPEN:
		_send_websocket_text(ws, json_string, project_path)
	else:
		_retry_websocket_send(ws, json_string, project_path)

func _send_websocket_text(ws: WebSocketPeer, json_string: String, project_path: String) -> void:
	var err := ws.send_text(json_string)
	if err == OK:
		print("Godoty: Sent project path: ", project_path)
	else:
		push_error("Godoty: Failed to send project path: %s" % error_string(err))

func _retry_websocket_send(ws: WebSocketPeer, json_string: String, project_path: String) -> void:
	var timer := Timer.new()
	timer.wait_time = 0.1
	timer.one_shot = false
	add_child(timer)

	var attempts := 0
	timer.timeout.connect(func():
		attempts += 1
		var state := ws.get_ready_state()

		if state == WebSocketPeer.STATE_OPEN:
			_send_websocket_text(ws, json_string, project_path)
			timer.queue_free()
		elif state == WebSocketPeer.STATE_CLOSED or attempts >= 50:
			print("Godoty: WebSocket closed before sending project info")
			timer.queue_free()
	)
	timer.start()

