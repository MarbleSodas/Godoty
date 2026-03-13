/**************************************************************************/
/*  script_context.h                                                      */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "core/variant/dictionary.h"
#include "core/variant/typed_array.h"

class ScriptContext {
public:
	// Collect full script context — open scripts, errors, cursor position.
	static Dictionary collect();

	// Get metadata for a specific script.
	static Dictionary get_script_metadata(const String &p_path);

	// Get list of currently open scripts in the script editor.
	static TypedArray<Dictionary> get_open_scripts();
};
