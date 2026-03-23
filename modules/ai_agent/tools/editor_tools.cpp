/**************************************************************************/
/*  editor_tools.cpp                                                      */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "editor_tools.h"

#include "core/config/project_settings.h"
#include "core/input/shortcut.h"
#include "modules/ai_agent/ai_tool_registry.h"

#ifdef TOOLS_ENABLED
#include "editor/editor_interface.h"
#include "editor/editor_node.h"
#include "editor/editor_undo_redo_manager.h"
#include "editor/gui/editor_toaster.h"
#endif

void EditorTools::_bind_methods() {
	ClassDB::bind_static_method("EditorTools", D_METHOD("register_tools"), &EditorTools::register_tools);
}

void EditorTools::register_tools() {
	AIToolRegistry *reg = AIToolRegistry::get_singleton();
	ERR_FAIL_NULL(reg);

	// select_nodes
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary paths_prop;
		paths_prop["type"] = "array";
		paths_prop["description"] = "Array of NodePath strings to select";
		props["node_paths"] = paths_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("node_paths");
		params["required"] = required;
		reg->register_tool("select_nodes", "Select nodes in the editor by their paths", params, callable_mp_static(&EditorTools::tool_select_nodes), false, AIToolRegistry::EXECUTION_MUTATING_EDITOR, false,
				"Use when highlighting the relevant nodes in the editor will help confirm focus or guide the next action.",
				"a confirmation string with the number of selected nodes");
	}

	// set_project_setting
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary key_prop;
		key_prop["type"] = "string";
		key_prop["description"] = "Setting key (e.g., 'application/config/name')";
		props["key"] = key_prop;
		Dictionary val_prop;
		val_prop["description"] = "Value to set";
		props["value"] = val_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("key");
		required.push_back("value");
		params["required"] = required;
		reg->register_tool("set_project_setting", "Modify a project setting", params, callable_mp_static(&EditorTools::tool_set_project_setting), true, AIToolRegistry::EXECUTION_MUTATING_EDITOR);
	}

	// undo
	{
		Dictionary params;
		params["type"] = "object";
		params["properties"] = Dictionary();
		reg->register_tool("undo", "Undo the last action in the editor", params, callable_mp_static(&EditorTools::tool_undo), false, AIToolRegistry::EXECUTION_MUTATING_EDITOR);
	}

	// redo
	{
		Dictionary params;
		params["type"] = "object";
		params["properties"] = Dictionary();
		reg->register_tool("redo", "Redo the previously undone action", params, callable_mp_static(&EditorTools::tool_redo), false, AIToolRegistry::EXECUTION_MUTATING_EDITOR);
	}

	// run_project
	{
		Dictionary params;
		params["type"] = "object";
		params["properties"] = Dictionary();
		reg->register_tool("run_project", "Run the project (equivalent to pressing F5)", params, callable_mp_static(&EditorTools::tool_run_project), false, AIToolRegistry::EXECUTION_MUTATING_EDITOR);
	}

	// stop_project
	{
		Dictionary params;
		params["type"] = "object";
		params["properties"] = Dictionary();
		reg->register_tool("stop_project", "Stop the running project", params, callable_mp_static(&EditorTools::tool_stop_project), false, AIToolRegistry::EXECUTION_MUTATING_EDITOR);
	}

	// show_notification
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary msg_prop;
		msg_prop["type"] = "string";
		msg_prop["description"] = "Notification message to show";
		props["message"] = msg_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("message");
		params["required"] = required;
		reg->register_tool("show_notification", "Show a toast notification in the editor", params, callable_mp_static(&EditorTools::tool_show_notification), false, AIToolRegistry::EXECUTION_MUTATING_EDITOR);
	}
}

Variant EditorTools::tool_select_nodes(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	Array paths = p_args.get("node_paths", Array());
	Node *root = EditorInterface::get_singleton()->get_edited_scene_root();
	if (!root) {
		return "Error: No scene open.";
	}

	EditorSelection *selection = EditorInterface::get_singleton()->get_selection();
	selection->clear();

	int selected = 0;
	for (int i = 0; i < paths.size(); i++) {
		Node *node = root->get_node_or_null(NodePath(paths[i]));
		if (node) {
			selection->add_node(node);
			selected++;
		}
	}

	return "Selected " + itos(selected) + " node(s).";
#else
	return "Error: only available in editor builds.";
#endif
}

Variant EditorTools::tool_set_project_setting(const Dictionary &p_args) {
	String key = p_args.get("key", "");
	Variant value = p_args.get("value", Variant());

	if (key.is_empty()) {
		return "Error: 'key' is required.";
	}

	ProjectSettings::get_singleton()->set_setting(key, value);
	ProjectSettings::get_singleton()->save();
	return "Set project setting: " + key;
}

Variant EditorTools::tool_undo(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	EditorUndoRedoManager *undo_redo = EditorUndoRedoManager::get_singleton();
	if (undo_redo && undo_redo->has_undo()) {
		undo_redo->undo();
		return "Undo performed.";
	}
	return "Nothing to undo.";
#else
	return "Error: only available in editor builds.";
#endif
}

Variant EditorTools::tool_redo(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	EditorUndoRedoManager *undo_redo = EditorUndoRedoManager::get_singleton();
	if (undo_redo && undo_redo->has_redo()) {
		undo_redo->redo();
		return "Redo performed.";
	}
	return "Nothing to redo.";
#else
	return "Error: only available in editor builds.";
#endif
}

Variant EditorTools::tool_run_project(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	EditorInterface::get_singleton()->play_main_scene();
	return "Project started.";
#else
	return "Error: only available in editor builds.";
#endif
}

Variant EditorTools::tool_stop_project(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	EditorInterface::get_singleton()->stop_playing_scene();
	return "Project stopped.";
#else
	return "Error: only available in editor builds.";
#endif
}

Variant EditorTools::tool_show_notification(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	String message = p_args.get("message", "");
	EditorToaster::get_singleton()->popup_str(message);
	return "Notification shown.";
#else
	return "Error: only available in editor builds.";
#endif
}
