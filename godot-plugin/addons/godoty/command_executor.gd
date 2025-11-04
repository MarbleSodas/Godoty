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
		"start_debug_capture":
			return _start_debug_capture(command)
		"stop_debug_capture":
			return _stop_debug_capture(command)
		"clear_debug_output":
			return _clear_debug_output(command)
		"get_debug_output":
			return _get_debug_output(command)
		_:
			return {
				"status": "error",
				"message": "Unknown action: %s" % action
			}

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

	# Resolve parent node (supports relative paths, "/" or "." for root, and absolute paths inside edited scene)
	var parent_node: Node = edited_scene
	if parent_path and not String(parent_path).is_empty():
		var p: NodePath = (typeof(parent_path) == TYPE_NODE_PATH) ? parent_path : NodePath(str(parent_path))
		var p_str := str(p)
		if p_str == "/" or p_str == ".":
			parent_node = edited_scene
		else:
			# Try relative to edited scene first
			parent_node = edited_scene.get_node_or_null(p)
			if not parent_node:
				# If absolute, try resolving from the SceneTree root, but ensure it's inside the edited scene
				var from_root := editor_plugin.get_tree().get_root().get_node_or_null(p)
				if from_root and (from_root == edited_scene or edited_scene.is_ancestor_of(from_root)):
					parent_node = from_root
			if not parent_node:
				new_node.free()
				return {"status": "error", "message": "Parent node not found or not in edited scene: %s" % p_str}

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

	var node = edited_scene.get_node_or_null(node_path)
	if not node:
		return {"status": "error", "message": "Node not found: %s" % node_path}

	if node == edited_scene:
		return {"status": "error", "message": "Cannot delete scene root"}

	node.queue_free()
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

	var node = edited_scene.get_node_or_null(node_path)
	if not node:
		return {"status": "error", "message": "Node not found: %s" % node_path}

	# Set properties
	var modified_props = []
	for prop_name in properties:
		if prop_name in node:
			node.set(prop_name, properties[prop_name])
			modified_props.append(prop_name)
		else:
			push_warning("Property not found on node: %s" % prop_name)

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

	var node = edited_scene.get_node_or_null(node_path)
	if not node:
		return {"status": "error", "message": "Node not found: %s" % node_path}

	# Create script
	var script = GDScript.new()
	script.source_code = script_content
	var err = script.reload()

	if err != OK:
		return {"status": "error", "message": "Script compilation failed: %s" % error_string(err)}

	# Save script if path provided
	if script_path:
		var file_err = ResourceSaver.save(script, script_path)
		if file_err != OK:
			return {"status": "error", "message": "Failed to save script: %s" % error_string(file_err)}

	# Attach script to node
	node.set_script(script)
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
		var idx := key.rfind("/")
		if idx == -1:
			continue
		var parent_key := key.substr(0, idx)
		if nodes.has(parent_key):
			nodes[parent_key].children.append(nodes[key])
	# Fallback if root_key not found
	if root_key == "" and nodes.size() > 0:
		root_key = nodes.keys()[0]
	return nodes.get(root_key, {"name": "", "type": "", "path": "", "properties": {}, "children": []})
