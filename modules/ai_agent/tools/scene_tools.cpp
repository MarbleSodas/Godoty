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

namespace {

} // namespace

void SceneTools::_bind_methods() {
	ClassDB::bind_static_method("SceneTools", D_METHOD("register_tools"), &SceneTools::register_tools);
}

String SceneTools::sanitize_ai_node_name(const String &p_requested_name, const String &p_type_name) {
	String resolved_name = p_requested_name.strip_edges();
	if (resolved_name.is_empty()) {
		resolved_name = p_type_name.strip_edges();
	}
	if (resolved_name.is_empty()) {
		resolved_name = "Node";
	}

	resolved_name = Node::adjust_name_casing(resolved_name);
	resolved_name = resolved_name.validate_node_name().strip_edges();
	if (resolved_name.is_empty()) {
		resolved_name = p_type_name.strip_edges();
		resolved_name = Node::adjust_name_casing(resolved_name);
		resolved_name = resolved_name.validate_node_name().strip_edges();
	}
	if (resolved_name.is_empty()) {
		resolved_name = "Node";
	}

	return resolved_name;
}

String SceneTools::resolve_ai_node_name(Node *p_parent, Node *p_candidate, const String &p_requested_name, const String &p_type_name) {
	String resolved_name = sanitize_ai_node_name(p_requested_name, p_type_name);
	if (p_parent && p_candidate) {
		resolved_name = p_parent->prevalidate_child_name(p_candidate, StringName(resolved_name));
		resolved_name = sanitize_ai_node_name(resolved_name, p_type_name);
	}
	if (resolved_name.is_empty()) {
		resolved_name = "Node";
	}
	return resolved_name;
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
		params["required"] = required;
		reg->register_tool("create_node", "Create a new node in the scene tree", params, callable_mp_static(&SceneTools::tool_create_node), true, AIToolRegistry::EXECUTION_MUTATING_SCENE, false,
				"Use after inspecting the target scene and parent node when you need to add a new node of a known type.",
				"a confirmation string with the created node type, resolved name, and parent path");
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
		reg->register_tool("delete_node", "Delete a node from the scene tree", params, callable_mp_static(&SceneTools::tool_delete_node), true, AIToolRegistry::EXECUTION_MUTATING_SCENE);
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
		reg->register_tool("rename_node", "Rename a node in the scene tree", params, callable_mp_static(&SceneTools::tool_rename_node), true, AIToolRegistry::EXECUTION_MUTATING_SCENE);
	}

	// reparent_node
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary node_prop;
		node_prop["type"] = "string";
		node_prop["description"] = "NodePath of the node to move.";
		props["node_path"] = node_prop;
		Dictionary parent_prop;
		parent_prop["type"] = "string";
		parent_prop["description"] = "NodePath of the new parent.";
		props["new_parent_path"] = parent_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("node_path");
		required.push_back("new_parent_path");
		params["required"] = required;
		reg->register_tool("reparent_node", "Move a node under a different parent in the scene tree", params, callable_mp_static(&SceneTools::tool_reparent_node), true, AIToolRegistry::EXECUTION_MUTATING_SCENE, false,
				"Use when the scene structure is correct except for which parent currently owns a node.",
				"a confirmation string with the moved node and its new parent path");
	}

	// duplicate_node
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary node_prop;
		node_prop["type"] = "string";
		node_prop["description"] = "NodePath of the node to duplicate.";
		props["node_path"] = node_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("node_path");
		params["required"] = required;
		reg->register_tool("duplicate_node", "Duplicate a node in the scene tree", params, callable_mp_static(&SceneTools::tool_duplicate_node), true, AIToolRegistry::EXECUTION_MUTATING_SCENE, false,
				"Use when you need a copy of an existing node hierarchy as a starting point.",
				"a confirmation string with the original node and the duplicate name");
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
		reg->register_tool("set_node_property", "Set a property on a node", params, callable_mp_static(&SceneTools::tool_set_node_property), true, AIToolRegistry::EXECUTION_MUTATING_SCENE, false,
				"Use after inspect_node or get_class_reference confirms the property name and expected value type.",
				"a confirmation string with the property, value, and target node");
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
		reg->register_tool("get_node_property", "Get the value of a property on a node", params, callable_mp_static(&SceneTools::tool_get_node_property), false, AIToolRegistry::EXECUTION_READ_ONLY, true,
				"Use for a quick value check when you already know the property name and only need the current live value.",
				"a short string containing the property name and current value");
	}

	// connect_signal
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary source_prop;
		source_prop["type"] = "string";
		source_prop["description"] = "NodePath of the signal source node.";
		props["source_path"] = source_prop;
		Dictionary signal_prop;
		signal_prop["type"] = "string";
		signal_prop["description"] = "Signal name to connect.";
		props["signal_name"] = signal_prop;
		Dictionary target_prop;
		target_prop["type"] = "string";
		target_prop["description"] = "NodePath of the target node.";
		props["target_path"] = target_prop;
		Dictionary method_prop;
		method_prop["type"] = "string";
		method_prop["description"] = "Method name to call on the target node.";
		props["method_name"] = method_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("source_path");
		required.push_back("signal_name");
		required.push_back("target_path");
		required.push_back("method_name");
		params["required"] = required;
		reg->register_tool("connect_signal", "Connect a signal between nodes in the edited scene", params, callable_mp_static(&SceneTools::tool_connect_signal), true, AIToolRegistry::EXECUTION_MUTATING_SCENE, false,
				"Use after get_class_reference or inspect_node confirms the signal and target method you want to wire together.",
				"a confirmation string describing the created connection");
	}

	// disconnect_signal
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary source_prop;
		source_prop["type"] = "string";
		source_prop["description"] = "NodePath of the signal source node.";
		props["source_path"] = source_prop;
		Dictionary signal_prop;
		signal_prop["type"] = "string";
		signal_prop["description"] = "Signal name to disconnect.";
		props["signal_name"] = signal_prop;
		Dictionary target_prop;
		target_prop["type"] = "string";
		target_prop["description"] = "NodePath of the target node.";
		props["target_path"] = target_prop;
		Dictionary method_prop;
		method_prop["type"] = "string";
		method_prop["description"] = "Method name previously connected on the target node.";
		props["method_name"] = method_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("source_path");
		required.push_back("signal_name");
		required.push_back("target_path");
		required.push_back("method_name");
		params["required"] = required;
		reg->register_tool("disconnect_signal", "Disconnect a signal between nodes in the edited scene", params, callable_mp_static(&SceneTools::tool_disconnect_signal), true, AIToolRegistry::EXECUTION_MUTATING_SCENE, false,
				"Use when a signal connection exists but should be removed or replaced.",
				"a confirmation string describing the removed connection");
	}

	// add_to_group
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary node_prop;
		node_prop["type"] = "string";
		node_prop["description"] = "NodePath of the node to add to a group.";
		props["node_path"] = node_prop;
		Dictionary group_prop;
		group_prop["type"] = "string";
		group_prop["description"] = "Group name to add to the node.";
		props["group_name"] = group_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("node_path");
		required.push_back("group_name");
		params["required"] = required;
		reg->register_tool("add_to_group", "Add a node to a persistent group", params, callable_mp_static(&SceneTools::tool_add_to_group), true, AIToolRegistry::EXECUTION_MUTATING_SCENE, false,
				"Use when a node should participate in a known persistent group-based system.",
				"a confirmation string with the node and group name");
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
		reg->register_tool("save_scene", "Save the current scene to disk", params, callable_mp_static(&SceneTools::tool_save_scene), true, AIToolRegistry::EXECUTION_MUTATING_FILE, false,
				"Use after scene mutations when you need to persist the current edited scene to its existing path or a new path.",
				"a confirmation string with the saved scene path");
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
		reg->register_tool("create_scene", "Create a new scene with a specified root node type", params, callable_mp_static(&SceneTools::tool_create_scene), true, AIToolRegistry::EXECUTION_MUTATING_SCENE, false,
				"Use when starting a brand-new scene rooted at a known node type.",
				"a confirmation string with the root type and resolved root name");
	}

	// instantiate_scene
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary scene_prop;
		scene_prop["type"] = "string";
		scene_prop["description"] = "Path of the scene resource to instantiate.";
		props["scene_path"] = scene_prop;
		Dictionary parent_prop;
		parent_prop["type"] = "string";
		parent_prop["description"] = "Optional parent NodePath for the new instance (default: '.').";
		props["parent_path"] = parent_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("scene_path");
		params["required"] = required;
		reg->register_tool("instantiate_scene", "Instantiate a packed scene into the edited scene tree", params, callable_mp_static(&SceneTools::tool_instantiate_scene), true, AIToolRegistry::EXECUTION_MUTATING_SCENE, false,
				"Use when you want to add a reusable scene instance under a chosen parent in the current edited scene.",
				"a confirmation string with the instantiated scene path and parent path");
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

	String resolved_name = resolve_ai_node_name(parent, new_node, name, type);
	new_node->set_name(resolved_name);

	// Use UndoRedo for editor integration.
	EditorUndoRedoManager *undo_redo = EditorUndoRedoManager::get_singleton();
	undo_redo->create_action("AI: Create " + type + " '" + resolved_name + "'");
	undo_redo->add_do_method(parent, "add_child", new_node, true);
	undo_redo->add_do_method(new_node, "set_owner", edited_root);
	undo_redo->add_undo_method(parent, "remove_child", new_node);
	undo_redo->add_do_reference(new_node);
	undo_redo->commit_action();

	return "Created " + type + " '" + resolved_name + "' as child of " + String(parent->get_path());
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
	if (new_name.strip_edges().is_empty()) {
		return "Error: 'new_name' must not be empty.";
	}

	Node *root = EditorInterface::get_singleton()->get_edited_scene_root();
	if (!root) {
		return "Error: No scene is currently open.";
	}

	Node *node = root->get_node_or_null(NodePath(node_path));
	if (!node) {
		return "Error: Node not found at path: " + node_path;
	}

	Node *parent = node->get_parent();
	if (!parent) {
		return "Error: Cannot rename a node without a parent.";
	}

	const String resolved_name = resolve_ai_node_name(parent, node, new_name, node->get_class());
	String old_name = node->get_name();
	EditorUndoRedoManager *undo_redo = EditorUndoRedoManager::get_singleton();
	undo_redo->create_action("AI: Rename '" + old_name + "' to '" + resolved_name + "'");
	undo_redo->add_do_method(node, "set_name", resolved_name);
	undo_redo->add_undo_method(node, "set_name", old_name);
	undo_redo->commit_action();

	return "Renamed '" + old_name + "' to '" + resolved_name + "'";
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
	String resolved_name = sanitize_ai_node_name(root_name, root_type);
	root->set_name(resolved_name);

	EditorInterface::get_singleton()->edit_node(root);
	return "Created new scene with " + root_type + " root named '" + resolved_name + "'";
#else
	return "Error: only available in editor builds.";
#endif
}
