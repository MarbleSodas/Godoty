/**************************************************************************/
/*  scene_context.h                                                       */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "core/variant/dictionary.h"
#include "core/variant/typed_array.h"

class Node;

class SceneContext {
public:
	// Collect the full scene context — tree structure, selected nodes, signals.
	static Dictionary collect();

	// Serialize a single node and its children recursively.
	static Dictionary serialize_node(Node *p_node, int p_max_depth = 10);

	// Get currently selected nodes in the editor.
	static TypedArray<Dictionary> get_selected_nodes();

	// Get signal connections for a node.
	static TypedArray<Dictionary> get_signal_connections(Node *p_node);
};
