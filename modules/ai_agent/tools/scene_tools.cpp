/**************************************************************************/
/*  scene_tools.cpp                                                       */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "scene_tools.h"

#include "core/config/project_settings.h"
#include "core/io/resource_saver.h"
#include "modules/ai_agent/ai_tool_registry.h"
#include "scene/main/node.h"
#include "scene/main/scene_tree.h"
#include "scene/resources/packed_scene.h"

#ifdef TOOLS_ENABLED
#include "editor/editor_interface.h"
#include "editor/editor_node.h"
#include "editor/editor_undo_redo_manager.h"
#endif

void SceneTools::_bind_methods() {
	ClassDB::bind_static_method("SceneTools", D_METHOD("register_tools"), &SceneTools::register_tools);
}

void SceneTools::register_tools() {
	AIToolRegistry *reg = AIToolRegistry::get_singleton();
	ERR_FAIL_NULL(reg);

	// create_node
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary type_prop;
		type_prop["type"] = "string";
		type_prop["description"] = "The node type to create (e.g., 'Sprite2D', 'CharacterBody3D')";
		props["type"] = type_prop;
		Dictionary name_prop;
		name_prop["type"] = "string";
		name_prop["description"] = "Name for the new node";
		props["name"] = name_prop;
		Dictionary parent_prop;
		parent_prop["type"] = "string";
		parent_prop["description"] = "NodePath of the parent (use '.' for scene root)";
		props["parent_path"] = parent_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("type");
		required.push_back("name");
		params["required"] = required;
		reg->register_tool("create_node", "Create a new node in the scene tree", params, callable_mp_static(&SceneTools::tool_create_node), true);
	}

	// delete_node
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary path_prop;
		path_prop["type"] = "string";
		path_prop["description"] = "NodePath of the node to delete";
		props["node_path"] = path_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("node_path");
		params["required"] = required;
		reg->register_tool("delete_node", "Delete a node from the scene tree", params, callable_mp_static(&SceneTools::tool_delete_node), true);
	}

	// rename_node
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary path_prop;
		path_prop["type"] = "string";
		path_prop["description"] = "NodePath of the node to rename";
		props["node_path"] = path_prop;
		Dictionary name_prop;
		name_prop["type"] = "string";
		name_prop["description"] = "New name for the node";
		props["new_name"] = name_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("node_path");
		required.push_back("new_name");
		params["required"] = required;
		reg->register_tool("rename_node", "Rename a node in the scene tree", params, callable_mp_static(&SceneTools::tool_rename_node), true);
	}

	// set_node_property
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary path_prop;
		path_prop["type"] = "string";
		path_prop["description"] = "NodePath of the node";
		props["node_path"] = path_prop;
		Dictionary prop_prop;
		prop_prop["type"] = "string";
		prop_prop["description"] = "Property name to set";
		props["property"] = prop_prop;
		Dictionary val_prop;
		val_prop["description"] = "Value to set the property to";
		props["value"] = val_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("node_path");
		required.push_back("property");
		required.push_back("value");
		params["required"] = required;
		reg->register_tool("set_node_property", "Set a property on a node", params, callable_mp_static(&SceneTools::tool_set_node_property), true);
	}

	// get_node_property
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary path_prop;
		path_prop["type"] = "string";
		path_prop["description"] = "NodePath of the node";
		props["node_path"] = path_prop;
		Dictionary prop_prop;
		prop_prop["type"] = "string";
		prop_prop["description"] = "Property name to get";
		props["property"] = prop_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("node_path");
		required.push_back("property");
		params["required"] = required;
		reg->register_tool("get_node_property", "Get the value of a property on a node", params, callable_mp_static(&SceneTools::tool_get_node_property));
	}

	// save_scene
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary path_prop;
		path_prop["type"] = "string";
		path_prop["description"] = "Optional file path to save to (leave empty for current path)";
		props["path"] = path_prop;
		params["properties"] = props;
		reg->register_tool("save_scene", "Save the current scene to disk", params, callable_mp_static(&SceneTools::tool_save_scene), true);
	}

	// create_scene
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary root_type;
		root_type["type"] = "string";
		root_type["description"] = "Type of root node (e.g., 'Node2D', 'Node3D', 'Control')";
		props["root_type"] = root_type;
		Dictionary root_name;
		root_name["type"] = "string";
		root_name["description"] = "Name for the root node";
		props["root_name"] = root_name;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("root_type");
		params["required"] = required;
		reg->register_tool("create_scene", "Create a new scene with a specified root node type", params, callable_mp_static(&SceneTools::tool_create_scene), true);
	}
}

