/**************************************************************************/
/*  debug_tools.h                                                         */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "core/object/object.h"
#include "core/variant/dictionary.h"

class DebugTools : public Object {
	GDCLASS(DebugTools, Object);

protected:
	static void _bind_methods();

public:
	static void register_tools();

	static Variant tool_get_console_output(const Dictionary &p_args);
	static Variant tool_pause_game(const Dictionary &p_args);
	static Variant tool_resume_game(const Dictionary &p_args);
	static Variant tool_get_performance_metrics(const Dictionary &p_args);

	DebugTools() {}
};
