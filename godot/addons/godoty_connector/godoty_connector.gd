@tool
extends EditorPlugin
## Godoty Connector Plugin (Headless)
## 
## Connects the Godot Editor to the local Godoty brain sidecar.
## Handles bidirectional JSON-RPC 2.0 communication over WebSocket.
## 
## UI and HITL confirmations are handled by the external Tauri desktop app.

const PROTOCOL_VERSION := "0.2"
const DEFAULT_URL := "ws://127.0.0.1:8000/ws/godot"

enum JsonRpcErrorCode {
	PARSE_ERROR = -32700,
	INVALID_REQUEST = -32600,
	METHOD_NOT_FOUND = -32601,
	INVALID_PARAMS = -32602,
	INTERNAL_ERROR = -32603,
}

var _socket: WebSocketPeer
var _next_id: int = 1
var _pending_requests: Dictionary = {}  # id -> callback
var _connected: bool = false
var _session_id: String = ""

# Signals for external status monitoring
signal connection_state_changed(connected: bool)


func _enter_tree() -> void:
	print("[Godoty] Plugin initialized")
	_setup_socket()
	_enable_auto_reload()


func _exit_tree() -> void:
	print("[Godoty] Plugin disabled")
	_socket = null


func _setup_socket() -> void:
	_socket = WebSocketPeer.new()
	var url := _get_server_url()
	var err := _socket.connect_to_url(url)
	if err != OK:
		push_error("[Godoty] Failed to connect: %s" % err)


func _get_server_url() -> String:
	# Allow override via project setting
	if ProjectSettings.has_setting("godoty/server_url"):
		return ProjectSettings.get_setting("godoty/server_url")
	return DEFAULT_URL


func _enable_auto_reload() -> void:
	## Enable auto-reload for external script changes (required for AI edits)
	var settings := EditorInterface.get_editor_settings()
	settings.set_setting("text_editor/behavior/files/auto_reload_scripts_on_external_change", true)


var _retry_interval: float = 3.0
var _time_since_closed: float = 0.0


func _process(delta: float) -> void:
	if _socket == null:
		return

	_socket.poll()
	var state := _socket.get_ready_state()

	match state:
		WebSocketPeer.STATE_OPEN:
			_time_since_closed = 0.0
			if not _connected:
				_connected = true
				_send_hello()
				connection_state_changed.emit(true)
				print("[Godoty] Connected to brain")
			_process_packets()
			
		WebSocketPeer.STATE_CLOSED:
			if _connected:
				_connected = false
				connection_state_changed.emit(false)
				print("[Godoty] Disconnected")
			
			# Auto-reconnect logic
			_time_since_closed += delta
			if _time_since_closed >= _retry_interval:
				_time_since_closed = 0.0
				_setup_socket()

		WebSocketPeer.STATE_CONNECTING:
			_time_since_closed = 0.0
			pass  # Still connecting


func _process_packets() -> void:
	while _socket.get_available_packet_count() > 0:
		var packet := _socket.get_packet()
		var text := packet.get_string_from_utf8()
		_handle_message(text)


func _handle_message(text: String) -> void:
	var data: Variant = JSON.parse_string(text)
	if data == null or not data is Dictionary:
		push_warning("[Godoty] Invalid JSON received: %s" % text)
		_send_error(null, JsonRpcErrorCode.PARSE_ERROR, "Parse error: Invalid JSON")
		return

	# Check if this is a response to our request
	if data.has("id") and data.has("result"):
		var id: int = data["id"]
		if _pending_requests.has(id):
			var callback: Callable = _pending_requests[id]
			_pending_requests.erase(id)
			callback.call(data["result"])
		return

	# Check if this is an error
	if data.has("id") and data.has("error"):
		var id: int = data["id"]
		if _pending_requests.has(id):
			_pending_requests.erase(id)
		push_error("[Godoty] Error: %s" % JSON.stringify(data["error"]))
		return

	# Handle incoming requests from brain
	if data.has("method"):
		_handle_brain_request(data)