Variant SceneTools::tool_create_node(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	String type = p_args.get("type", "");
	String name = p_args.get("name", type);
	String parent_path = p_args.get("parent_path", ".");

	if (type.is_empty()) {
		return "Error: 'type' is required.";
	}

	Node *edited_root = EditorInterface::get_singleton()->get_edited_scene_root();
	if (!edited_root) {
		return "Error: No scene is currently open.";
	}

	// Find parent node.
	Node *parent = (parent_path == "." || parent_path.is_empty()) ? edited_root : edited_root->get_node_or_null(NodePath(parent_path));
	if (!parent) {
		return "Error: Parent node not found at path: " + parent_path;
	}

	// Create the node.
	Object *obj = ClassDB::instantiate(type);
	Node *new_node = Object::cast_to<Node>(obj);
	if (!new_node) {
		if (obj) {
			memdelete(obj);
		}
		return "Error: '" + type + "' is not a valid Node type.";
	}

	new_node->set_name(name);

	// Use UndoRedo for editor integration.
	EditorUndoRedoManager *undo_redo = EditorUndoRedoManager::get_singleton();
	undo_redo->create_action("AI: Create " + type + " '" + name + "'");
	undo_redo->add_do_method(parent, "add_child", new_node, true);
	undo_redo->add_do_method(new_node, "set_owner", edited_root);
	undo_redo->add_undo_method(parent, "remove_child", new_node);
	undo_redo->add_do_reference(new_node);
	undo_redo->commit_action();

	return "Created " + type + " '" + name + "' as child of " + String(parent->get_path());
#else
	return "Error: Scene tools are only available in editor builds.";
#endif
}

Variant SceneTools::tool_delete_node(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	String node_path = p_args.get("node_path", "");
	if (node_path.is_empty()) {
		return "Error: 'node_path' is required.";
	}

	Node *root = EditorInterface::get_singleton()->get_edited_scene_root();
	if (!root) {
		return "Error: No scene is currently open.";
	}

	Node *node = root->get_node_or_null(NodePath(node_path));
	if (!node) {
		return "Error: Node not found at path: " + node_path;
	}

	if (node == root) {
		return "Error: Cannot delete the root node.";
	}

	Node *parent = node->get_parent();
	EditorUndoRedoManager *undo_redo = EditorUndoRedoManager::get_singleton();
	undo_redo->create_action("AI: Delete '" + node->get_name() + "'");
	undo_redo->add_do_method(parent, "remove_child", node);
	undo_redo->add_undo_method(parent, "add_child", node, true);
	undo_redo->add_undo_method(node, "set_owner", root);
	undo_redo->add_undo_reference(node);
	undo_redo->commit_action();

	return "Deleted node: " + node_path;
#else
	return "Error: Scene tools are only available in editor builds.";
#endif
}

Variant SceneTools::tool_rename_node(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	String node_path = p_args.get("node_path", "");
	String new_name = p_args.get("new_name", "");

	Node *root = EditorInterface::get_singleton()->get_edited_scene_root();
	if (!root) {
		return "Error: No scene is currently open.";
	}

	Node *node = root->get_node_or_null(NodePath(node_path));
	if (!node) {
		return "Error: Node not found at path: " + node_path;
	}

	String old_name = node->get_name();
	EditorUndoRedoManager *undo_redo = EditorUndoRedoManager::get_singleton();
	undo_redo->create_action("AI: Rename '" + old_name + "' to '" + new_name + "'");
	undo_redo->add_do_method(node, "set_name", new_name);
	undo_redo->add_undo_method(node, "set_name", old_name);
	undo_redo->commit_action();

	return "Renamed '" + old_name + "' to '" + new_name + "'";
#else
	return "Error: Scene tools are only available in editor builds.";
#endif
}

