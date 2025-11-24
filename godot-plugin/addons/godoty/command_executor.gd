extends Node

var editor_plugin: EditorPlugin
var debugger_plugin: EditorDebuggerPlugin

func execute_command(command: Dictionary):
	var action = command.get("action", "")

	match action:
		"create_node":
			return _create_node(command)
		"delete_node":
			return _delete_node(command)
		"modify_node":
			return _modify_node(command)
		"attach_script":
			return _attach_script(command)
		"create_scene":
			return await _create_scene(command)
		"get_scene_info":
			return _get_scene_info(command)
		"inspect_scene_file":
			return _inspect_scene_file(command)
		"get_current_scene_detailed":
			return _get_current_scene_detailed(command)
		# Debug screenshot command
		"capture_game_screenshot":
			return await _capture_game_screenshot(command)
		# New editor integration commands (EditorInterface / CommandPalette)
		"select_nodes":
			return _select_nodes(command)
		"focus_node":
			return _focus_node(command)
		"play":
			return _play(command)
		"open_scene":
			return await _open_scene(command)
		"add_command_palette_command":
			return _add_command_palette_command(command)
		# Search commands
		"search_nodes_by_type":
			return _search_nodes_by_type(command)
		"search_nodes_by_name":
			return _search_nodes_by_name(command)
		"search_nodes_by_group":
			return _search_nodes_by_group(command)
		"search_nodes_by_script":
			return _search_nodes_by_script(command)
		# Structure editing commands
		"duplicate_node":
			return _duplicate_node(command)
		"reparent_node":
			return _reparent_node(command)
		"rename_node":
			return _rename_node(command)
		"add_to_group":
			return _add_to_group(command)
		"remove_from_group":
			return _remove_from_group(command)
		"start_debug_capture":
			return _start_debug_capture(command)
		"stop_debug_capture":
			return _stop_debug_capture(command)
		"clear_debug_output":
			return _clear_debug_output(command)
		"get_debug_output":
			return _get_debug_output(command)
		"get_project_path":
			return _get_project_path(command)
		"get_project_info":
			return _get_project_info(command)
		# Visual context commands
		"capture_visual_context":
			return await _capture_visual_context(command)
		"get_visual_snapshot":
			return await _get_visual_snapshot(command)
		"enable_auto_visual_capture":
			return _enable_auto_visual_capture(command)
		"disable_auto_visual_capture":
			return _disable_auto_visual_capture(command)
		"save_current_scene":
			return _save_current_scene(command)
		"stop_playing":
			return _stop_playing(command)
		"create_resource":
			return _create_resource(command)
		"delete_resource":
			return _delete_resource(command)
		"create_and_attach_script":
			return _create_and_attach_script(command)
		"create_node_with_script":
			return _create_node_with_script(command)
		_:
			return {
				"status": "error",
				"message": "Unknown action: %s" % action
			}

# Helper function to resolve node paths smartly
func _resolve_node(path_str: String) -> Node:
	if path_str.is_empty():
		return null

	var editor_interface = editor_plugin.get_editor_interface()
	var edited_scene = editor_interface.get_edited_scene_root()

	if not edited_scene:
		return null

	# Case 1: Special markers for root
	if path_str == "/" or path_str == ".":
		return edited_scene

	# Case 2: Try as relative path first (standard behavior)
	var node = edited_scene.get_node_or_null(path_str)
	if node:
		return node

	# Case 3: Try resolving if path starts with scene root name (user convenience)
	var root_name := str(edited_scene.name)
	if path_str == root_name:
		return edited_scene
	elif path_str.begins_with(root_name + "/"):
		var stripped := path_str.substr(root_name.length() + 1)
		node = edited_scene.get_node_or_null(stripped)
		if node:
			return node

	# Case 4: Try absolute path but ensure it's inside edited scene
	if path_str.begins_with("/root/"):
		node = editor_plugin.get_tree().get_root().get_node_or_null(path_str)
		if node and (node == edited_scene or edited_scene.is_ancestor_of(node)):
			return node
		
	return null

func _create_node(command: Dictionary) -> Dictionary:
	var node_type = command.get("type", "")
	var node_name = command.get("name", "")
	var parent_path = command.get("parent", null)
	var properties = command.get("properties", {})

	if node_type.is_empty():
		return {"status": "error", "message": "Node type is required"}
	if node_name.is_empty():
		return {"status": "error", "message": "Node name is required"}

	# Get editor interface
	var editor_interface = editor_plugin.get_editor_interface()
	var edited_scene: Node = editor_interface.get_edited_scene_root()

	if not edited_scene:
		return {
			"status": "error",
			"message": "No scene is currently open. Please create a scene first using create_scene command.",
			"suggestion": "Use create_scene before create_node"
		}

	# Create the node
	var new_node: Node = _instantiate_node_by_type(node_type)
	if not new_node:
		return {"status": "error", "message": "Failed to create node of type: %s" % node_type}

	new_node.name = node_name

	# Resolve parent node
	var parent_node: Node = edited_scene
	if parent_path and not String(parent_path).is_empty():
		var resolved = _resolve_node(str(parent_path))
		if resolved:
			parent_node = resolved
		else:
			new_node.free()
			return {"status": "error", "message": "Parent node not found: %s" % parent_path, "suggestion": "Check parent path"}

	# Determine correct owner for saving (match parent's owner, fallback to scene root)
	var owner_for_save: Node = parent_node.owner if parent_node.owner else edited_scene

	# Apply via Undo/Redo so it integrates with the editor and can be undone
	var ur: EditorUndoRedoManager = editor_plugin.get_undo_redo()
	ur.create_action("Create Node: %s" % node_name)
	ur.add_do_method(parent_node, "add_child", new_node)
	ur.add_do_method(new_node, "set_owner", owner_for_save)
	# Apply properties through undo/redo (only those that exist)
	for prop_name in properties:
		var prop_exists := false
		for prop in new_node.get_property_list():
			if prop["name"] == prop_name:
				prop_exists = true
				break
		if prop_exists:
			ur.add_do_property(new_node, prop_name, properties[prop_name])
		else:
			push_warning("Property not found on node: %s" % prop_name)
	ur.add_undo_method(parent_node, "remove_child", new_node)
	ur.add_undo_method(new_node, "set_owner", null)
	ur.commit_action()

	# Mark scene as modified
	editor_interface.mark_scene_as_unsaved()

	return {
		"status": "success",
		"message": "Created node: %s" % node_name,
		"data": {
			"node_path": str(edited_scene.get_path_to(new_node))
		}
	}

func _delete_node(command: Dictionary) -> Dictionary:
	var node_path = command.get("path", "")

	if node_path.is_empty():
		return {"status": "error", "message": "Node path is required"}

	var editor_interface = editor_plugin.get_editor_interface()
	var edited_scene = editor_interface.get_edited_scene_root()

	if not edited_scene:
		return {
			"status": "error",
			"message": "No scene is currently open. Please create or open a scene first.",
			"suggestion": "Use create_scene or open an existing scene"
		}

	var node: Node = _resolve_node(node_path)
	if not node:
		return {"status": "error", "message": "Node not found: %s" % node_path}

	if node == edited_scene:
		return {"status": "error", "message": "Cannot delete scene root"}

	var parent: Node = node.get_parent()
	if parent == null:
		return {"status": "error", "message": "Node has no parent (can't delete rootless node)"}
	var index: int = parent.get_child_index(node)
	var prev_owner := node.owner

	var ur: EditorUndoRedoManager = editor_plugin.get_undo_redo()
	ur.create_action("Delete Node: %s" % node_path)
	ur.add_do_method(parent, "remove_child", node)
	# Undo: re-add at same index and restore owner
	ur.add_undo_method(parent, "add_child", node)
	ur.add_undo_method(node, "set_owner", prev_owner)
	ur.add_undo_method(parent, "move_child", node, index)
	ur.commit_action()

	editor_interface.mark_scene_as_unsaved()

	return {
		"status": "success",
		"message": "Deleted node: %s" % node_path
	}