func _handle_brain_request(data: Dictionary) -> void:
	var method: String = data.get("method", "")
	var params: Dictionary = data.get("params", {})
	var request_id: Variant = data.get("id")

	match method:
		# Perception handlers
		"take_screenshot":
			_handle_take_screenshot(params, request_id)
		"get_scene_tree":
			_handle_get_scene_tree(params, request_id)
		"get_open_script":
			_handle_get_open_script(params, request_id)
		"get_project_settings":
			_handle_get_project_settings(params, request_id)
		# File operations (no confirmation - handled by Tauri)
		"read_file":
			_handle_read_file(params, request_id)
		"write_file":
			_handle_write_file(params, request_id)
		"set_project_setting":
			_handle_set_project_setting(params, request_id)
		"create_node":
			_handle_create_node(params, request_id)
		"delete_node":
			_handle_delete_node(params, request_id)
		_:
			_send_error(request_id, JsonRpcErrorCode.METHOD_NOT_FOUND, "Method not found: %s" % method)


# ============================================================================
# Outgoing Messages
# ============================================================================


func _send_hello() -> void:
	var msg := {
		"jsonrpc": "2.0",
		"method": "hello",
		"params": {
			"client": "godot",
			"protocol_version": PROTOCOL_VERSION,
			"project_name": ProjectSettings.get_setting("application/config/name", "Unknown"),
			"project_path": ProjectSettings.globalize_path("res://"),
			"godot_version": Engine.get_version_info().get("string", "4.x"),
		},
		"id": _next_id,
	}
	_next_id += 1
	_socket.send_text(JSON.stringify(msg))


func _send_response(request_id: Variant, result: Variant) -> void:
	if request_id == null:
		return
	var msg := {
		"jsonrpc": "2.0",
		"result": result,
		"id": request_id,
	}
	_socket.send_text(JSON.stringify(msg))


func _send_error(request_id: Variant, code: int, message: String) -> void:
	var msg := {
		"jsonrpc": "2.0",
		"error": {"code": code, "message": message},
		"id": request_id,
	}
	_socket.send_text(JSON.stringify(msg))


func _send_event(method: String, params: Dictionary) -> void:
	var msg := {
		"jsonrpc": "2.0",
		"method": method,
		"params": params,
	}
	_socket.send_text(JSON.stringify(msg))


# ============================================================================
# Perception Handlers
# ============================================================================


func _handle_take_screenshot(params: Dictionary, request_id: Variant) -> void:
	var viewport_type: String = params.get("viewport", "3d")
	var max_width: int = params.get("max_width", 1024)
	
	var img: Image
	var editor_interface = EditorInterface
	
	match viewport_type:
		"3d":
			# get_editor_viewport_3d() is only available in Godot 4.2+
			if editor_interface.has_method("get_editor_viewport_3d"):
				var viewport = editor_interface.call("get_editor_viewport_3d", 0)
				if viewport:
					img = viewport.get_texture().get_image()
			else:
				# Fallback: use main editor viewport
				var viewport = EditorInterface.get_base_control().get_viewport()
				if viewport:
					img = viewport.get_texture().get_image()
		"2d":
			# get_editor_viewport_2d() is only available in Godot 4.2+
			if editor_interface.has_method("get_editor_viewport_2d"):
				var viewport = editor_interface.call("get_editor_viewport_2d", 0)
				if viewport:
					img = viewport.get_texture().get_image()
			else:
				# Fallback: use main editor viewport
				var viewport = EditorInterface.get_base_control().get_viewport()
				if viewport:
					img = viewport.get_texture().get_image()
		"editor":
			# Capture the main editor viewport
			var viewport = EditorInterface.get_base_control().get_viewport()
			if viewport:
				img = viewport.get_texture().get_image()
	
	if img == null:
		_send_response(request_id, {"error": "Failed to capture viewport"})
		return
	
	# Downscale if needed
	if img.get_width() > max_width:
		var ratio := float(max_width) / img.get_width()
		var new_height := int(img.get_height() * ratio)
		img.resize(max_width, new_height, Image.INTERPOLATE_LANCZOS)
	
	# Convert to JPEG and base64
	var buffer := img.save_jpg_to_buffer(0.85)
	var base64 := Marshalls.raw_to_base64(buffer)
	
	_send_response(request_id, {
		"image": base64,
		"width": img.get_width(),
		"height": img.get_height(),
		"viewport": viewport_type,
	})


