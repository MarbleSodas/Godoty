extends SceneTree

func _init():
	var args = OS.get_cmdline_args()
	
	var operation = ""
	var params_json = ""
	
	var script_path_index = -1
	for i in range(args.size()):
		if args[i].ends_with("godot_operations.gd"):
			script_path_index = i
			break
			
	if script_path_index != -1:
		if args.size() > script_path_index + 1:
			operation = args[script_path_index + 1]
		if args.size() > script_path_index + 2:
			params_json = args[script_path_index + 2]
			
	if operation == "":
		print(JSON.stringify({"error": "No operation specified"}))
		quit(1)
		return

	var params = {}
	if params_json != "":
		var json = JSON.new()
		var error = json.parse(params_json)
		if error == OK:
			params = json.data
		else:
			print(JSON.stringify({"error": "Invalid JSON params", "raw": params_json}))
			quit(1)
			return

	var result = {}
	if operation == "create_scene":
		result = create_scene(params)
	elif operation == "add_node":
		result = add_node(params)
	elif operation == "save_scene":
		result = save_scene(params)
	elif operation == "load_sprite":
		result = load_sprite(params)
	elif operation == "export_mesh_library":
		result = export_mesh_library(params)
	elif operation == "get_uid":
		result = get_uid(params)
	elif operation == "resave_resources":
		result = resave_resources(params)
	else:
		result = {"error": "Unknown operation: " + operation}

	print(JSON.stringify(result))
	quit(0)

func create_scene(params):
	var scene_path = params.get("scene_path")
	var root_node_type = params.get("root_node_type", "Node2D")
	
	if not scene_path:
		return {"error": "scene_path is required"}
		
	if FileAccess.file_exists(scene_path):
		return {"error": "File already exists: " + scene_path}
		
	var root = ClassDB.instantiate(root_node_type)
	if not root:
		return {"error": "Invalid root node type: " + root_node_type}
		
	root.name = scene_path.get_file().get_basename()
	
	var packed_scene = PackedScene.new()
	var result = packed_scene.pack(root)
	if result != OK:
		return {"error": "Failed to pack scene"}
		
	var save_result = ResourceSaver.save(packed_scene, scene_path)
	if save_result != OK:
		return {"error": "Failed to save scene"}
		
	return {"status": "success", "path": scene_path}

func add_node(params):
	var scene_path = params.get("scene_path")
	var parent_path = params.get("parent_node_path", ".")
	var node_type = params.get("node_type")
	var node_name = params.get("node_name")
	var properties = params.get("properties", {})
	
	if not scene_path or not node_type or not node_name:
		return {"error": "scene_path, node_type, and node_name are required"}
		
	var packed_scene = ResourceLoader.load(scene_path)
	if not packed_scene:
		return {"error": "Failed to load scene: " + scene_path}
		
	var root = packed_scene.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE)
	if not root:
		return {"error": "Failed to instantiate scene"}
		
	var parent = root.get_node_or_null(parent_path)
	if not parent:
		return {"error": "Parent node not found: " + parent_path}
		
	var new_node = ClassDB.instantiate(node_type)
	if not new_node:
		return {"error": "Invalid node type: " + node_type}
		
	new_node.name = node_name
	parent.add_child(new_node)
	new_node.owner = root
	
	for key in properties:
		new_node.set(key, properties[key])
		
	var new_packed_scene = PackedScene.new()
	new_packed_scene.pack(root)
	ResourceSaver.save(new_packed_scene, scene_path)
	
	return {"status": "success"}

func load_sprite(params):
	var scene_path = params.get("scene_path")
	var node_path = params.get("node_path")
	var texture_path = params.get("texture_path")
	
	if not scene_path or not node_path or not texture_path:
		return {"error": "scene_path, node_path, and texture_path are required"}
		
	var packed_scene = ResourceLoader.load(scene_path)
	if not packed_scene:
		return {"error": "Failed to load scene"}
		
	var root = packed_scene.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE)
	var node = root.get_node_or_null(node_path)
	
	if not node:
		return {"error": "Node not found"}
		
	if not (node is Sprite2D or node is Sprite3D):
		return {"error": "Node is not a Sprite"}
		
	var texture = ResourceLoader.load(texture_path)
	if not texture:
		return {"error": "Failed to load texture"}
		
	node.texture = texture
	
	var new_packed_scene = PackedScene.new()
	new_packed_scene.pack(root)
	ResourceSaver.save(new_packed_scene, scene_path)
	
	return {"status": "success"}

func save_scene(params):
	var scene_path = params.get("scene_path")
	var new_path = params.get("new_path")
	
	if not scene_path:
		return {"error": "scene_path is required"}
		
	if new_path:
		var packed_scene = ResourceLoader.load(scene_path)
		if not packed_scene:
			return {"error": "Failed to load scene"}
		ResourceSaver.save(packed_scene, new_path)
		return {"status": "success", "path": new_path}
	
	return {"status": "success", "path": scene_path}

func export_mesh_library(params):
	var scene_path = params.get("scene_path")
	var output_path = params.get("output_path")
	
	if not scene_path or not output_path:
		return {"error": "scene_path and output_path are required"}
		
	var packed_scene = ResourceLoader.load(scene_path)
	if not packed_scene:
		return {"error": "Failed to load scene"}
		
	var root = packed_scene.instantiate()
	var mesh_lib = MeshLibrary.new()
	
	var children = root.get_children()
	for child in children:
		if child is MeshInstance3D:
			var id = mesh_lib.get_last_unused_item_id()
			mesh_lib.create_item(id)
			mesh_lib.set_item_name(id, child.name)
			mesh_lib.set_item_mesh(id, child.mesh)
			
	ResourceSaver.save(mesh_lib, output_path)
	return {"status": "success"}

func get_uid(params):
	var file_path = params.get("file_path")
	if not file_path:
		return {"error": "file_path is required"}
		
	var id = ResourceLoader.get_resource_uid(file_path)
	if id == -1:
		return {"uid": null, "exists": FileAccess.file_exists(file_path)}
		
	return {"uid": ResourceUID.id_to_text(id)}

func resave_resources(params):
	var dir = DirAccess.open("res://")
	if dir:
		dir.list_dir_begin()
		var file_name = dir.get_next()
		while file_name != "":
			if not dir.current_is_dir():
				if file_name.ends_with(".tres") or file_name.ends_with(".tscn"):
					var res = ResourceLoader.load("res://" + file_name)
					if res:
						ResourceSaver.save(res, "res://" + file_name)
			file_name = dir.get_next()
			
	return {"status": "success"}
