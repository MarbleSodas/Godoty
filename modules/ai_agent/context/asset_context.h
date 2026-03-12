/**************************************************************************/
/*  asset_context.h                                                       */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "core/variant/dictionary.h"
#include "core/variant/typed_array.h"

class AssetContext {
public:
	// Collect asset/filesystem context.
	static Dictionary collect();

	// Get directory tree of the project.
	static Dictionary get_directory_tree(const String &p_path = "res://", int p_max_depth = 4);

	// Get recently modified files.
	static TypedArray<Dictionary> get_recent_files(int p_minutes = 30);
};