func _handle_get_scene_tree(params: Dictionary, request_id: Variant) -> void:
	var max_depth: int = params.get("max_depth", 10)
	var include_properties: bool = params.get("include_properties", false)
	
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		_send_response(request_id, {"tree": null, "scene_path": null})
		return
	
	var tree := _serialize_node(root, 0, max_depth, include_properties)
	var scene_path := root.scene_file_path
	
	_send_response(request_id, {
		"tree": tree,
		"scene_path": scene_path,
	})


func _serialize_node(node: Node, depth: int, max_depth: int, include_properties: bool) -> Dictionary:
	var data := {
		"name": node.name,
		"type": node.get_class(),
		"path": str(node.get_path()),
		"children": [],
	}
	
	if include_properties:
		data["properties"] = _get_node_properties(node)
	
	if depth < max_depth:
		for child in node.get_children():
			data["children"].append(_serialize_node(child, depth + 1, max_depth, include_properties))
	
	return data


func _get_node_properties(node: Node) -> Dictionary:
	var props := {}
	# Get commonly useful properties
	if node is Node2D:
		props["position"] = {"x": node.position.x, "y": node.position.y}
		props["rotation"] = node.rotation
		props["scale"] = {"x": node.scale.x, "y": node.scale.y}
	elif node is Node3D:
		props["position"] = {"x": node.position.x, "y": node.position.y, "z": node.position.z}
		props["rotation"] = {"x": node.rotation.x, "y": node.rotation.y, "z": node.rotation.z}
		props["scale"] = {"x": node.scale.x, "y": node.scale.y, "z": node.scale.z}
	return props


func _handle_get_open_script(params: Dictionary, request_id: Variant) -> void:
	var script_editor := EditorInterface.get_script_editor()
	var current_script := script_editor.get_current_script()
	
	if current_script == null:
		_send_response(request_id, {"error": "No script currently open"})
		return
	
	var source := current_script.source_code
	var path := current_script.resource_path
	var lines := source.split("\n")
	
	_send_response(request_id, {
		"path": path,
		"content": source,
		"line_count": lines.size(),
	})


func _handle_get_project_settings(params: Dictionary, request_id: Variant) -> void:
	var setting_path: Variant = params.get("path")
	
	if setting_path != null and setting_path is String:
		var value := ProjectSettings.get_setting(setting_path)
		_send_response(request_id, {"settings": {setting_path: value}})
	else:
		# Return common settings
		var settings := {
			"application/config/name": ProjectSettings.get_setting("application/config/name"),
			"display/window/size/viewport_width": ProjectSettings.get_setting("display/window/size/viewport_width"),
			"display/window/size/viewport_height": ProjectSettings.get_setting("display/window/size/viewport_height"),
			"rendering/renderer/rendering_method": ProjectSettings.get_setting("rendering/renderer/rendering_method"),
		}
		_send_response(request_id, {"settings": settings})


# ============================================================================
# Actuation Handlers (No local confirmation - Tauri handles HITL)
# ============================================================================


