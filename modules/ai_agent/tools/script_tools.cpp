/**************************************************************************/
/*  script_tools.cpp                                                      */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "script_tools.h"

#include "core/io/file_access.h"
#include "core/io/resource_loader.h"
#include "core/io/resource_saver.h"
#include "modules/ai_agent/ai_tool_registry.h"
#include "scene/main/node.h"

#ifdef TOOLS_ENABLED
#include "editor/editor_interface.h"
#include "editor/file_system/editor_file_system.h"
#include "editor/editor_undo_redo_manager.h"
#include "editor/script/script_editor_plugin.h"
#endif

void ScriptTools::_bind_methods() {
	ClassDB::bind_static_method("ScriptTools", D_METHOD("register_tools"), &ScriptTools::register_tools);
}

void ScriptTools::register_tools() {
	AIToolRegistry *reg = AIToolRegistry::get_singleton();
	ERR_FAIL_NULL(reg);

	// create_script
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary path_prop;
		path_prop["type"] = "string";
		path_prop["description"] = "File path for the script (e.g., 'res://scripts/player.gd')";
		props["path"] = path_prop;
		Dictionary content_prop;
		content_prop["type"] = "string";
		content_prop["description"] = "Full source code content for the script";
		props["content"] = content_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("path");
		required.push_back("content");
		params["required"] = required;
		reg->register_tool("create_script", "Create a new script file with the specified content", params, callable_mp_static(&ScriptTools::tool_create_script), true);
	}

	// edit_script
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary path_prop;
		path_prop["type"] = "string";
		path_prop["description"] = "Path of the script to edit";
		props["path"] = path_prop;
		Dictionary content_prop;
		content_prop["type"] = "string";
		content_prop["description"] = "New full content to replace the script with";
		props["content"] = content_prop;
		Dictionary find_prop;
		find_prop["type"] = "string";
		find_prop["description"] = "Text to find (for find/replace mode)";
		props["find"] = find_prop;
		Dictionary replace_prop;
		replace_prop["type"] = "string";
		replace_prop["description"] = "Replacement text (for find/replace mode)";
		props["replace"] = replace_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("path");
		params["required"] = required;
		reg->register_tool("edit_script", "Edit an existing script — full replacement or find/replace", params, callable_mp_static(&ScriptTools::tool_edit_script), true);
	}

	// attach_script
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary node_prop;
		node_prop["type"] = "string";
		node_prop["description"] = "NodePath of the node to attach the script to";
		props["node_path"] = node_prop;
		Dictionary script_prop;
		script_prop["type"] = "string";
		script_prop["description"] = "Path of the script file";
		props["script_path"] = script_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("node_path");
		required.push_back("script_path");
		params["required"] = required;
		reg->register_tool("attach_script", "Attach a script to a node", params, callable_mp_static(&ScriptTools::tool_attach_script), true);
	}

	// get_script_content
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary path_prop;
		path_prop["type"] = "string";
		path_prop["description"] = "Path of the script to read";
		props["path"] = path_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("path");
		params["required"] = required;
		reg->register_tool("get_script_content", "Read the full source code of a script file", params, callable_mp_static(&ScriptTools::tool_get_script_content));
	}

	// open_script
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary path_prop;
		path_prop["type"] = "string";
		path_prop["description"] = "Path of the script to open in the editor";
		props["path"] = path_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("path");
		params["required"] = required;
		reg->register_tool("open_script", "Open a script file in the script editor", params, callable_mp_static(&ScriptTools::tool_open_script));
	}
}

Variant ScriptTools::tool_create_script(const Dictionary &p_args) {
	String path = p_args.get("path", "");
	String content = p_args.get("content", "");

	if (path.is_empty()) {
		return "Error: 'path' is required.";
	}

	Ref<FileAccess> file = FileAccess::open(path, FileAccess::WRITE);
	if (file.is_null()) {
		return "Error: Cannot create file: " + path;
	}
	file->store_string(content);
	file->flush();

#ifdef TOOLS_ENABLED
	// Trigger reimport so editor picks up the new file.
	EditorFileSystem::get_singleton()->scan();
#endif

	return "Created script: " + path;
}

