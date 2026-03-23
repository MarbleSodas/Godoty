/**************************************************************************/
/*  resource_tools.h                                                      */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "core/object/object.h"
#include "core/variant/dictionary.h"

class ResourceTools : public Object {
	GDCLASS(ResourceTools, Object);

protected:
	static void _bind_methods();

public:
	static void register_tools();

	static Variant tool_read_file(const Dictionary &p_args);
	static Variant tool_write_file(const Dictionary &p_args);
	static Variant tool_delete_file(const Dictionary &p_args);
	static Variant tool_list_directory(const Dictionary &p_args);
	static Variant tool_grep_files(const Dictionary &p_args);
	static Variant tool_search_files(const Dictionary &p_args);
	static Variant tool_move_file(const Dictionary &p_args);

	ResourceTools() {}
};
