/**************************************************************************/
/*  reference_tools.cpp                                                   */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "reference_tools.h"

#include "core/config/engine.h"
#include "core/doc_data.h"
#include "core/object/class_db.h"
#include "modules/ai_agent/ai_tool_registry.h"
#include "modules/ai_agent/context/project_context.h"
#include "modules/ai_agent/context/scene_context.h"
#include "modules/ai_agent/context/script_context.h"
#include "scene/main/node.h"

#ifdef TOOLS_ENABLED
#include "editor/doc/editor_help.h"
#include "editor/editor_interface.h"
#endif

namespace {

constexpr int CLASS_REFERENCE_DEFAULT_LIMIT = 12;
constexpr int CLASS_REFERENCE_DOC_LIMIT = 220;

String _trim_doc_text(const String &p_text, int p_limit = CLASS_REFERENCE_DOC_LIMIT) {
	String text = p_text.strip_edges().replace("\n", " ").replace("\r", " ");
	while (text.contains("  ")) {
		text = text.replace("  ", " ");
	}
	if (text.length() <= p_limit) {
		return text;
	}
	return text.substr(0, p_limit - 3).rstrip(" ,.:-") + "...";
}

bool _matches_filter(const String &p_value, const String &p_filter) {
	if (p_filter.is_empty()) {
		return true;
	}
	return p_value.findn(p_filter) != -1;
}

Dictionary _method_doc_to_dictionary(const DocData::MethodDoc &p_method) {
	Dictionary dict = DocData::MethodDoc::to_dict(p_method);
	if (dict.has("description")) {
		dict["description"] = _trim_doc_text(dict["description"]);
	}
	return dict;
}

Dictionary _property_doc_to_dictionary(const DocData::PropertyDoc &p_property) {
	Dictionary dict = DocData::PropertyDoc::to_dict(p_property);
	if (dict.has("description")) {
		dict["description"] = _trim_doc_text(dict["description"]);
	}
	return dict;
}

Dictionary _method_info_to_dictionary(const MethodInfo &p_method) {
	Dictionary dict;
	dict["name"] = p_method.name;
	dict["return_type"] = Variant::get_type_name(p_method.return_val.type);
	PackedStringArray args;
	for (int i = 0; i < p_method.arguments.size(); i++) {
		const PropertyInfo &arg = p_method.arguments[i];
		args.push_back(arg.name + ": " + Variant::get_type_name(arg.type));
	}
	dict["arguments"] = args;
	return dict;
}

Dictionary _property_info_to_dictionary(const PropertyInfo &p_property) {
	Dictionary dict;
	dict["name"] = p_property.name;
	dict["type"] = Variant::get_type_name(p_property.type);
	if (p_property.type == Variant::OBJECT && !p_property.class_name.is_empty()) {
		dict["class_name"] = p_property.class_name;
	}
	return dict;
}

void _append_doc_methods(const Vector<DocData::MethodDoc> &p_methods, const String &p_filter, TypedArray<Dictionary> &r_output, int p_limit) {
	for (int i = 0; i < p_methods.size() && r_output.size() < p_limit; i++) {
		if (!_matches_filter(p_methods[i].name, p_filter)) {
			continue;
		}
		r_output.push_back(_method_doc_to_dictionary(p_methods[i]));
	}
}

void _append_doc_properties(const Vector<DocData::PropertyDoc> &p_properties, const String &p_filter, TypedArray<Dictionary> &r_output, int p_limit) {
	for (int i = 0; i < p_properties.size() && r_output.size() < p_limit; i++) {
		if (!_matches_filter(p_properties[i].name, p_filter)) {
			continue;
		}
		r_output.push_back(_property_doc_to_dictionary(p_properties[i]));
	}
}

void _append_fallback_methods(const StringName &p_class_name, const String &p_filter, TypedArray<Dictionary> &r_output, int p_limit, bool p_signals) {
	List<MethodInfo> methods;
	if (p_signals) {
		ClassDB::get_signal_list(p_class_name, &methods);
	} else {
		ClassDB::get_method_list(p_class_name, &methods, false, true);
	}

	for (const MethodInfo &method : methods) {
		if ((int)r_output.size() >= p_limit) {
			break;
		}
		if (!_matches_filter(method.name, p_filter)) {
			continue;
		}
		r_output.push_back(_method_info_to_dictionary(method));
	}
}

void _append_fallback_properties(const StringName &p_class_name, const String &p_filter, TypedArray<Dictionary> &r_output, int p_limit) {
	List<PropertyInfo> properties;
	ClassDB::get_property_list(p_class_name, &properties);

	for (const PropertyInfo &property : properties) {
		if ((int)r_output.size() >= p_limit) {
			break;
		}
		if (!(property.usage & PROPERTY_USAGE_EDITOR)) {
			continue;
		}
		if (!_matches_filter(property.name, p_filter)) {
			continue;
		}
		r_output.push_back(_property_info_to_dictionary(property));
	}
}

} // namespace

