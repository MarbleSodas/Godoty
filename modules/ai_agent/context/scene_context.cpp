/**************************************************************************/
/*  scene_context.cpp                                                     */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "scene_context.h"

#include "core/config/project_settings.h"
#include "scene/main/node.h"
#include "scene/main/scene_tree.h"

#ifdef TOOLS_ENABLED
#include "editor/editor_interface.h"
#include "editor/editor_node.h"
#include "editor/gui/editor_scene_tabs.h"
#endif

Dictionary SceneContext::collect() {
	Dictionary context;

#ifdef TOOLS_ENABLED
	SceneTree *tree = SceneTree::get_singleton();
	if (!tree) {
		context["error"] = "No SceneTree available.";
		return context;
	}

	// Get the edited scene root.
	Node *edited_root = EditorInterface::get_singleton()->get_edited_scene_root();
	if (edited_root) {
		context["scene_tree"] = serialize_node(edited_root);
		context["scene_file"] = edited_root->get_scene_file_path();
	} else {
		context["scene_tree"] = Dictionary();
		context["scene_file"] = "";
		context["note"] = "No scene currently open.";
	}

	// Currently selected nodes.
	context["selected_nodes"] = get_selected_nodes();
#else
	context["error"] = "Scene context is only available in editor builds.";
#endif

	return context;
}

Dictionary SceneContext::serialize_node(Node *p_node, int p_max_depth) {
	Dictionary node_data;
	if (!p_node) {
		return node_data;
	}

	node_data["name"] = p_node->get_name();
	node_data["type"] = p_node->get_class();
	node_data["path"] = String(p_node->get_path());

	// Exported/configured properties.
	List<PropertyInfo> props;
	p_node->get_property_list(&props);
	Dictionary properties;
	for (const PropertyInfo &pi : props) {
		if (pi.usage & PROPERTY_USAGE_EDITOR) {
			Variant val = p_node->get(pi.name);
			// Only include non-default, serializable properties.
			if (val.get_type() != Variant::NIL && val.get_type() != Variant::OBJECT) {
				properties[pi.name] = val;
			}
		}
	}
	if (!properties.is_empty()) {
		node_data["properties"] = properties;
	}

	// Groups.
	List<Node::GroupInfo> groups;
	p_node->get_groups(&groups);
	if (groups.size() > 0) {
		PackedStringArray group_names;
		for (const Node::GroupInfo &gi : groups) {
			if (!gi.persistent) {
				continue; // Skip internal groups.
			}
			group_names.push_back(gi.name);
		}
		if (group_names.size() > 0) {
			node_data["groups"] = group_names;
		}
	}

	// Script info.
	Ref<Script> script = p_node->get_script();
	if (script.is_valid()) {
		node_data["script"] = script->get_path();
	}

	// Signal connections.
	TypedArray<Dictionary> connections = get_signal_connections(p_node);
	if (connections.size() > 0) {
		node_data["connections"] = connections;
	}

	// Children (recursive).
	if (p_max_depth > 0 && p_node->get_child_count() > 0) {
		TypedArray<Dictionary> children;
		for (int i = 0; i < p_node->get_child_count(); i++) {
			Node *child = p_node->get_child(i);
			if (child->get_owner() == nullptr && child != p_node->get_tree()->get_edited_scene_root()) {
				continue; // Skip nodes not owned by the scene (internal nodes).
			}
			children.push_back(serialize_node(child, p_max_depth - 1));
		}
		if (children.size() > 0) {
			node_data["children"] = children;
		}
	}

	return node_data;
}

TypedArray<Dictionary> SceneContext::get_selected_nodes() {
	TypedArray<Dictionary> selected;

#ifdef TOOLS_ENABLED
	EditorSelection *selection = EditorInterface::get_singleton()->get_selection();
	if (!selection) {
		return selected;
	}

	List<Node *> nodes = selection->get_selected_node_list();
	for (Node *node : nodes) {
		Dictionary info;
		info["name"] = node->get_name();
		info["type"] = node->get_class();
		info["path"] = String(node->get_path());
		selected.push_back(info);
	}
#endif

	return selected;
}

TypedArray<Dictionary> SceneContext::get_signal_connections(Node *p_node) {
	TypedArray<Dictionary> connections;
	if (!p_node) {
		return connections;
	}

	List<Object::Connection> conns;
	p_node->get_all_signal_connections(&conns);
	for (const Object::Connection &conn : conns) {
		Dictionary cd;
		cd["signal"] = conn.signal.get_name();
		Object *target = conn.callable.get_object();
		if (target) {
			Node *target_node = Object::cast_to<Node>(target);
			if (target_node) {
				cd["target"] = String(target_node->get_path());
			}
		}
		cd["method"] = conn.callable.get_method();
		connections.push_back(cd);
	}

	return connections;
}
