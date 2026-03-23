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
#include "modules/regex/regex.h"

#ifdef TOOLS_ENABLED
#include "editor/file_system/editor_file_system.h"
#endif

namespace {

constexpr int MAX_GREP_RESULTS_LIMIT = 200;
constexpr int MAX_GREP_CONTEXT_LIMIT = 3;

struct GrepOptions {
	String pattern;
	String directory = "res://";
	String glob;
	bool use_regex = false;
	bool case_sensitive = false;
	int max_results = 100;
	int context_lines = 0;
};

String _normalize_search_line(const String &p_line) {
	String line = p_line;
	if (line.ends_with("\r")) {
		line = line.substr(0, line.length() - 1);
	}
	return line;
}

bool _path_matches_glob(const String &p_path, const String &p_glob, bool p_case_sensitive) {
	if (p_glob.is_empty()) {
		return true;
	}

	const String stripped_path = p_path.trim_prefix("res://");
	const String file_name = p_path.get_file();
	if (p_case_sensitive) {
		return p_path.match(p_glob) || stripped_path.match(p_glob) || file_name.match(p_glob);
	}
	return p_path.matchn(p_glob) || stripped_path.matchn(p_glob) || file_name.matchn(p_glob);
}

bool _line_matches_search(const String &p_line, const GrepOptions &p_options, const Ref<RegEx> &p_regex) {
	if (p_options.use_regex) {
		return p_regex.is_valid() && p_regex->search(p_line).is_valid();
	}
	return p_options.case_sensitive ? p_line.find(p_options.pattern) != -1 : p_line.findn(p_options.pattern) != -1;
}

Variant _run_grep_search(const GrepOptions &p_options) {
	if (p_options.pattern.is_empty()) {
		return "Error: 'pattern' is required.";
	}

	Ref<RegEx> regex;
	if (p_options.use_regex) {
		regex.instantiate();
		const String compiled_pattern = p_options.case_sensitive ? p_options.pattern : String("(?i)") + p_options.pattern;
		if (regex->compile(compiled_pattern, false) != OK) {
			return "Error: Invalid regex pattern.";
		}
	}

	String results;
	int match_count = 0;
	bool truncated = false;
	List<String> dirs_to_search;
	dirs_to_search.push_back(p_options.directory);

	while (!dirs_to_search.is_empty() && match_count < p_options.max_results) {
		const String current_dir = dirs_to_search.front()->get();
		dirs_to_search.pop_front();

		Ref<DirAccess> dir = DirAccess::open(current_dir);
		if (dir.is_null()) {
			continue;
		}

		dir->list_dir_begin();
		String item = dir->get_next();
		while (!item.is_empty() && match_count < p_options.max_results) {
			if (item == "." || item == ".." || item.begins_with(".")) {
				item = dir->get_next();
				continue;
			}

			const String full_path = current_dir.path_join(item);
			if (dir->current_is_dir()) {
				dirs_to_search.push_back(full_path);
				item = dir->get_next();
				continue;
			}

			if (!_path_matches_glob(full_path, p_options.glob, p_options.case_sensitive)) {
				item = dir->get_next();
				continue;
			}

			Ref<FileAccess> file = FileAccess::open(full_path, FileAccess::READ);
			if (file.is_null()) {
				item = dir->get_next();
				continue;
			}

			const String content = file->get_as_text();
			const int line_count = content.get_slice_count("\n");
			for (int line_index = 0; line_index < line_count && match_count < p_options.max_results; line_index++) {
				const String line = _normalize_search_line(content.get_slice("\n", line_index));
				if (!_line_matches_search(line, p_options, regex)) {
					continue;
				}

				results += full_path + ":" + itos(line_index + 1) + ": " + line + "\n";
				if (p_options.context_lines > 0) {
					const int start = MAX(0, line_index - p_options.context_lines);
					const int end = MIN(line_count - 1, line_index + p_options.context_lines);
					for (int context_index = start; context_index <= end; context_index++) {
						if (context_index == line_index) {
							continue;
						}
						results += "  " + itos(context_index + 1) + "- " + _normalize_search_line(content.get_slice("\n", context_index)) + "\n";
					}
				}
				results += "\n";
				match_count++;
			}

			if (match_count >= p_options.max_results) {
				truncated = true;
			}
			item = dir->get_next();
		}
		dir->list_dir_end();
	}

	if (match_count == 0) {
		return "No matches found for: " + p_options.pattern;
	}

	String summary = "Found " + itos(match_count) + " matches";
	if (truncated) {
		summary += " (truncated at " + itos(p_options.max_results) + ")";
	}
	return summary + ":\n" + results.strip_edges(false, true);
}

} // namespace

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
		reg->register_tool("read_file", "Read the contents of a project file", params, callable_mp_static(&ResourceTools::tool_read_file), false, AIToolRegistry::EXECUTION_READ_ONLY, true,
				"Use when you already know the file path and need the exact current file contents.",
				"the raw file contents as plain text");
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
		reg->register_tool("write_file", "Write content to a project file", params, callable_mp_static(&ResourceTools::tool_write_file), true, AIToolRegistry::EXECUTION_MUTATING_FILE);
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
		reg->register_tool("delete_file", "Delete a file from the project", params, callable_mp_static(&ResourceTools::tool_delete_file), true, AIToolRegistry::EXECUTION_MUTATING_FILE);
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
		reg->register_tool("list_directory", "List the contents of a project directory", params, callable_mp_static(&ResourceTools::tool_list_directory), false, AIToolRegistry::EXECUTION_READ_ONLY, true,
				"Use to discover relevant files or folders before reading or editing them.",
				"a directory listing grouped into folders and files");
	}

	// search_files
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary pattern_prop;
		pattern_prop["type"] = "string";
		pattern_prop["description"] = "Pattern to search for in project files";
		props["pattern"] = pattern_prop;
		Dictionary dir_prop;
		dir_prop["type"] = "string";
		dir_prop["description"] = "Directory to search in (default: 'res://')";
		props["directory"] = dir_prop;
		Dictionary glob_prop;
		glob_prop["type"] = "string";
		glob_prop["description"] = "Optional glob filter such as '*.gd' or 'scripts/*'";
		props["glob"] = glob_prop;
		Dictionary regex_prop;
		regex_prop["type"] = "boolean";
		regex_prop["description"] = "Treat pattern as a regular expression";
		props["use_regex"] = regex_prop;
		Dictionary case_prop;
		case_prop["type"] = "boolean";
		case_prop["description"] = "Use case-sensitive matching";
		props["case_sensitive"] = case_prop;
		Dictionary max_prop;
		max_prop["type"] = "integer";
		max_prop["description"] = "Maximum number of matches to return";
		props["max_results"] = max_prop;
		Dictionary context_prop;
		context_prop["type"] = "integer";
		context_prop["description"] = "Number of context lines to include before and after each match";
		props["context_lines"] = context_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("pattern");
		params["required"] = required;
		reg->register_tool("grep_files", "Search project files with grep-like output", params, callable_mp_static(&ResourceTools::tool_grep_files), false, AIToolRegistry::EXECUTION_READ_ONLY, true,
				"Use to locate symbols, strings, or patterns across the project before reading specific files.",
				"grep-style matches with file paths, line numbers, and optional context");
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
		reg->register_tool("search_files", "Search for text in project files", params, callable_mp_static(&ResourceTools::tool_search_files), false, AIToolRegistry::EXECUTION_READ_ONLY, true,
				"Use for simpler text searches when you do not need regex or grep-style context output.",
				"a text-search result string with matching files");
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
		reg->register_tool("move_file", "Move or rename a project file", params, callable_mp_static(&ResourceTools::tool_move_file), true, AIToolRegistry::EXECUTION_MUTATING_FILE);
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

Variant ResourceTools::tool_grep_files(const Dictionary &p_args) {
	GrepOptions options;
	options.pattern = String(p_args.get("pattern", "")).strip_edges();
	options.directory = String(p_args.get("directory", "res://")).strip_edges();
	options.glob = String(p_args.get("glob", "")).strip_edges();
	options.use_regex = (bool)p_args.get("use_regex", false);
	options.case_sensitive = (bool)p_args.get("case_sensitive", false);
	options.max_results = CLAMP((int)p_args.get("max_results", 100), 1, MAX_GREP_RESULTS_LIMIT);
	options.context_lines = CLAMP((int)p_args.get("context_lines", 0), 0, MAX_GREP_CONTEXT_LIMIT);

	if (options.directory.is_empty()) {
		options.directory = "res://";
	}

	return _run_grep_search(options);
}

Variant ResourceTools::tool_search_files(const Dictionary &p_args) {
	Dictionary grep_args;
	grep_args["pattern"] = p_args.get("query", "");
	grep_args["directory"] = p_args.get("directory", "res://");

	const String extension = String(p_args.get("extension", "")).strip_edges();
	if (!extension.is_empty()) {
		grep_args["glob"] = "*." + extension;
	}
	return tool_grep_files(grep_args);
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