void ReferenceTools::_bind_methods() {
	ClassDB::bind_static_method("ReferenceTools", D_METHOD("register_tools"), &ReferenceTools::register_tools);
}

void ReferenceTools::register_tools() {
	AIToolRegistry *reg = AIToolRegistry::get_singleton();
	ERR_FAIL_NULL(reg);

	{
		Dictionary params;
		params["type"] = "object";
		params["properties"] = Dictionary();
		reg->register_tool("get_project_info",
				"Get summary information about the current open project",
				params,
				callable_mp_static(&ReferenceTools::tool_get_project_info),
				false,
				AIToolRegistry::EXECUTION_READ_ONLY,
				true,
				"Use before planning changes that depend on project settings, autoloads, input actions, or the current main scene.",
				"a structured project summary including project metadata, rendering, physics, autoloads, and input map details");
	}

	{
		Dictionary params;
		params["type"] = "object";
		params["properties"] = Dictionary();
		reg->register_tool("get_godot_version",
				"Get the running Godot editor and engine version information",
				params,
				callable_mp_static(&ReferenceTools::tool_get_godot_version),
				false,
				AIToolRegistry::EXECUTION_READ_ONLY,
				true,
				"Use when version-specific APIs, nodes, properties, or editor behavior may matter.",
				"a structured engine version dictionary");
	}

	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary path_prop;
		path_prop["type"] = "string";
		path_prop["description"] = "NodePath of the node to inspect.";
		props["node_path"] = path_prop;
		Dictionary depth_prop;
		depth_prop["type"] = "integer";
		depth_prop["description"] = "Optional child depth to include (default: 0, max: 3).";
		props["include_children_depth"] = depth_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("node_path");
		params["required"] = required;
		reg->register_tool("inspect_node",
				"Inspect a live node in the currently edited scene",
				params,
				callable_mp_static(&ReferenceTools::tool_inspect_node),
				false,
				AIToolRegistry::EXECUTION_READ_ONLY,
				true,
				"Use before mutating unfamiliar nodes to confirm the live class, script, groups, connections, and editor-visible properties.",
				"a structured node snapshot with class, path, properties, signals, script, groups, and optional shallow children");
	}

	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary class_prop;
		class_prop["type"] = "string";
		class_prop["description"] = "Godot class name to inspect.";
		props["class_name"] = class_prop;
		Dictionary property_prop;
		property_prop["type"] = "string";
		property_prop["description"] = "Optional property name filter.";
		props["property"] = property_prop;
		Dictionary method_prop;
		method_prop["type"] = "string";
		method_prop["description"] = "Optional method name filter.";
		props["method"] = method_prop;
		Dictionary signal_prop;
		signal_prop["type"] = "string";
		signal_prop["description"] = "Optional signal name filter.";
		props["signal"] = signal_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("class_name");
		params["required"] = required;
		reg->register_tool("get_class_reference",
				"Get built-in class reference data for a Godot class",
				params,
				callable_mp_static(&ReferenceTools::tool_get_class_reference),
				false,
				AIToolRegistry::EXECUTION_READ_ONLY,
				true,
				"Use when you need authoritative node, resource, property, method, or signal reference data before guessing an API.",
				"a structured class reference with inheritance, summary, and filtered properties, methods, and signals");
	}

	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary path_prop;
		path_prop["type"] = "string";
		path_prop["description"] = "Path of the script to inspect.";
		props["path"] = path_prop;
		params["properties"] = props;
		PackedStringArray required;
		required.push_back("path");
		params["required"] = required;
		reg->register_tool("get_script_reference",
				"Get metadata about a script file",
				params,
				callable_mp_static(&ReferenceTools::tool_get_script_reference),
				false,
				AIToolRegistry::EXECUTION_READ_ONLY,
				true,
				"Use before editing or attaching scripts when you need the class name, base type, methods, properties, signals, or current source.",
				"a structured script reference with class metadata, members, signals, and source code");
	}
}

Variant ReferenceTools::tool_get_project_info(const Dictionary &p_args) {
	(void)p_args;
	return ProjectContext::collect();
}