func _modify_node(command: Dictionary) -> Dictionary:
	var node_path = command.get("path", "")
	var properties = command.get("properties", {})

	if node_path.is_empty():
		return {"status": "error", "message": "Node path is required"}

	var editor_interface = editor_plugin.get_editor_interface()
	var edited_scene = editor_interface.get_edited_scene_root()

	if not edited_scene:
		return {
			"status": "error",
			"message": "No scene is currently open. Please create or open a scene first.",
			"suggestion": "Use create_scene or open an existing scene"
		}

	var node = _resolve_node(node_path)
	if not node:
		return {"status": "error", "message": "Node not found: %s" % node_path}

	var ur: EditorUndoRedoManager = editor_plugin.get_undo_redo()
	ur.create_action("Modify Node: %s" % node_path)
	var modified_props := []
	for prop_name in properties:
		# Verify property exists on the node
		var exists := false
		var prop_type = TYPE_NIL
		for p in node.get_property_list():
			if p.get("name", "") == prop_name:
				exists = true
				prop_type = p.get("type")
				break
		if exists:
			var old_val = node.get(prop_name)
			var new_val = properties[prop_name]
			
			# Handle Resource loading for Object types (like Script)
			if prop_type == TYPE_OBJECT and typeof(new_val) == TYPE_STRING and new_val.begins_with("res://"):
				var res = load(new_val)
				if res:
					new_val = res
				else:
					push_warning("Failed to load resource from path: %s" % new_val)
			
			ur.add_do_property(node, prop_name, new_val)
			ur.add_undo_property(node, prop_name, old_val)
			modified_props.append(prop_name)
		else:
			push_warning("Property not found on node: %s" % prop_name)
	ur.commit_action()

	editor_interface.mark_scene_as_unsaved()

	return {
		"status": "success",
		"message": "Modified node: %s" % node_path,
		"data": {
			"modified_properties": modified_props
		}
	}

func _attach_script(command: Dictionary) -> Dictionary:
	var node_path = command.get("path", "")
	var script_content = command.get("script_content", "")
	var script_path = command.get("script_path", null)

	if node_path.is_empty():
		return {"status": "error", "message": "Node path is required"}
	if script_content.is_empty():
		return {"status": "error", "message": "Script content is required"}

	var editor_interface = editor_plugin.get_editor_interface()
	var edited_scene = editor_interface.get_edited_scene_root()

	if not edited_scene:
		return {
			"status": "error",
			"message": "No scene is currently open. Please create or open a scene first.",
			"suggestion": "Use create_scene or open an existing scene"
		}

	var node = _resolve_node(node_path)
	if not node:
		return {"status": "error", "message": "Node not found: %s" % node_path}

	# Create script resource
	var script := GDScript.new()
	script.source_code = script_content
	var err := script.reload()
	if err != OK:
		return {"status": "error", "message": "Script compilation failed: %s" % error_string(err)}

	# Save script if a path was provided
	if script_path:
		var file_err = ResourceSaver.save(script, script_path)
		if file_err != OK:
			return {"status": "error", "message": "Failed to save script: %s" % error_string(file_err)}

	# Attach via undo/redo so it's revertible
	var prev_script: Script = node.get_script()
	var ur: EditorUndoRedoManager = editor_plugin.get_undo_redo()
	ur.create_action("Attach Script to %s" % node.name)
	ur.add_do_method(node, "set_script", script)
	ur.add_undo_method(node, "set_script", prev_script)
	ur.commit_action()

	editor_interface.mark_scene_as_unsaved()

	return {
		"status": "success",
		"message": "Attached script to node: %s" % node_path,
		"data": {
			"script_path": script_path if script_path else "inline"
		}
	}

func _create_scene(command: Dictionary) -> Dictionary:
	var scene_name = command.get("name", "")
	var root_type = command.get("root_type", "Node")
	var save_path = command.get("save_path", null)

	if scene_name.is_empty():
		return {"status": "error", "message": "Scene name is required"}

	# Create root node
	var root_node = _instantiate_node_by_type(root_type)
	if not root_node:
		return {"status": "error", "message": "Failed to create root node of type: %s" % root_type}

	root_node.name = scene_name

	# Create packed scene
	var packed_scene = PackedScene.new()
	var err = packed_scene.pack(root_node)

	if err != OK:
		root_node.free()
		return {"status": "error", "message": "Failed to pack scene: %s" % error_string(err)}

	# Save if path provided
	if save_path:
		var save_err = ResourceSaver.save(packed_scene, save_path)
		if save_err != OK:
			root_node.free()
			return {"status": "error", "message": "Failed to save scene: %s" % error_string(save_err)}

	# Open in editor
	var editor_interface = editor_plugin.get_editor_interface()
	if save_path:
		editor_interface.open_scene_from_path(save_path)

		# Wait a frame to ensure the scene is loaded
		await editor_plugin.get_tree().process_frame

		# Verify the scene is actually open
		var opened_scene = editor_interface.get_edited_scene_root()
		if not opened_scene or opened_scene.name != scene_name:
			return {
				"status": "error",
				"message": "Scene created but failed to open properly. Please open %s manually." % save_path
			}
	else:
		editor_interface.edit_node(root_node)

	return {
		"status": "success",
		"message": "Created and opened scene: %s" % scene_name,
		"data": {
			"save_path": save_path if save_path else "unsaved",
			"scene_name": scene_name
		}
	}

func _get_scene_info(command: Dictionary) -> Dictionary:
	var editor_interface = editor_plugin.get_editor_interface()
	var edited_scene = editor_interface.get_edited_scene_root()

	if not edited_scene:
		return {
			"status": "success",
			"message": "No scene is currently open",
			"data": {
				"scene_open": false
			}
		}

	var scene_info = {
		"scene_open": true,
		"root_name": edited_scene.name,
		"root_type": edited_scene.get_class(),
		"scene_path": edited_scene.scene_file_path,
		"nodes": _get_node_tree(edited_scene)
	}

	return {
		"status": "success",
		"message": "Scene info retrieved",
		"data": scene_info
	}

func _get_node_tree(node: Node, depth: int = 0) -> Dictionary:
	var info = {
		"name": node.name,
		"type": node.get_class(),
		"path": str(node.get_path()),
		"children": []
	}

	if depth < 5:  # Limit depth to avoid huge responses
		for child in node.get_children():
			info.children.append(_get_node_tree(child, depth + 1))

	return info

func _instantiate_node_by_type(type_name: String) -> Node:
	# Try to instantiate using ClassDB
	if ClassDB.class_exists(type_name):
		if ClassDB.can_instantiate(type_name):
			return ClassDB.instantiate(type_name)

	# Fallback for common types
	match type_name:
		"Node": return Node.new()
		"Node2D": return Node2D.new()
		"Node3D": return Node3D.new()
		"Control": return Control.new()
		"CharacterBody2D": return CharacterBody2D.new()
		"CharacterBody3D": return CharacterBody3D.new()
		"Sprite2D": return Sprite2D.new()
		"Sprite3D": return Sprite3D.new()
		"CollisionShape2D": return CollisionShape2D.new()
		"CollisionShape3D": return CollisionShape3D.new()
		"Area2D": return Area2D.new()
		"Area3D": return Area3D.new()
		"Camera2D": return Camera2D.new()
		"Camera3D": return Camera3D.new()
		"Label": return Label.new()
		"Button": return Button.new()
		_:
			push_error("Unknown node type: %s" % type_name)
			return null

	# === Editor integration commands ===
