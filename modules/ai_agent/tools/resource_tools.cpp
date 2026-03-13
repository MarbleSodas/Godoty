/**************************************************************************/
/*  resource_tools.cpp                                                    */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "resource_tools.h"

#include "core/io/dir_access.h"
#include "core/io/file_access.h"
#include "modules/ai_agent/ai_tool_registry.h"

#ifdef TOOLS_ENABLED
#include "editor/file_system/editor_file_system.h"
#endif

void ResourceTools::_bind_methods() {
	ClassDB::bind_static_method("ResourceTools", D_METHOD("register_tools"), &ResourceTools::register_tools);
}

void ResourceTools::register_tools() {
	AIToolRegistry *reg = AIToolRegistry::get_singleton();
	ERR_FAIL_NULL(reg);

	// read_file
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary path_prop;
		path_prop["type"] = "string";
		path_prop["description"] = "Path of the file to read (e.g., 'res://project.godot')";
		props["path"] = path_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("path");
		params["required"] = required;
		reg->register_tool("read_file", "Read the contents of a project file", params, callable_mp_static(&ResourceTools::tool_read_file));
	}

	// write_file
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary path_prop;
		path_prop["type"] = "string";
		path_prop["description"] = "Path of the file to write";
		props["path"] = path_prop;
		Dictionary content_prop;
		content_prop["type"] = "string";
		content_prop["description"] = "Content to write to the file";
		props["content"] = content_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("path");
		required.push_back("content");
		params["required"] = required;
		reg->register_tool("write_file", "Write content to a project file", params, callable_mp_static(&ResourceTools::tool_write_file), true);
	}

	// delete_file
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary path_prop;
		path_prop["type"] = "string";
		path_prop["description"] = "Path of the file to delete";
		props["path"] = path_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("path");
		params["required"] = required;
		reg->register_tool("delete_file", "Delete a file from the project", params, callable_mp_static(&ResourceTools::tool_delete_file), true);
	}

	// list_directory
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary path_prop;
		path_prop["type"] = "string";
		path_prop["description"] = "Directory path to list (default: 'res://')";
		props["path"] = path_prop;
		params["properties"] = props;
		reg->register_tool("list_directory", "List the contents of a project directory", params, callable_mp_static(&ResourceTools::tool_list_directory));
	}

	// search_files
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary query_prop;
		query_prop["type"] = "string";
		query_prop["description"] = "Text to search for in file contents";
		props["query"] = query_prop;
		Dictionary dir_prop;
		dir_prop["type"] = "string";
		dir_prop["description"] = "Directory to search in (default: 'res://')";
		props["directory"] = dir_prop;
		Dictionary ext_prop;
		ext_prop["type"] = "string";
		ext_prop["description"] = "File extension filter (e.g., 'gd', 'tscn')";
		props["extension"] = ext_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("query");
		params["required"] = required;
		reg->register_tool("search_files", "Search for text in project files", params, callable_mp_static(&ResourceTools::tool_search_files));
	}

	// move_file
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary from_prop;
		from_prop["type"] = "string";
		from_prop["description"] = "Current file path";
		props["from"] = from_prop;
		Dictionary to_prop;
		to_prop["type"] = "string";
		to_prop["description"] = "New file path";
		props["to"] = to_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("from");
		required.push_back("to");
		params["required"] = required;
		reg->register_tool("move_file", "Move or rename a project file", params, callable_mp_static(&ResourceTools::tool_move_file), true);
	}
}