Variant ScriptTools::tool_edit_script(const Dictionary &p_args) {
	String path = p_args.get("path", "");
	if (path.is_empty()) {
		return "Error: 'path' is required.";
	}

	// Read existing content.
	Ref<FileAccess> read_file = FileAccess::open(path, FileAccess::READ);
	if (read_file.is_null()) {
		return "Error: Script not found: " + path;
	}
	String old_content = read_file->get_as_text();
	read_file.unref();

	String new_content;
	if (p_args.has("content")) {
		// Full replacement mode.
		new_content = p_args["content"];
	} else if (p_args.has("find") && p_args.has("replace")) {
		// Find/replace mode.
		String find = p_args["find"];
		String replace = p_args["replace"];
		new_content = old_content.replace(find, replace);
		if (new_content == old_content) {
			return "Warning: Find text not found in script. No changes made.";
		}
	} else {
		return "Error: Provide either 'content' for full replacement or 'find'/'replace' for find/replace.";
	}

	Ref<FileAccess> write_file = FileAccess::open(path, FileAccess::WRITE);
	if (write_file.is_null()) {
		return "Error: Cannot write to file: " + path;
	}
	write_file->store_string(new_content);
	write_file->flush();

#ifdef TOOLS_ENABLED
	// Reload the script in the editor.
	Ref<Script> script = ResourceLoader::load(path, "", ResourceFormatLoader::CACHE_MODE_IGNORE);
	if (script.is_valid()) {
		script->set_source_code(new_content);
		script->reload(true);
	}
#endif

	return "Script updated: " + path;
}

Variant ScriptTools::tool_attach_script(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	String node_path = p_args.get("node_path", "");
	String script_path = p_args.get("script_path", "");

	Node *root = EditorInterface::get_singleton()->get_edited_scene_root();
	if (!root) {
		return "Error: No scene open.";
	}

	Node *node = root->get_node_or_null(NodePath(node_path));
	if (!node) {
		return "Error: Node not found: " + node_path;
	}

	Ref<Script> script = ResourceLoader::load(script_path);
	if (script.is_null()) {
		return "Error: Script not found: " + script_path;
	}

	Ref<Script> old_script = node->get_script();
	EditorUndoRedoManager *undo_redo = EditorUndoRedoManager::get_singleton();
	undo_redo->create_action("AI: Attach script '" + script_path + "'");
	undo_redo->add_do_method(node, "set_script", script);
	undo_redo->add_undo_method(node, "set_script", old_script);
	undo_redo->commit_action();

	return "Attached '" + script_path + "' to " + node_path;
#else
	return "Error: only available in editor builds.";
#endif
}

Variant ScriptTools::tool_detach_script(const Dictionary &p_args) {
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

	Ref<Script> old_script = node->get_script();
	EditorUndoRedoManager *undo_redo = EditorUndoRedoManager::get_singleton();
	undo_redo->create_action("AI: Detach script from '" + node->get_name() + "'");
	undo_redo->add_do_method(node, "set_script", Variant());
	undo_redo->add_undo_method(node, "set_script", old_script);
	undo_redo->commit_action();

	return "Detached script from " + node_path;
#else
	return "Error: only available in editor builds.";
#endif
}

Variant ScriptTools::tool_open_script(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	String path = p_args.get("path", "");
	if (path.is_empty()) {
		return "Error: 'path' is required.";
	}

	Ref<Script> script = ResourceLoader::load(path);
	if (script.is_null()) {
		return "Error: Script not found: " + path;
	}

	EditorInterface::get_singleton()->edit_resource(script);
	return "Opened script: " + path;
#else
	return "Error: only available in editor builds.";
#endif
}

Variant ScriptTools::tool_get_script_content(const Dictionary &p_args) {
	String path = p_args.get("path", "");
	if (path.is_empty()) {
		return "Error: 'path' is required.";
	}

	Ref<FileAccess> file = FileAccess::open(path, FileAccess::READ);
	if (file.is_null()) {
		return "Error: File not found: " + path;
	}
	return file->get_as_text();
}