Variant SceneTools::tool_reparent_node(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	String node_path = p_args.get("node_path", "");
	String new_parent_path = p_args.get("new_parent_path", "");

	Node *root = EditorInterface::get_singleton()->get_edited_scene_root();
	if (!root) {
		return "Error: No scene is currently open.";
	}

	Node *node = root->get_node_or_null(NodePath(node_path));
	Node *new_parent = root->get_node_or_null(NodePath(new_parent_path));
	if (!node) {
		return "Error: Node not found: " + node_path;
	}
	if (!new_parent) {
		return "Error: New parent not found: " + new_parent_path;
	}

	Node *old_parent = node->get_parent();
	EditorUndoRedoManager *undo_redo = EditorUndoRedoManager::get_singleton();
	undo_redo->create_action("AI: Reparent '" + node->get_name() + "'");
	undo_redo->add_do_method(old_parent, "remove_child", node);
	undo_redo->add_do_method(new_parent, "add_child", node, true);
	undo_redo->add_do_method(node, "set_owner", root);
	undo_redo->add_undo_method(new_parent, "remove_child", node);
	undo_redo->add_undo_method(old_parent, "add_child", node, true);
	undo_redo->add_undo_method(node, "set_owner", root);
	undo_redo->commit_action();

	return "Reparented '" + node->get_name() + "' to " + new_parent_path;
#else
	return "Error: only available in editor builds.";
#endif
}

Variant SceneTools::tool_duplicate_node(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	String node_path = p_args.get("node_path", "");
	Node *root = EditorInterface::get_singleton()->get_edited_scene_root();
	if (!root) {
		return "Error: No scene open.";
	}
	Node *node = root->get_node_or_null(NodePath(node_path));
	if (!node) {
		return "Error: Node not found: " + node_path;
	}

	Node *dup = node->duplicate();
	Node *parent = node->get_parent();

	EditorUndoRedoManager *undo_redo = EditorUndoRedoManager::get_singleton();
	undo_redo->create_action("AI: Duplicate '" + node->get_name() + "'");
	undo_redo->add_do_method(parent, "add_child", dup, true);
	undo_redo->add_do_method(dup, "set_owner", root);
	undo_redo->add_undo_method(parent, "remove_child", dup);
	undo_redo->add_do_reference(dup);
	undo_redo->commit_action();

	return "Duplicated '" + node->get_name() + "' as '" + dup->get_name() + "'";
#else
	return "Error: only available in editor builds.";
#endif
}

Variant SceneTools::tool_set_node_property(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	String node_path = p_args.get("node_path", "");
	String property = p_args.get("property", "");
	Variant value = p_args.get("value", Variant());

	Node *root = EditorInterface::get_singleton()->get_edited_scene_root();
	if (!root) {
		return "Error: No scene open.";
	}
	Node *node = root->get_node_or_null(NodePath(node_path));
	if (!node) {
		return "Error: Node not found: " + node_path;
	}

	Variant old_value = node->get(property);
	EditorUndoRedoManager *undo_redo = EditorUndoRedoManager::get_singleton();
	undo_redo->create_action("AI: Set " + property + " on '" + node->get_name() + "'");
	undo_redo->add_do_method(node, "set", property, value);
	undo_redo->add_undo_method(node, "set", property, old_value);
	undo_redo->commit_action();

	return "Set " + property + " = " + String(value) + " on " + node->get_name();
#else
	return "Error: only available in editor builds.";
#endif
}

Variant SceneTools::tool_get_node_property(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	String node_path = p_args.get("node_path", "");
	String property = p_args.get("property", "");

	Node *root = EditorInterface::get_singleton()->get_edited_scene_root();
	if (!root) {
		return "Error: No scene open.";
	}
	Node *node = root->get_node_or_null(NodePath(node_path));
	if (!node) {
		return "Error: Node not found: " + node_path;
	}

	Variant val = node->get(property);
	return property + " = " + String(val);
#else
	return "Error: only available in editor builds.";
#endif
}

Variant SceneTools::tool_connect_signal(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	String source_path = p_args.get("source_path", "");
	String signal_name = p_args.get("signal_name", "");
	String target_path = p_args.get("target_path", "");
	String method_name = p_args.get("method_name", "");

	Node *root = EditorInterface::get_singleton()->get_edited_scene_root();
	if (!root) {
		return "Error: No scene open.";
	}
	Node *source = root->get_node_or_null(NodePath(source_path));
	Node *target = root->get_node_or_null(NodePath(target_path));
	if (!source || !target) {
		return "Error: Source or target node not found.";
	}

	Error err = source->connect(signal_name, Callable(target, method_name));
	if (err != OK) {
		return "Error: Failed to connect signal: " + itos(err);
	}
	return "Connected " + source_path + "." + signal_name + " -> " + target_path + "." + method_name;
#else
	return "Error: only available in editor builds.";
#endif
}

