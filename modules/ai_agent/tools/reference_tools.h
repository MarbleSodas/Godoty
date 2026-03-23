/**************************************************************************/
/*  reference_tools.h                                                     */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "core/object/object.h"
#include "core/variant/dictionary.h"

class ReferenceTools : public Object {
	GDCLASS(ReferenceTools, Object);

protected:
	static void _bind_methods();

public:
	static void register_tools();

	static Variant tool_get_project_info(const Dictionary &p_args);
	static Variant tool_get_godot_version(const Dictionary &p_args);
	static Variant tool_inspect_node(const Dictionary &p_args);
	static Variant tool_get_class_reference(const Dictionary &p_args);
	static Variant tool_get_script_reference(const Dictionary &p_args);

	ReferenceTools() {}
};