Variant ResourceTools::tool_read_file(const Dictionary &p_args) {
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

Variant ResourceTools::tool_write_file(const Dictionary &p_args) {
	String path = p_args.get("path", "");
	String content = p_args.get("content", "");
	if (path.is_empty()) {
		return "Error: 'path' is required.";
	}

	// Ensure directory exists.
	String dir = path.get_base_dir();
	Ref<DirAccess> da = DirAccess::open("res://");
	if (da.is_valid() && !da->dir_exists(dir)) {
		da->make_dir_recursive(dir);
	}

	Ref<FileAccess> file = FileAccess::open(path, FileAccess::WRITE);
	if (file.is_null()) {
		return "Error: Cannot write to: " + path;
	}
	file->store_string(content);
	file->flush();

#ifdef TOOLS_ENABLED
	EditorFileSystem::get_singleton()->scan();
#endif
	return "File written: " + path;
}

Variant ResourceTools::tool_delete_file(const Dictionary &p_args) {
	String path = p_args.get("path", "");
	if (path.is_empty()) {
		return "Error: 'path' is required.";
	}

	Ref<DirAccess> da = DirAccess::open("res://");
	if (da.is_null() || !da->file_exists(path)) {
		return "Error: File not found: " + path;
	}

	Error err = da->remove(path);
	if (err != OK) {
		return "Error: Failed to delete: " + path;
	}

#ifdef TOOLS_ENABLED
	EditorFileSystem::get_singleton()->scan();
#endif
	return "Deleted: " + path;
}

Variant ResourceTools::tool_list_directory(const Dictionary &p_args) {
	String path = p_args.get("path", "res://");

	Ref<DirAccess> dir = DirAccess::open(path);
	if (dir.is_null()) {
		return "Error: Cannot open directory: " + path;
	}

	String result = "Contents of " + path + ":\n";
	dir->list_dir_begin();
	String item = dir->get_next();
	while (!item.is_empty()) {
		if (item != "." && item != "..") {
			if (dir->current_is_dir()) {
				result += "  [DIR] " + item + "/\n";
			} else {
				result += "  " + item + "\n";
			}
		}
		item = dir->get_next();
	}
	dir->list_dir_end();
	return result;
}

Variant ResourceTools::tool_search_files(const Dictionary &p_args) {
	String query = p_args.get("query", "");
	String directory = p_args.get("directory", "res://");
	String ext_filter = p_args.get("extension", "");

	if (query.is_empty()) {
		return "Error: 'query' is required.";
	}

	String results;
	int match_count = 0;
	const int MAX_MATCHES = 50;

	// Recursive file search.
	List<String> dirs_to_search;
	dirs_to_search.push_back(directory);

	while (!dirs_to_search.is_empty() && match_count < MAX_MATCHES) {
		String current_dir = dirs_to_search.front()->get();
		dirs_to_search.pop_front();

		Ref<DirAccess> dir = DirAccess::open(current_dir);
		if (dir.is_null()) {
			continue;
		}

		dir->list_dir_begin();
		String item = dir->get_next();
		while (!item.is_empty() && match_count < MAX_MATCHES) {
			if (item == "." || item == ".." || item.begins_with(".")) {
				item = dir->get_next();
				continue;
			}

			String full_path = current_dir.path_join(item);
			if (dir->current_is_dir()) {
				dirs_to_search.push_back(full_path);
			} else {
				// Check extension filter.
				if (!ext_filter.is_empty() && item.get_extension() != ext_filter) {
					item = dir->get_next();
					continue;
				}

				// Search file contents.
				Ref<FileAccess> file = FileAccess::open(full_path, FileAccess::READ);
				if (file.is_valid()) {
					String content = file->get_as_text();
					int pos = content.find(query);
					if (pos != -1) {
						// Find the line number.
						int line = content.substr(0, pos).get_slice_count("\n");
						results += full_path + ":" + itos(line) + "\n";
						match_count++;
					}
				}
			}
			item = dir->get_next();
		}
		dir->list_dir_end();
	}

	if (results.is_empty()) {
		return "No matches found for: " + query;
	}
	return "Found " + itos(match_count) + " matches:\n" + results;
}

Variant ResourceTools::tool_move_file(const Dictionary &p_args) {
	String from = p_args.get("from", "");
	String to = p_args.get("to", "");

	if (from.is_empty() || to.is_empty()) {
		return "Error: 'from' and 'to' are required.";
	}

	Ref<DirAccess> da = DirAccess::open("res://");
	if (da.is_null()) {
		return "Error: Cannot access project filesystem.";
	}

	Error err = da->rename(from, to);
	if (err != OK) {
		return "Error: Failed to move file: " + itos(err);
	}

#ifdef TOOLS_ENABLED
	EditorFileSystem::get_singleton()->scan();
#endif
	return "Moved: " + from + " -> " + to;
}