func _handle_read_file(params: Dictionary, request_id: Variant) -> void:
	var path: String = params.get("path", "")
	if path.is_empty():
		_send_response(request_id, {"error": "Path is required"})
		return
	
	# Ensure path starts with res://
	if not path.begins_with("res://"):
		path = "res://" + path
	
	if not FileAccess.file_exists(path):
		_send_response(request_id, {"exists": false, "path": path, "content": ""})
		return
	
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		_send_response(request_id, {"error": "Failed to open file: %s" % FileAccess.get_open_error()})
		return
	
	var content := file.get_as_text()
	file.close()
	
	_send_response(request_id, {
		"path": path,
		"content": content,
		"exists": true,
	})


func _handle_write_file(params: Dictionary, request_id: Variant) -> void:
	var path: String = params.get("path", "")
	var content: String = params.get("content", "")
	var create_backup: bool = params.get("create_backup", true)
	
	if path.is_empty():
		_send_response(request_id, {"success": false, "message": "Path is required"})
		return
	
	if not path.begins_with("res://"):
		path = "res://" + path
	
	# Write directly - HITL confirmation is handled by Tauri before this is called
	_do_write_file(path, content, create_backup, request_id)


func _do_write_file(path: String, content: String, create_backup: bool, request_id: Variant) -> void:
	var backup_path: Variant = null
	
	# Create backup if requested and file exists
	if create_backup and FileAccess.file_exists(path):
		backup_path = path + ".bak"
		var original := FileAccess.open(path, FileAccess.READ)
		if original:
			var backup := FileAccess.open(backup_path, FileAccess.WRITE)
			if backup:
				backup.store_string(original.get_as_text())
				backup.close()
			original.close()
	
	# Write the new content
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		_send_response(request_id, {"success": false, "message": "Failed to open file for writing"})
		return
	
	file.store_string(content)
	file.close()
	
	# Force filesystem rescan
	EditorInterface.get_resource_filesystem().scan()
	
	_send_response(request_id, {
		"success": true,
		"message": "File written successfully",
		"backup_path": backup_path,
	})


func _handle_set_project_setting(params: Dictionary, request_id: Variant) -> void:
	var path: String = params.get("path", "")
	var value: Variant = params.get("value")
	
	if path.is_empty():
		_send_response(request_id, {"success": false, "message": "Path is required"})
		return
	
	# Write directly - HITL confirmation is handled by Tauri
	ProjectSettings.set_setting(path, value)
	ProjectSettings.save()
	_send_response(request_id, {"success": true, "message": "Setting updated"})


func _handle_create_node(params: Dictionary, request_id: Variant) -> void:
	var parent_path: String = params.get("parent_path", "")
	var node_name: String = params.get("node_name", "")
	var node_type: String = params.get("node_type", "")
	
	if node_name.is_empty() or node_type.is_empty():
		_send_response(request_id, {"success": false, "message": "node_name and node_type required"})
		return
	
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		_send_response(request_id, {"success": false, "message": "No scene open"})
		return
	
	var parent: Node = root if parent_path.is_empty() else root.get_node_or_null(parent_path)
	if parent == null:
		_send_response(request_id, {"success": false, "message": "Parent node not found"})
		return
	
	# Create the new node
	var new_node: Node = ClassDB.instantiate(node_type)
	if new_node == null:
		_send_response(request_id, {"success": false, "message": "Failed to create node of type: %s" % node_type})
		return
	
	new_node.name = node_name
	parent.add_child(new_node)
	new_node.owner = root
	
	_send_response(request_id, {
		"success": true,
		"node_path": str(new_node.get_path()),
		"message": "Node created",
	})


func _handle_delete_node(params: Dictionary, request_id: Variant) -> void:
	var node_path: String = params.get("node_path", "")
	
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		_send_response(request_id, {"success": false, "message": "No scene open"})
		return
	
	var node: Node = root.get_node_or_null(node_path)
	if node == null:
		_send_response(request_id, {"success": false, "message": "Node not found"})
		return
	
	if node == root:
		_send_response(request_id, {"success": false, "message": "Cannot delete root node"})
		return
	
	node.queue_free()
	_send_response(request_id, {"success": true, "message": "Node deleted"})