func _select_nodes(command: Dictionary) -> Dictionary:
		var paths: Array = command.get("paths", [])
		var clear := bool(command.get("clear", true))
		var editor_interface = editor_plugin.get_editor_interface()
		var edited_scene = editor_interface.get_edited_scene_root()
		if not edited_scene:
			return {"status": "error", "message": "No scene is currently open."}
		var selection = editor_interface.get_selection()
		if selection == null:
			return {"status": "error", "message": "Editor selection is unavailable"}
		if clear:
			selection.clear()
		var added := []
		for p in paths:
			var n = _resolve_node(str(p))
			if n:
				selection.add_node(n)
				added.append(str(edited_scene.get_path_to(n)))
		return {"status": "success", "message": "Selection updated", "data": {"selected": added, "count": added.size()}}

func _focus_node(command: Dictionary) -> Dictionary:
		var path := str(command.get("path", ""))
		var also_select := bool(command.get("select", true))
		if path.is_empty():
			return {"status": "error", "message": "Node path is required"}
		var editor_interface = editor_plugin.get_editor_interface()
		var edited_scene = editor_interface.get_edited_scene_root()
		if not edited_scene:
			return {"status": "error", "message": "No scene is currently open."}
		var node = _resolve_node(path)
		if not node:
			return {"status": "error", "message": "Node not found: %s" % path}
		editor_interface.edit_node(node)
		if also_select and editor_interface.get_selection():
			editor_interface.get_selection().clear()
			editor_interface.get_selection().add_node(node)
		return {"status": "success", "message": "Focused node: %s" % path}

func _play(command: Dictionary) -> Dictionary:
		var mode := str(command.get("mode", "current")).to_lower()
		var editor_interface = editor_plugin.get_editor_interface()
		match mode:
			"current":
				editor_interface.play_current_scene()
				return {"status": "success", "message": "Playing current scene"}
			"main":
				editor_interface.play_main_scene()
				return {"status": "success", "message": "Playing main scene"}
			"custom":
				var path := _to_res_path(str(command.get("path", "")))
				if path.is_empty():
					return {"status": "error", "message": "Path is required for custom play"}
				editor_interface.play_custom_scene(path)
				return {"status": "success", "message": "Playing scene: %s" % path}
			_:
				return {"status": "error", "message": "Unknown play mode: %s" % mode}

func _open_scene(command: Dictionary) -> Dictionary:
		var path := _to_res_path(str(command.get("path", "")))
		if path.is_empty():
			return {"status": "error", "message": "Scene path is required"}
		var editor_interface = editor_plugin.get_editor_interface()
		editor_interface.open_scene_from_path(path)
		await editor_plugin.get_tree().process_frame
		var opened = editor_interface.get_edited_scene_root()
		if opened and String(opened.scene_file_path) == path:
			return {"status": "success", "message": "Opened scene: %s" % path}
		return {"status": "error", "message": "Failed to open scene: %s" % path}

func _add_command_palette_command(command: Dictionary) -> Dictionary:
		var display_name := str(command.get("display_name", ""))
		var key := str(command.get("key", ""))
		var action_to_execute := str(command.get("action_to_execute", ""))
		var payload := command.get("payload", {})
		if display_name.is_empty() or key.is_empty() or action_to_execute.is_empty():
			return {"status": "error", "message": "display_name, key, and action_to_execute are required"}
		var cp = editor_plugin.get_editor_interface().get_command_palette()
		if cp == null:
			return {"status": "error", "message": "Command palette unavailable in this editor build"}
		var callable := Callable(self, "_on_palette_command").bind(action_to_execute, payload)
		cp.add_command(display_name, key, callable)
		return {"status": "success", "message": "Command added to palette", "data": {"key": key, "display_name": display_name}}

	# === Search commands ===
func _search_nodes_by_type(command: Dictionary) -> Dictionary:
		var type_name := str(command.get("type", ""))
		var select_results := bool(command.get("select_results", false))
		var focus_first := bool(command.get("focus_first", false))
		if type_name.is_empty():
			return {"status": "error", "message": "Type is required"}
		var editor_interface = editor_plugin.get_editor_interface()
		var edited_scene: Node = editor_interface.get_edited_scene_root()
		if not edited_scene:
			return {"status": "error", "message": "No scene is currently open."}
		var results := []
		var stack := [edited_scene]
		while stack.size() > 0:
			var n: Node = stack.pop_back()
			if n.is_class(type_name):
				results.append(str(edited_scene.get_path_to(n)))
			for c in n.get_children():
				stack.append(c)
		var selected_count := 0
		var focused := ""
		if select_results and results.size() > 0:
			var sel_res = _select_nodes({"paths": results, "clear": true})
			if typeof(sel_res) == TYPE_DICTIONARY:
				var sel_data = sel_res.get("data", {})
				if typeof(sel_data) == TYPE_DICTIONARY:
					selected_count = int(sel_data.get("count", 0))
		if focus_first and results.size() > 0:
			_focus_node({"path": results[0], "select": false})
			focused = results[0]
		var msg := "Found %d nodes of type %s" % [results.size(), type_name] if (results.size() > 0) else "No nodes found of type %s" % type_name
		return {"status": "success", "message": msg, "data": {"matches": results, "count": results.size(), "selected_count": selected_count, "focused": focused}}

func _search_nodes_by_name(command: Dictionary) -> Dictionary:
		var query := str(command.get("name", ""))
		var exact := bool(command.get("exact", false))
		var case_sensitive := bool(command.get("case_sensitive", false))
		var select_results := bool(command.get("select_results", false))
		var focus_first := bool(command.get("focus_first", false))
		if query.is_empty():
			return {"status": "error", "message": "Name is required"}
		var editor_interface = editor_plugin.get_editor_interface()
		var edited_scene: Node = editor_interface.get_edited_scene_root()
		if not edited_scene:
			return {"status": "error", "message": "No scene is currently open."}
		var results := []
		var cmp_query := query if case_sensitive else query.to_lower()
		var stack := [edited_scene]
		while stack.size() > 0:
			var n: Node = stack.pop_back()
			var n_name := str(n.name)
			var cmp_name := n_name if case_sensitive else n_name.to_lower()
			var match := cmp_name == cmp_query if exact else (cmp_name.find(cmp_query) != -1)
			if match:
				results.append(str(edited_scene.get_path_to(n)))
			for c in n.get_children():
				stack.append(c)
		var selected_count := 0
		var focused := ""
		if select_results and results.size() > 0:
			var sel_res = _select_nodes({"paths": results, "clear": true})
			if typeof(sel_res) == TYPE_DICTIONARY:
				var sel_data = sel_res.get("data", {})
				if typeof(sel_data) == TYPE_DICTIONARY:
					selected_count = int(sel_data.get("count", 0))
		if focus_first and results.size() > 0:
			_focus_node({"path": results[0], "select": false})
			focused = results[0]
		var mode := "exact" if exact else "contains"
		var msg := "Found %d nodes where name %s '%s'" % [results.size(), mode, query] if (results.size() > 0) else "No nodes found where name %s '%s'" % [mode, query]
		return {"status": "success", "message": msg, "data": {"matches": results, "count": results.size(), "selected_count": selected_count, "focused": focused}}