Variant SceneTools::tool_disconnect_signal(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	String source_path = p_args.get("source_path", "");
	String signal_name = p_args.get("signal_name", "");
	String target_path = p_args.get("target_path", "");
	String method_name = p_args.get("method_name", "");

	Node *root = EditorInterface::get_singleton()->get_edited_scene_root();
	if (!root) {
		return "Error: No scene open.";
	}
	Node *source = root->get_node_or_null(NodePath(source_path));
	Node *target = root->get_node_or_null(NodePath(target_path));
	if (!source || !target) {
		return "Error: Source or target node not found.";
	}

	source->disconnect(signal_name, Callable(target, method_name));
	return "Disconnected " + source_path + "." + signal_name + " -> " + target_path + "." + method_name;
#else
	return "Error: only available in editor builds.";
#endif
}

Variant SceneTools::tool_add_to_group(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	String node_path = p_args.get("node_path", "");
	String group_name = p_args.get("group_name", "");

	Node *root = EditorInterface::get_singleton()->get_edited_scene_root();
	if (!root) {
		return "Error: No scene open.";
	}
	Node *node = root->get_node_or_null(NodePath(node_path));
	if (!node) {
		return "Error: Node not found: " + node_path;
	}

	node->add_to_group(group_name, true);
	return "Added '" + node->get_name() + "' to group '" + group_name + "'";
#else
	return "Error: only available in editor builds.";
#endif
}

Variant SceneTools::tool_instantiate_scene(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	String scene_path = p_args.get("scene_path", "");
	String parent_path = p_args.get("parent_path", ".");

	Node *root = EditorInterface::get_singleton()->get_edited_scene_root();
	if (!root) {
		return "Error: No scene open.";
	}
	Node *parent = (parent_path == "." || parent_path.is_empty()) ? root : root->get_node_or_null(NodePath(parent_path));
	if (!parent) {
		return "Error: Parent not found: " + parent_path;
	}

	Ref<PackedScene> packed = ResourceLoader::load(scene_path);
	if (packed.is_null()) {
		return "Error: Scene not found: " + scene_path;
	}

	Node *instance = packed->instantiate();
	if (!instance) {
		return "Error: Failed to instantiate scene.";
	}

	EditorUndoRedoManager *undo_redo = EditorUndoRedoManager::get_singleton();
	undo_redo->create_action("AI: Instantiate " + scene_path);
	undo_redo->add_do_method(parent, "add_child", instance, true);
	undo_redo->add_do_method(instance, "set_owner", root);
	undo_redo->add_undo_method(parent, "remove_child", instance);
	undo_redo->add_do_reference(instance);
	undo_redo->commit_action();

	return "Instantiated '" + scene_path + "' as child of " + String(parent->get_path());
#else
	return "Error: only available in editor builds.";
#endif
}

Variant SceneTools::tool_save_scene(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	Node *root = EditorInterface::get_singleton()->get_edited_scene_root();
	if (!root) {
		return "Error: No scene open.";
	}

	String path = p_args.get("path", root->get_scene_file_path());
	if (path.is_empty()) {
		return "Error: No save path specified and scene has no existing path.";
	}

	Ref<PackedScene> packed;
	packed.instantiate();
	packed->pack(root);
	Error err = ResourceSaver::save(packed, path);
	if (err != OK) {
		return "Error: Failed to save scene: " + itos(err);
	}
	return "Scene saved to: " + path;
#else
	return "Error: only available in editor builds.";
#endif
}

Variant SceneTools::tool_create_scene(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	String root_type = p_args.get("root_type", "Node2D");
	String root_name = p_args.get("root_name", root_type);

	Object *obj = ClassDB::instantiate(root_type);
	Node *root = Object::cast_to<Node>(obj);
	if (!root) {
		if (obj) {
			memdelete(obj);
		}
		return "Error: '" + root_type + "' is not a valid Node type.";
	}
	root->set_name(root_name);

	EditorInterface::get_singleton()->edit_node(root);
	return "Created new scene with " + root_type + " root named '" + root_name + "'";
#else
	return "Error: only available in editor builds.";
#endif
}