Variant ReferenceTools::tool_get_godot_version(const Dictionary &p_args) {
	(void)p_args;
	Engine *engine = Engine::get_singleton();
	if (!engine) {
		return "Error: Engine singleton is not available.";
	}
	return engine->get_version_info();
}

Variant ReferenceTools::tool_inspect_node(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	const String node_path = String(p_args.get("node_path", "")).strip_edges();
	if (node_path.is_empty()) {
		return "Error: 'node_path' is required.";
	}

	Node *root = EditorInterface::get_singleton()->get_edited_scene_root();
	if (!root) {
		return "Error: No scene is currently open.";
	}

	Node *node = root->get_node_or_null(NodePath(node_path));
	if (!node) {
		return "Error: Node not found at path: " + node_path;
	}

	const int requested_depth = (int)p_args.get("include_children_depth", 0);
	const int depth = CLAMP(requested_depth, 0, 3);
	return SceneContext::serialize_node(node, depth);
#else
	return "Error: only available in editor builds.";
#endif
}

Variant ReferenceTools::tool_get_class_reference(const Dictionary &p_args) {
	const String class_name = String(p_args.get("class_name", "")).strip_edges();
	if (class_name.is_empty()) {
		return "Error: 'class_name' is required.";
	}

	const String property_filter = String(p_args.get("property", "")).strip_edges();
	const String method_filter = String(p_args.get("method", "")).strip_edges();
	const String signal_filter = String(p_args.get("signal", "")).strip_edges();
	const StringName class_name_sn = class_name;

	const bool class_exists = ClassDB::class_exists(class_name_sn);
	const DocData::ClassDoc *class_doc = nullptr;
#ifdef TOOLS_ENABLED
	DocTools *doc_data = EditorHelp::get_doc_data();
	if (doc_data) {
		class_doc = doc_data->class_list.getptr(class_name);
	}
#endif

	if (!class_exists && class_doc == nullptr) {
		return "Error: Class reference not found for: " + class_name;
	}

	Dictionary result;
	result["class_name"] = class_name;
	result["inherits"] = class_doc ? class_doc->inherits : String(ClassDB::get_parent_class(class_name_sn));
	result["has_built_in_docs"] = class_doc != nullptr;

	String summary;
	if (class_doc) {
		summary = !class_doc->brief_description.is_empty() ? class_doc->brief_description : class_doc->description;
	}
	if (summary.is_empty() && class_exists) {
		summary = "Built-in engine metadata is available for this class even when prose documentation is unavailable.";
	}
	result["summary"] = _trim_doc_text(summary);

	TypedArray<Dictionary> properties;
	TypedArray<Dictionary> methods;
	TypedArray<Dictionary> signals;
	if (class_doc) {
		_append_doc_properties(class_doc->properties, property_filter, properties, CLASS_REFERENCE_DEFAULT_LIMIT);
		_append_doc_methods(class_doc->methods, method_filter, methods, CLASS_REFERENCE_DEFAULT_LIMIT);
		_append_doc_methods(class_doc->signals, signal_filter, signals, CLASS_REFERENCE_DEFAULT_LIMIT);
	}

	if (class_exists && properties.is_empty()) {
		_append_fallback_properties(class_name_sn, property_filter, properties, CLASS_REFERENCE_DEFAULT_LIMIT);
	}
	if (class_exists && methods.is_empty()) {
		_append_fallback_methods(class_name_sn, method_filter, methods, CLASS_REFERENCE_DEFAULT_LIMIT, false);
	}
	if (class_exists && signals.is_empty()) {
		_append_fallback_methods(class_name_sn, signal_filter, signals, CLASS_REFERENCE_DEFAULT_LIMIT, true);
	}

	result["properties"] = properties;
	result["methods"] = methods;
	result["signals"] = signals;
	if (!property_filter.is_empty() || !method_filter.is_empty() || !signal_filter.is_empty()) {
		Dictionary filters;
		if (!property_filter.is_empty()) {
			filters["property"] = property_filter;
		}
		if (!method_filter.is_empty()) {
			filters["method"] = method_filter;
		}
		if (!signal_filter.is_empty()) {
			filters["signal"] = signal_filter;
		}
		result["filters"] = filters;
	}

	return result;
}

Variant ReferenceTools::tool_get_script_reference(const Dictionary &p_args) {
	const String path = String(p_args.get("path", "")).strip_edges();
	if (path.is_empty()) {
		return "Error: 'path' is required.";
	}
	return ScriptContext::get_script_metadata(path);
}