func _search_nodes_by_group(command: Dictionary) -> Dictionary:
		var group := str(command.get("group", ""))
		var select_results := bool(command.get("select_results", false))
		var focus_first := bool(command.get("focus_first", false))
		if group.is_empty():
			return {"status": "error", "message": "Group is required"}
		var editor_interface = editor_plugin.get_editor_interface()
		var edited_scene: Node = editor_interface.get_edited_scene_root()
		if not edited_scene:
			return {"status": "error", "message": "No scene is currently open."}
		var results := []
		var stack := [edited_scene]
		while stack.size() > 0:
			var n: Node = stack.pop_back()
			if n.is_in_group(group):
				results.append(str(edited_scene.get_path_to(n)))
			for c in n.get_children():
				stack.append(c)
		var selected_count := 0
		var focused := ""
		if select_results and results.size() > 0:
			var sel_res = _select_nodes({"paths": results, "clear": true})
			if typeof(sel_res) == TYPE_DICTIONARY:
				var sel_data = sel_res.get("data", {})
				if typeof(sel_data) == TYPE_DICTIONARY:
					selected_count = int(sel_data.get("count", 0))
		if focus_first and results.size() > 0:
			_focus_node({"path": results[0], "select": false})
			focused = results[0]
		var msg := "Found %d nodes in group '%s'" % [results.size(), group] if (results.size() > 0) else "No nodes found in group '%s'" % group
		return {"status": "success", "message": msg, "data": {"matches": results, "count": results.size(), "selected_count": selected_count, "focused": focused}}

func _search_nodes_by_script(command: Dictionary) -> Dictionary:
		var script_path := str(command.get("script_path", ""))
		var filter_by_path := not script_path.is_empty()
		var select_results := bool(command.get("select_results", false))
		var focus_first := bool(command.get("focus_first", false))
		if filter_by_path:
			script_path = _to_res_path(script_path)
		var editor_interface = editor_plugin.get_editor_interface()
		var edited_scene: Node = editor_interface.get_edited_scene_root()
		if not edited_scene:
			return {"status": "error", "message": "No scene is currently open."}
		var results := []
		var stack := [edited_scene]
		while stack.size() > 0:
			var n: Node = stack.pop_back()
			var s: Script = n.get_script()
			if s:
				if not filter_by_path or String(s.resource_path) == script_path:
					results.append(str(edited_scene.get_path_to(n)))
			for c in n.get_children():
				stack.append(c)
		var selected_count := 0
		var focused := ""
		if select_results and results.size() > 0:
			var sel_res = _select_nodes({"paths": results, "clear": true})
			if typeof(sel_res) == TYPE_DICTIONARY:
				var sel_data = sel_res.get("data", {})
				if typeof(sel_data) == TYPE_DICTIONARY:
					selected_count = int(sel_data.get("count", 0))
		if focus_first and results.size() > 0:
			_focus_node({"path": results[0], "select": false})
			focused = results[0]
		var msg := "Found %d nodes with scripts" % results.size()
		if filter_by_path:
			msg = "Found %d nodes with script '%s'" % [results.size(), script_path] if (results.size() > 0) else "No nodes found with script '%s'" % script_path
		elif results.size() == 0:
			msg = "No nodes with scripts found"
		return {"status": "success", "message": msg, "data": {"matches": results, "count": results.size(), "selected_count": selected_count, "focused": focused}}

	# === Structure editing commands ===
func _duplicate_node(command: Dictionary) -> Dictionary:
		var path := str(command.get("path", ""))
		var parent_path_val = command.get("parent_path", null)
		var explicit_name := str(command.get("name", ""))
		if path.is_empty():
			return {"status": "error", "message": "Path is required"}
		var editor_interface = editor_plugin.get_editor_interface()
		var edited_scene: Node = editor_interface.get_edited_scene_root()
		if not edited_scene:
			return {"status": "error", "message": "No scene is currently open."}
		var node: Node = _resolve_node(path)
		if not node:
			return {"status": "error", "message": "Node not found: %s" % path}
		var current_parent: Node = node.get_parent()
		if current_parent == null:
			return {"status": "error", "message": "Node has no parent (can't duplicate rootless node)"}
		var target_parent: Node = current_parent
		if parent_path_val and not String(parent_path_val).is_empty():
			var p_str := str(parent_path_val)
			target_parent = _resolve_node(p_str)
			if not target_parent:
				return {"status": "error", "message": "Parent node not found: %s" % p_str}
		# Duplicate with scripts, groups, and signals
		var flags: int = Node.DUPLICATE_SIGNALS | Node.DUPLICATE_GROUPS | Node.DUPLICATE_SCRIPTS
		var dup: Node = node.duplicate(flags)
		if dup == null:
			return {"status": "error", "message": "Failed to duplicate node"}
		# Name handling: explicit or auto-unique
		var final_name := explicit_name
		if final_name.is_empty():
			final_name = _make_unique_name(target_parent, str(node.name))
		else:
			if _sibling_name_exists(target_parent, final_name):
				final_name = _make_unique_name(target_parent, final_name)
		# Determine owner for save
		var owner_for_save: Node = target_parent.owner if target_parent.owner else edited_scene
		# Build undo/redo
		var ur: EditorUndoRedoManager = editor_plugin.get_undo_redo()
		ur.create_action("Duplicate Node: %s" % path)
		ur.add_do_method(target_parent, "add_child", dup)
		ur.add_do_property(dup, "name", final_name)
		# Set owner on whole subtree
		var subs := []
		_collect_subtree_nodes(dup, subs)
		for s in subs:
			ur.add_do_method(s, "set_owner", owner_for_save)
			ur.add_undo_method(s, "set_owner", null)
		# If duplicating under same parent, place it right after original
		if target_parent == current_parent:
			var insert_index: int = current_parent.get_child_index(node) + 1
			ur.add_do_method(target_parent, "move_child", dup, insert_index)
		ur.add_undo_method(target_parent, "remove_child", dup)
		ur.commit_action()
		editor_interface.mark_scene_as_unsaved()
		return {"status": "success", "message": "Duplicated node", "data": {"new_path": str(edited_scene.get_path_to(dup)), "name": final_name, "parent_path": str(edited_scene.get_path_to(target_parent))}}

