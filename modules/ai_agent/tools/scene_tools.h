/**************************************************************************/
/*  scene_tools.h                                                         */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "core/object/object.h"
#include "core/variant/dictionary.h"

class SceneTools : public Object {
	GDCLASS(SceneTools, Object);

protected:
	static void _bind_methods();

public:
	// Register all scene tools with the AIToolRegistry.
	static void register_tools();

	// Tool implementations — all return result strings.
	static Variant tool_create_node(const Dictionary &p_args);
	static Variant tool_delete_node(const Dictionary &p_args);
	static Variant tool_rename_node(const Dictionary &p_args);
	static Variant tool_reparent_node(const Dictionary &p_args);
	static Variant tool_duplicate_node(const Dictionary &p_args);
	static Variant tool_set_node_property(const Dictionary &p_args);
	static Variant tool_get_node_property(const Dictionary &p_args);
	static Variant tool_connect_signal(const Dictionary &p_args);
	static Variant tool_disconnect_signal(const Dictionary &p_args);
	static Variant tool_add_to_group(const Dictionary &p_args);
	static Variant tool_instantiate_scene(const Dictionary &p_args);
	static Variant tool_save_scene(const Dictionary &p_args);
	static Variant tool_create_scene(const Dictionary &p_args);

	SceneTools() {}
};
