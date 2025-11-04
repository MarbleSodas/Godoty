extends Node

var editor_plugin: EditorPlugin

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
	var edited_scene = editor_interface.get_edited_scene_root()

	if not edited_scene:
		return {
			"status": "error",
			"message": "No scene is currently open. Please create a scene first using create_scene command.",
			"suggestion": "Use create_scene before create_node"
		}
	
	# Create the node
	var new_node = _instantiate_node_by_type(node_type)
	if not new_node:
		return {"status": "error", "message": "Failed to create node of type: %s" % node_type}
	
	new_node.name = node_name
	
	# Find parent node
	var parent_node = edited_scene
	if parent_path and not parent_path.is_empty():
		parent_node = edited_scene.get_node_or_null(parent_path)
		if not parent_node:
			new_node.free()
			return {"status": "error", "message": "Parent node not found: %s" % parent_path}
	
	# Add node to parent
	parent_node.add_child(new_node)
	new_node.owner = edited_scene
	
	# Set properties
	for prop_name in properties:
		if prop_name in new_node:
			new_node.set(prop_name, properties[prop_name])
	
	# Mark scene as modified
	editor_interface.mark_scene_as_unsaved()
	
	return {
		"status": "success",
		"message": "Created node: %s" % node_name,
		"data": {
			"node_path": new_node.get_path()
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
		var open_err = editor_interface.open_scene_from_path(save_path)
		if open_err != OK:
			return {"status": "error", "message": "Failed to open scene: %s" % error_string(open_err)}

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