func _reparent_node(command: Dictionary) -> Dictionary:
		var path := str(command.get("path", ""))
		var new_parent_path := str(command.get("new_parent_path", ""))
		var idx_param = command.get("index", null)
		var keep_param_present := command.has("keep_global_transform")
		var keep_global := keep_param_present and bool(command.get("keep_global_transform", true))
		if path.is_empty() or new_parent_path.is_empty():
			return {"status": "error", "message": "path and new_parent_path are required"}
		var editor_interface = editor_plugin.get_editor_interface()
		var edited_scene: Node = editor_interface.get_edited_scene_root()
		if not edited_scene:
			return {"status": "error", "message": "No scene is currently open."}
		var node: Node = _resolve_node(path)
		if not node:
			return {"status": "error", "message": "Node not found: %s" % path}
		var old_parent: Node = node.get_parent()
		if old_parent == null:
			return {"status": "error", "message": "Node has no parent (can't reparent rootless node)"}
		var dest_parent: Node = _resolve_node(new_parent_path)
		if not dest_parent:
			return {"status": "error", "message": "Destination parent not found: %s" % new_parent_path}
		if node == dest_parent or node.is_ancestor_of(dest_parent):
			return {"status": "error", "message": "Cannot reparent a node under itself or its descendant"}
		if not keep_param_present:
			# Default true for spatial/canvas nodes
			keep_global = node is Node2D or node is Node3D
		var old_index: int = old_parent.get_child_index(node)
		var target_index: int = -1
		if typeof(idx_param) == TYPE_INT:
			target_index = clamp(int(idx_param), 0, dest_parent.get_child_count())
		else:
			target_index = old_index if dest_parent == old_parent else dest_parent.get_child_count()
		if dest_parent == old_parent and target_index == old_index:
			return {"status": "success", "message": "Node already at requested position", "data": {"path": path, "index": old_index}}
		var owner_for_save: Node = dest_parent.owner if dest_parent.owner else edited_scene
		# Collect subtree owners for undo
		var subs := []
		_collect_subtree_nodes(node, subs)
		var prev_owners := []
		for s in subs:
			prev_owners.append(s.owner)
		var ur: EditorUndoRedoManager = editor_plugin.get_undo_redo()
		if dest_parent == old_parent:
			ur.create_action("Move Node: %s" % path)
			ur.add_do_method(old_parent, "move_child", node, target_index)
			ur.add_undo_method(old_parent, "move_child", node, old_index)
			ur.commit_action()
			editor_interface.mark_scene_as_unsaved()
			return {"status": "success", "message": "Moved node within parent", "data": {"path": str(edited_scene.get_path_to(node)), "index": target_index}}
		# Full reparent
		ur.create_action("Reparent Node: %s" % path)
		ur.add_do_method(node, "reparent", dest_parent, keep_global)
		ur.add_do_method(dest_parent, "move_child", node, target_index)
		for i in range(subs.size()):
			ur.add_do_method(subs[i], "set_owner", owner_for_save)
			ur.add_undo_method(subs[i], "set_owner", prev_owners[i])
		ur.add_undo_method(node, "reparent", old_parent, keep_global)
		ur.add_undo_method(old_parent, "move_child", node, old_index)
		ur.commit_action()
		editor_interface.mark_scene_as_unsaved()
		return {"status": "success", "message": "Reparented node", "data": {"new_parent_path": str(edited_scene.get_path_to(dest_parent)), "new_path": str(edited_scene.get_path_to(node)), "index": target_index}}

func _rename_node(command: Dictionary) -> Dictionary:
		var path := str(command.get("path", ""))
		var new_name := str(command.get("new_name", ""))
		if path.is_empty() or new_name.is_empty():
			return {"status": "error", "message": "path and new_name are required"}
		var editor_interface = editor_plugin.get_editor_interface()
		var edited_scene: Node = editor_interface.get_edited_scene_root()
		if not edited_scene:
			return {"status": "error", "message": "No scene is currently open."}
		var node: Node = _resolve_node(path)
		if not node:
			return {"status": "error", "message": "Node not found: %s" % path}
		var parent := node.get_parent()
		if parent == null:
			return {"status": "error", "message": "Cannot rename the scene root via this command"}
		# Validate sibling name uniqueness
		if _sibling_name_exists(parent, new_name, node):
			return {"status": "error", "message": "A sibling with the name '%s' already exists" % new_name}
		var old_name := str(node.name)
		var ur: EditorUndoRedoManager = editor_plugin.get_undo_redo()
		ur.create_action("Rename Node: %s -> %s" % [old_name, new_name])
		ur.add_do_property(node, "name", new_name)
		ur.add_undo_property(node, "name", old_name)
		ur.commit_action()
		editor_interface.mark_scene_as_unsaved()
		return {"status": "success", "message": "Renamed node", "data": {"new_path": str(edited_scene.get_path_to(node))}}

func _add_to_group(command: Dictionary) -> Dictionary:
		var path := str(command.get("path", ""))
		var group := str(command.get("group", ""))
		var persistent := bool(command.get("persistent", true))
		if path.is_empty() or group.is_empty():
			return {"status": "error", "message": "path and group are required"}
		var editor_interface = editor_plugin.get_editor_interface()
		var edited_scene: Node = editor_interface.get_edited_scene_root()
		if not edited_scene:
			return {"status": "error", "message": "No scene is currently open."}
		var node: Node = _resolve_node(path)
		if not node:
			return {"status": "error", "message": "Node not found: %s" % path}
		if node.is_in_group(group):
			return {"status": "success", "message": "Node is already in group '%s'" % group}
		var ur: EditorUndoRedoManager = editor_plugin.get_undo_redo()
		ur.create_action("Add To Group: %s" % group)
		ur.add_do_method(node, "add_to_group", group, persistent)
		ur.add_undo_method(node, "remove_from_group", group)
		ur.commit_action()
		editor_interface.mark_scene_as_unsaved()
		return {"status": "success", "message": "Added node to group", "data": {"group": group}}

func _remove_from_group(command: Dictionary) -> Dictionary:
		var path := str(command.get("path", ""))
		var group := str(command.get("group", ""))
		if path.is_empty() or group.is_empty():
			return {"status": "error", "message": "path and group are required"}
		var editor_interface = editor_plugin.get_editor_interface()
		var edited_scene: Node = editor_interface.get_edited_scene_root()
		if not edited_scene:
			return {"status": "error", "message": "No scene is currently open."}
		var node: Node = _resolve_node(path)
		if not node:
			return {"status": "error", "message": "Node not found: %s" % path}
		if not node.is_in_group(group):
			return {"status": "success", "message": "Node is not in group '%s'" % group}
		var ur: EditorUndoRedoManager = editor_plugin.get_undo_redo()
		ur.create_action("Remove From Group: %s" % group)
		ur.add_do_method(node, "remove_from_group", group)
		# Best-effort: restore persistently on undo
		ur.add_undo_method(node, "add_to_group", group, true)
		ur.commit_action()
		editor_interface.mark_scene_as_unsaved()
		return {"status": "success", "message": "Removed node from group", "data": {"group": group}}



func _on_palette_command(action: String, payload) -> void:
		var cmd := {}
		if typeof(payload) == TYPE_DICTIONARY:
			cmd = payload.duplicate(true)
		cmd["action"] = action
		# Execute without blocking the UI; result is sent via WebSocket normally for direct calls.
		call_deferred("execute_command", cmd)


# === Debug capture commands ===
func _start_debug_capture(command: Dictionary) -> Dictionary:
	if debugger_plugin:
		debugger_plugin.enable_capture()
		return {"status": "success", "message": "Debug capture enabled"}
	return {"status": "error", "message": "Debugger plugin not available"}

func _stop_debug_capture(command: Dictionary) -> Dictionary:
	if debugger_plugin:
		debugger_plugin.disable_capture()
		return {"status": "success", "message": "Debug capture disabled"}
	return {"status": "error", "message": "Debugger plugin not available"}

