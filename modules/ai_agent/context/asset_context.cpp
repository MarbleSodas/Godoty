/**************************************************************************/
/*  asset_context.cpp                                                     */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "asset_context.h"

#include "core/io/dir_access.h"
#include "core/io/file_access.h"
#include "core/os/os.h"

#ifdef TOOLS_ENABLED
#include "editor/file_system/editor_file_system.h"
#include "editor/editor_interface.h"
#endif

Dictionary AssetContext::collect() {
	Dictionary context;

#ifdef TOOLS_ENABLED
	context["directory_tree"] = get_directory_tree();
	context["recent_files"] = get_recent_files();

	// File system stats.
	EditorFileSystem *efs = EditorFileSystem::get_singleton();
	if (efs) {
		context["filesystem_scanning"] = efs->is_scanning();
		context["scan_progress"] = efs->get_scanning_progress();
	}
#else
	context["error"] = "Asset context is only available in editor builds.";
#endif

	return context;
}

Dictionary AssetContext::get_directory_tree(const String &p_path, int p_max_depth) {
	Dictionary tree;
	tree["path"] = p_path;

	if (p_max_depth <= 0) {
		tree["truncated"] = true;
		return tree;
	}

	Ref<DirAccess> dir = DirAccess::open(p_path);
	if (dir.is_null()) {
		tree["error"] = "Cannot open directory: " + p_path;
		return tree;
	}

	PackedStringArray files;
	TypedArray<Dictionary> subdirs;

	dir->list_dir_begin();
	String item = dir->get_next();
	while (!item.is_empty()) {
		if (item == "." || item == ".." || item.begins_with(".")) {
			item = dir->get_next();
			continue;
		}

		String full_path = p_path.path_join(item);
		if (dir->current_is_dir()) {
			// Skip .godot, .import, addons directories for brevity.
			if (item != ".godot" && item != ".import") {
				subdirs.push_back(get_directory_tree(full_path, p_max_depth - 1));
			}
		} else {
			files.push_back(item);
		}
		item = dir->get_next();
	}
	dir->list_dir_end();

	if (files.size() > 0) {
		tree["files"] = files;
	}
	if (subdirs.size() > 0) {
		tree["directories"] = subdirs;
	}

	return tree;
}

TypedArray<Dictionary> AssetContext::get_recent_files(int p_minutes) {
	TypedArray<Dictionary> recent;

#ifdef TOOLS_ENABLED
	EditorFileSystem *efs = EditorFileSystem::get_singleton();
	if (!efs) {
		return recent;
	}

	uint64_t cutoff_time = OS::get_singleton()->get_unix_time() - (p_minutes * 60);

	// Walk the editor filesystem to find recently modified files.
	EditorFileSystemDirectory *root = efs->get_filesystem();
	if (!root) {
		return recent;
	}

	// Simple recursive walk of the editor filesystem.
	List<EditorFileSystemDirectory *> queue;
	queue.push_back(root);
	while (!queue.is_empty()) {
		EditorFileSystemDirectory *dir = queue.front()->get();
		queue.pop_front();

		for (int i = 0; i < dir->get_file_count(); i++) {
			// EditorFileSystemDirectory stores modification times.
			String path = dir->get_file_path(i);
			String type = dir->get_file_type(i);

			// We can't easily get mod time from EditorFileSystem, use FileAccess.
			uint64_t mod_time = FileAccess::get_modified_time(path);
			if (mod_time >= cutoff_time) {
				Dictionary info;
				info["path"] = path;
				info["type"] = type;
				info["modified"] = mod_time;
				recent.push_back(info);
			}
		}

		for (int i = 0; i < dir->get_subdir_count(); i++) {
			queue.push_back(dir->get_subdir(i));
		}
	}
#endif

	return recent;
}
