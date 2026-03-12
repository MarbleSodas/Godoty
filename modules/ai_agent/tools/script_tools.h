/**************************************************************************/
/*  script_tools.h                                                        */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "core/object/object.h"
#include "core/variant/dictionary.h"

class ScriptTools : public Object {
	GDCLASS(ScriptTools, Object);

protected:
	static void _bind_methods();

public:
	static void register_tools();

	static Variant tool_create_script(const Dictionary &p_args);
	static Variant tool_edit_script(const Dictionary &p_args);
	static Variant tool_attach_script(const Dictionary &p_args);
	static Variant tool_detach_script(const Dictionary &p_args);
	static Variant tool_open_script(const Dictionary &p_args);
	static Variant tool_get_script_content(const Dictionary &p_args);

	ScriptTools() {}
};