# === Debug screenshot command ===
func _capture_game_screenshot(command: Dictionary) -> Dictionary:
	# Check if game is running by checking if we have an active debugger session
	var editor_interface = editor_plugin.get_editor_interface()
	if not editor_interface.is_playing_scene():
		return {"status": "error", "message": "No game is currently running. Use 'play' command first."}

	# Wait a moment for the game to render
	var wait_frames = command.get("wait_frames", 3)
	for i in range(wait_frames):
		await editor_plugin.get_tree().process_frame

	# Capture from the running game's viewport
	# The game runs in a separate window, but we can access its viewport through the tree
	var game_viewport: Viewport = null

	# Try to get the game viewport from the running scene tree
	# When a game is running, it's in a separate SceneTree, but we can access it through the debugger
	# For now, we'll capture the main viewport which should show the game when it's running
	var root = editor_plugin.get_tree().root
	if root:
		# Get the last child which is typically the running game window
		var child_count = root.get_child_count()
		if child_count > 0:
			# The running game is usually the last window
			var last_window = root.get_child(child_count - 1)
			if last_window is Window:
				game_viewport = last_window.get_viewport()

	if not game_viewport:
		# Fallback: try to get viewport from root
		game_viewport = root.get_viewport() if root else null

	if not game_viewport:
		return {"status": "error", "message": "Could not access game viewport"}

	# Capture the viewport texture
	var tex := game_viewport.get_texture()
	if not tex:
		return {"status": "error", "message": "Failed to get viewport texture"}

	var image: Image = tex.get_image()
	if not image:
		return {"status": "error", "message": "Failed to get image from texture"}

	var size = image.get_size()
	var bytes: PackedByteArray = image.save_png_to_buffer()
	var img_b64 = Marshalls.raw_to_base64(bytes)

	# Get project path
	var project_path = ProjectSettings.globalize_path("res://")
	var screenshots_dir = project_path.path_join(".godoty").path_join("screenshots").path_join("game")

	# Create directory if it doesn't exist
	if not DirAccess.dir_exists_absolute(screenshots_dir):
		var err = DirAccess.make_dir_recursive_absolute(screenshots_dir)
		if err != OK:
			return {"status": "error", "message": "Failed to create game screenshots directory: " + str(err)}

	# Generate filename with timestamp
	var timestamp = Time.get_datetime_string_from_system().replace(":", "-")
	var filename = command.get("filename", "game_%s.png" % timestamp)
	if not filename.ends_with(".png"):
		filename += ".png"

	var filepath = screenshots_dir.path_join(filename)

	# Save to file
	var file = FileAccess.open(filepath, FileAccess.WRITE)
	if not file:
		return {"status": "error", "message": "Failed to open file for writing: " + filepath}

	file.store_buffer(bytes)
	file.close()

	# Return relative path from project root
	var relative_path = filepath.replace(project_path, "").trim_prefix("/").trim_prefix("\થી")

	return {
		"status": "success",
		"message": "Game screenshot captured successfully",
		"data": {
			"filepath": relative_path,
			"absolute_path": filepath,
			"size": {"w": size.x, "h": size.y},
			"timestamp": timestamp,
			"image_b64": img_b64,
			"type": "game_debug"
		}
	}

func _clear_debug_output(command: Dictionary) -> Dictionary:
	if debugger_plugin:
		debugger_plugin.clear()
		return {"status": "success", "message": "Debug output cleared"}
	return {"status": "error", "message": "Debugger plugin not available"}

func _get_debug_output(command: Dictionary) -> Dictionary:
	var limit := int(command.get("limit", 200))
	if debugger_plugin and debugger_plugin.has_method("get_buffer"):
		var msgs = debugger_plugin.call("get_buffer", limit)
		return {"status": "success", "message": "Debug output retrieved", "data": {"messages": msgs}}
	return {"status": "error", "message": "Debugger plugin not available"}

# === Scene inspection commands ===
func _inspect_scene_file(command: Dictionary) -> Dictionary:
	var path := str(command.get("path", ""))
	if path.is_empty():
		return {"status": "error", "message": "Scene file path is required"}
	var res_path := _to_res_path(path)
	var packed: PackedScene = load(res_path)
	if packed == null:
		return {"status": "error", "message": "Failed to load scene: %s" % res_path}
	var state: SceneState = packed.get_state()
	var detailed := _build_tree_from_state(state)
	return {"status": "success", "message": "Scene loaded", "data": {"scene_path": res_path, "root": detailed}}

func _get_current_scene_detailed(command: Dictionary) -> Dictionary:
	var editor_interface = editor_plugin.get_editor_interface()
	var root := editor_interface.get_edited_scene_root()
	if not root:
		return {"status": "success", "message": "No scene is currently open", "data": {"scene_open": false}}
	var detailed := _get_node_tree_with_props(root)
	return {"status": "success", "message": "Current scene detailed info", "data": {"scene_open": true, "scene_path": root.scene_file_path, "root": detailed}}

# Helpers
func _to_res_path(p: String) -> String:
	if p.begins_with("res://") or p.begins_with("user://"):
		return p
	var localized := ProjectSettings.localize_path(p)
	return localized if not localized.is_empty() else p

func _get_node_tree_with_props(node: Node, depth: int = 0) -> Dictionary:
	var info := {
		"name": node.name,
		"type": node.get_class(),
		"path": str(node.get_path()),
		"script": node.get_script().resource_path if node.get_script() else "",
		"groups": node.get_groups(),
		"properties": _extract_basic_properties(node),
		"children": []
	}
	if depth < 5:
		for child in node.get_children():
			info.children.append(_get_node_tree_with_props(child, depth + 1))
	return info

func _has_property(obj: Object, prop: String) -> bool:
	for p in obj.get_property_list():
		if p.get("name", "") == prop:
			return true
	return false

func _extract_basic_properties(node: Node) -> Dictionary:
	var props := {}
	if node is Node2D:
		if _has_property(node, "position"): props["position"] = node.get("position")
		if _has_property(node, "rotation_degrees"): props["rotation_degrees"] = node.get("rotation_degrees")
		if _has_property(node, "scale"): props["scale"] = node.get("scale")
		if _has_property(node, "z_index"): props["z_index"] = node.get("z_index")
		if _has_property(node, "visible"): props["visible"] = node.get("visible")
		if _has_property(node, "modulate"): props["modulate"] = str(node.get("modulate"))
	elif node is Node3D:
		if _has_property(node, "position"): props["position"] = node.get("position")
		elif _has_property(node, "transform"): props["origin"] = node.get("transform").origin
		if _has_property(node, "rotation_degrees"): props["rotation_degrees"] = node.get("rotation_degrees")
		if _has_property(node, "scale"): props["scale"] = node.get("scale")
		if _has_property(node, "visible"): props["visible"] = node.get("visible")
elif node is Control:
		if _has_property(node, "position"): props["position"] = node.get("position")
		if _has_property(node, "size"): props["size"] = node.get("size")
		for an in ["anchor_left", "anchor_top", "anchor_right", "anchor_bottom"]:
			if _has_property(node, an): props[an] = node.get(an)
		if _has_property(node, "pivot_offset"): props["pivot_offset"] = node.get("pivot_offset")
		if _has_property(node, "rotation_degrees"): props["rotation_degrees"] = node.get("rotation_degrees")
		if _has_property(node, "scale"): props["scale"] = node.get("scale")
		if _has_property(node, "visible"): props["visible"] = node.get("visible")
	else:
		if _has_property(node, "visible"): props["visible"] = node.get("visible")
	return props

func _build_tree_from_state(state: SceneState) -> Dictionary:
	var nodes := {}
	var root_key := ""
	var count := state.get_node_count()
	for i in count:
		var path: NodePath = state.get_node_path(i)
		var path_str := String(path)
		var info := {
			"name": (path.get_name(path.get_name_count() - 1) if path.get_name_count() > 0 else ""),
			"type": state.get_node_type(i),
			"path": path_str,
			"properties": {},
			"children": []
		}
		var pc := state.get_node_property_count(i)
		for j in pc:
			var prop_name := state.get_node_property_name(i, j)
			var prop_val := state.get_node_property_value(i, j)
			info.properties[prop_name] = prop_val
		nodes[path_str] = info
		if path.get_name_count() == 1:
			root_key = path_str
	# Link children
	for key in nodes.keys():
		if key == root_key:
			continue
		var idx: int = String(key).rfind("/")
		if idx == -1:
			continue
		var parent_key: String = String(key).substr(0, idx)
		if nodes.has(parent_key):
			nodes[parent_key].children.append(nodes[key])
	# Fallback if root_key not found
	if root_key == "" and nodes.size() > 0:
		root_key = nodes.keys()[0]
	return nodes.get(root_key, {"name": "", "type": "", "path": "", "properties": {}, "children": []})

	# --- Additional helpers ---
