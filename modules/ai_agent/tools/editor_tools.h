/**************************************************************************/
/*  editor_tools.h                                                        */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "core/object/object.h"
#include "core/variant/dictionary.h"

class EditorTools : public Object {
	GDCLASS(EditorTools, Object);

protected:
	static void _bind_methods();

public:
	static void register_tools();

	static Variant tool_select_nodes(const Dictionary &p_args);
	static Variant tool_set_project_setting(const Dictionary &p_args);
	static Variant tool_undo(const Dictionary &p_args);
	static Variant tool_redo(const Dictionary &p_args);
	static Variant tool_run_project(const Dictionary &p_args);
	static Variant tool_stop_project(const Dictionary &p_args);
	static Variant tool_show_notification(const Dictionary &p_args);

	EditorTools() {}
};