func _collect_subtree_nodes(n: Node, out: Array) -> void:
		out.append(n)
		for c in n.get_children():
			_collect_subtree_nodes(c, out)

func _sibling_name_exists(parent: Node, name: String, exclude: Node = null) -> bool:
		for c in parent.get_children():
			if c != exclude and String(c.name) == name:
				return true
		return false

func _make_unique_name(parent: Node, base: String) -> String:
		var candidate := base
		if not _sibling_name_exists(parent, candidate):
			return candidate
		var i := 2
		while true:
			candidate = "%s%d" % [base, i]
			if not _sibling_name_exists(parent, candidate):
				return candidate
			i += 1
		return candidate

func _get_project_path(command: Dictionary) -> Dictionary:
	# Get the absolute path to the project directory
	var project_path = ProjectSettings.globalize_path("res://")
	print("Godoty: get_project_path called, returning: ", project_path)
	return {
		"status": "success",
		"message": "Retrieved project path",
		"data": {
			"project_path": project_path
		}
	}

func _get_project_info(command: Dictionary) -> Dictionary:
	var project_path := ProjectSettings.globalize_path("res://")
	
	# Get Godot version info
	var version_info := Engine.get_version_info()
	var godot_version := "%d.%d.%d" % [version_info.major, version_info.minor, version_info.patch]
	if version_info.status:
		godot_version += "-%s" % version_info.status

	# Get project settings
	var project_name := ProjectSettings.get_setting("application/config/name", "Unknown")
	var project_settings := {
		"name": project_name,
		"main_scene": ProjectSettings.get_setting("application/run/main_scene", ""),
		"viewport_width": ProjectSettings.get_setting("display/window/size/viewport_width", 1920),
		"viewport_height": ProjectSettings.get_setting("display/window/size/viewport_height", 1080),
		"renderer": ProjectSettings.get_setting("rendering/renderer/rendering_method", "forward_plus")
	}

	return {
		"status": "success",
		"message": "Project info retrieved",
		"data": {
			"project_path": project_path,
			"project_name": project_name,
			"godot_version": godot_version,
			"plugin_version": "0.1.0",
			"is_ready": true,
			"project_settings": project_settings
		}
	}

# --- Visual Context Commands ---

var _auto_capture_enabled: bool = false
var _auto_capture_timer: Timer = null
var _last_visual_context: Dictionary = {}

func _capture_visual_context(command: Dictionary) -> Dictionary:
	"""Capture comprehensive visual context including scene tree, editor state, and viewport"""
	print("Godoty: capture_visual_context called")

	var editor_interface = editor_plugin.get_editor_interface()
	var edited_scene = editor_interface.get_edited_scene_root()

	var context = {
		"timestamp": Time.get_datetime_string_from_system(),
		"editor_state": {
			"current_scene_path": editor_interface.get_current_scene_path(),
			"selected_nodes": [],
			"focused_node": "",
			"playing": editor_interface.is_playing_scene()
		},
		"scene_tree": null,
		"viewport_info": {},
		"editor_layout": {
			"visible_docks": [],
			"active_inspector": ""
		}
	}

	# Get selected nodes
	var selected = editor_interface.get_selection().get_selected_nodes()
	for node in selected:
		if edited_scene:
			context.editor_state.selected_nodes.append(str(edited_scene.get_path_to(node)))

	# Get focused node
	var focused = editor_interface.get_inspector().get_edited_object()
	if focused and edited_scene:
		context.editor_state.focused_node = str(edited_scene.get_path_to(focused))

	# Get scene tree structure if scene is open
	if edited_scene:
		context.scene_tree = _build_scene_tree_snapshot(edited_scene)

	# Get viewport information
	var viewport = editor_interface.get_editor_viewport_2d()
	if viewport:
		context.viewport_info = {
			"size": viewport.get_size(),
			"camera_transform": viewport.get_canvas_transform(),
			"visible_rect": viewport.get_visible_rect()
		}

	# Get visible docks
	var main_screen = editor_interface.get_main_screen_control()
	if main_screen:
		for child in main_screen.get_children():
			if child.visible:
				context.editor_layout.visible_docks.append(child.name)

	# Store for auto-capture
	_last_visual_context = context

	return {
		"status": "success",
		"message": "Captured visual context",
		"data": context
	}

func _get_visual_snapshot(command: Dictionary) -> Dictionary:
	"""Get a visual snapshot of the current editor viewport"""
	print("Godoty: get_visual_snapshot called")

	var editor_interface = editor_plugin.get_editor_interface()
	var viewport = editor_interface.get_editor_viewport_2d()

	if not viewport:
		# Try 3D viewport if 2D is not available
		var viewport_3d = editor_interface.get_editor_viewport_3d(0)
		if viewport_3d:
			return await _capture_3d_viewport(viewport_3d)
		else:
			return {
				"status": "error",
				"message": "No viewport available for capture"
			}

	# Capture 2D viewport
	var img = viewport.get_texture().get_image()
	if img:
		var timestamp = Time.get_unix_time_from_system()
		var filename = "visual_snapshot_%d.png" % timestamp
		var path = "user://snapshots/" + filename

		# Ensure directory exists
		var dir = DirAccess.open("user://")
		if dir:
			dir.make_dir("snapshots")

		# Save image
		img.save_png(path)
		var global_path = ProjectSettings.globalize_path(path)

		# Also save as base64 for immediate transfer
		var base64 = Marshalls.raw_to_base64(img.save_png_to_buffer())

		return {
			"status": "success",
			"message": "Captured visual snapshot",
			"data": {
				"image_path": global_path,
				"filename": filename,
				"base64_data": base64,
				"width": img.get_width(),
				"height": img.get_height(),
				"timestamp": timestamp
			}
		}
	else:
		return {
			"status": "error",
			"message": "Failed to capture viewport image"
		}

func _capture_3d_viewport(viewport: SubViewport) -> Dictionary:
	"""Helper to capture 3D viewport"""
	# Create a copy of the viewport texture
	var viewport_texture = viewport.get_texture()
	if viewport_texture:
		var img = viewport_texture.get_image()
		if img:
			var timestamp = Time.get_unix_time_from_system()
			var filename = "visual_snapshot_3d_%d.png" % timestamp
			var path = "user://snapshots/" + filename

			# Ensure directory exists
			var dir = DirAccess.open("user://")
			if dir:
				dir.make_dir("snapshots")

			# Save image
			img.save_png(path)
			var global_path = ProjectSettings.globalize_path(path)

			return {
				"status": "success",
				"message": "Captured 3D visual snapshot",
				"data": {
					"image_path": global_path,
					"filename": filename,
					"width": img.get_width(),
					"height": img.get_height(),
					"timestamp": timestamp,
					"viewport_type": "3d"
				}
			}

	return {
		"status": "error",
		"message": "Failed to capture 3D viewport"
	}

func _enable_auto_visual_capture(command: Dictionary) -> Dictionary:
	"""Enable automatic visual capture at intervals"""
	var interval = command.get("interval", 5.0)  # Default 5 seconds

	if _auto_capture_enabled:
		return {
			"status": "success",
			"message": "Auto visual capture already enabled",
			"data": {"interval": interval}
		}

	_auto_capture_enabled = true

	# Create timer if it doesn't exist
	if not _auto_capture_timer:
		_auto_capture_timer = Timer.new()
		_auto_capture_timer.wait_time = interval
		_auto_capture_timer.timeout.connect(_on_auto_capture_timeout)
		editor_plugin.add_child(_auto_capture_timer)

	_auto_capture_timer.wait_time = interval
	_auto_capture_timer.autostart = true
	_auto_capture_timer.start()

	print("Godoty: Auto visual capture enabled with interval: ", interval, " seconds")

	return {
		"status": "success",
		"message": "Auto visual capture enabled",
		"data": {
			"interval": interval,
			"enabled": true
		}
	}

func _disable_auto_visual_capture(command: Dictionary) -> Dictionary:
	"""Disable automatic visual capture"""
	if not _auto_capture_enabled:
		return {
			"status": "success",
			"message": "Auto visual capture already disabled"
		}

	_auto_capture_enabled = false

	if _auto_capture_timer and _auto_capture_timer.is_connected("timeout", _on_auto_capture_timeout):
		_auto_capture_timer.stop()
		_auto_capture_timer.autostart = false

	print("Godoty: Auto visual capture disabled")

	return {
		"status": "success",
		"message": "Auto visual capture disabled",
		"data": {"enabled": false}
	}

func _on_auto_capture_timeout():
	"""Timer callback for automatic capture"""
	if _auto_capture_enabled:
		print("Godoty: Auto-capturing visual context...")
		# Capture context in background
		_capture_visual_context({})

func _build_scene_tree_snapshot(root: Node) -> Dictionary:
	"""Build a lightweight snapshot of the scene tree"""
	var snapshot = {
		"name": root.name,
		"type": root.get_class(),
		"path": "/root",
		"visible": root.visible if root.has_method("is_visible") else true,
		"properties": _extract_node_properties(root),
		"children": []
	}

	for child in root.get_children():
		snapshot.children.append(_build_node_snapshot(child, root))

	return snapshot

func _build_node_snapshot(node: Node, root: Node) -> Dictionary:
	var node_path = str(root.get_path_to(node))
	var snapshot = {
		"name": node.name,
		"type": node.get_class(),
		"path": node_path,
		"visible": node.visible if node.has_method("is_visible") else true,
		"properties": _extract_node_properties(node),
		"children": []
	}

	# Limit depth for performance
	if node.get_child_count() < 100:
		for child in node.get_children():
			snapshot.children.append(_build_node_snapshot(child, root))

	return snapshot

func _extract_node_properties(node: Node) -> Dictionary:
	"""Extract key properties from a node for visual context"""
	var props = {}

	# Common properties
	if node.has_method("get_position"):
		props.position = node.call("get_position")
	if node.has_method("get_global_position"):
		props.global_position = node.call("get_global_position")
	if node.has_method("get_scale"):
		props.scale = node.call("get_scale")
	if node.has_method("get_rotation"):
		props.rotation = node.call("get_rotation")
	if node.has_method("get_size"):
		props.size = node.call("get_size")
	if node.has_method("get_modulate"):
		props.modulate = node.call("get_modulate")

	# Script properties
	if node.get_script():
		props.script_path = node.get_script().get_path()

	# Group membership
	if node.get_groups().size() > 0:
		props.groups = node.get_groups()

	return props


func _save_current_scene(command: Dictionary) -> Dictionary:
	var editor_interface = editor_plugin.get_editor_interface()
	var err = editor_interface.save_scene()
	if err != OK:
		return {"status": "error", "message": "Failed to save scene: %s" % error_string(err)}
	return {"status": "success", "message": "Saved current scene"}

func _stop_playing(command: Dictionary) -> Dictionary:
	var editor_interface = editor_plugin.get_editor_interface()
	editor_interface.stop_playing_scene()
	return {"status": "success", "message": "Stopped playing scene"}

func _create_resource(command: Dictionary) -> Dictionary:
	var type = command.get("resource_type", "")
	var path = command.get("resource_path", "")
	var data = command.get("initial_data", {})

	if type.is_empty() or path.is_empty():
		return {"status": "error", "message": "resource_type and resource_path are required"}

	if not ClassDB.class_exists(type) or not ClassDB.is_parent_class(type, "Resource"):
		return {"status": "error", "message": "Invalid resource type: %s" % type}

	var res = ClassDB.instantiate(type)
	for key in data:
		res.set(key, data[key])

	var err = ResourceSaver.save(res, path)
	if err != OK:
		return {"status": "error", "message": "Failed to save resource: %s" % error_string(err)}

	return {"status": "success", "message": "Created resource: %s" % path, "data": {"path": path}}

func _delete_resource(command: Dictionary) -> Dictionary:
	var path = command.get("resource_path", "")
	if path.is_empty():
		return {"status": "error", "message": "resource_path is required"}

	var dir = DirAccess.open("res://")
	if dir.file_exists(path):
		var err = dir.remove(path)
		if err != OK:
			return {"status": "error", "message": "Failed to delete resource: %s" % error_string(err)}
		return {"status": "success", "message": "Deleted resource: %s" % path}
	else:
		return {"status": "error", "message": "Resource not found: %s" % path}

func _create_and_attach_script(command: Dictionary) -> Dictionary:
	var node_path = command.get("node_path", "")
	var script_content = command.get("script_content", "")
	var script_name = command.get("script_name", "")

	if node_path.is_empty() or script_content.is_empty():
		return {"status": "error", "message": "node_path and script_content are required"}

	var editor_interface = editor_plugin.get_editor_interface()
	var edited_scene = editor_interface.get_edited_scene_root()
	if not edited_scene:
		return {"status": "error", "message": "No scene is currently open"}

	var node = _resolve_node(node_path)
	if not node:
		return {"status": "error", "message": "Node not found: %s" % node_path}

	var script = GDScript.new()
	script.source_code = script_content
	var err = script.reload()
	if err != OK:
		return {"status": "error", "message": "Script compilation failed: %s" % error_string(err)}

	var script_path = ""
	if not script_name.is_empty():
		script_path = "res://%s" % script_name
		if not script_path.ends_with(".gd"):
			script_path += ".gd"
		var save_err = ResourceSaver.save(script, script_path)
		if save_err != OK:
			return {"status": "error", "message": "Failed to save script: %s" % error_string(save_err)}

	var ur = editor_plugin.get_undo_redo()
	ur.create_action("Attach Script to %s" % node.name)
	ur.add_do_method(node, "set_script", script)
	ur.add_undo_method(node, "set_script", node.get_script())
	ur.commit_action()

	editor_interface.mark_scene_as_unsaved()

	return {"status": "success", "message": "Created and attached script", "data": {"script_path": script_path}}

func _create_node_with_script(command: Dictionary) -> Dictionary:
	# First create node
	var create_res = _create_node(command)
	if create_res.status == "error":
		return create_res

	var node_path = create_res.data.node_path

	# Then attach script
	var attach_cmd = command.duplicate()
	attach_cmd["node_path"] = node_path
	# script_content should be in command

	var attach_res = _create_and_attach_script(attach_cmd)
	if attach_res.status == "error":
		return attach_res

	return {"status": "success", "message": "Created node with script", "data": {"node_path": node_path, "script_path": attach_res.data.script_path}}