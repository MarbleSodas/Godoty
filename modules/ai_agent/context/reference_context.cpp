/**************************************************************************/
/*  reference_context.cpp                                                 */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "reference_context.h"

#include "modules/ai_agent/context/scene_context.h"
#include "modules/ai_agent/tools/reference_tools.h"
#include "scene/main/node.h"

#ifdef TOOLS_ENABLED
#include "editor/editor_interface.h"
#include "editor/inspector/editor_inspector.h"
#include "editor/script/script_editor_plugin.h"
#endif

namespace {

constexpr int MAX_REFERENCE_CLASSES = 4;
constexpr int MAX_REFERENCE_PROPERTIES = 6;
constexpr int MAX_REFERENCE_METHODS = 6;
constexpr int MAX_REFERENCE_SIGNALS = 4;

void _append_unique_class(PackedStringArray &r_classes, const String &p_class_name) {
	const String class_name = p_class_name.strip_edges();
	if (class_name.is_empty() || r_classes.has(class_name) || r_classes.size() >= MAX_REFERENCE_CLASSES) {
		return;
	}
	r_classes.push_back(class_name);
}

TypedArray<Dictionary> _truncate_dictionary_array(const TypedArray<Dictionary> &p_array, int p_limit) {
	TypedArray<Dictionary> trimmed;
	for (int i = 0; i < p_array.size() && i < p_limit; i++) {
		trimmed.push_back(p_array[i]);
	}
	return trimmed;
}

Dictionary _trim_reference_entry(const Dictionary &p_entry) {
	Dictionary entry = p_entry.duplicate(true);
	if (entry.has("properties")) {
		entry["properties"] = _truncate_dictionary_array(entry["properties"], MAX_REFERENCE_PROPERTIES);
	}
	if (entry.has("methods")) {
		entry["methods"] = _truncate_dictionary_array(entry["methods"], MAX_REFERENCE_METHODS);
	}
	if (entry.has("signals")) {
		entry["signals"] = _truncate_dictionary_array(entry["signals"], MAX_REFERENCE_SIGNALS);
	}
	return entry;
}

} // namespace

Dictionary ReferenceContext::collect() {
	Dictionary context;

#ifdef TOOLS_ENABLED
	PackedStringArray class_names;
	EditorInterface *editor_interface = EditorInterface::get_singleton();
	if (!editor_interface) {
		context["error"] = "EditorInterface not available.";
		return context;
	}

	EditorInspector *inspector = editor_interface->get_inspector();
	if (inspector) {
		Object *inspected = inspector->get_edited_object();
		if (inspected) {
			_append_unique_class(class_names, inspected->get_class());
		}
	}

	TypedArray<Dictionary> selected_nodes = SceneContext::get_selected_nodes();
	for (int i = 0; i < selected_nodes.size(); i++) {
		_append_unique_class(class_names, ((Dictionary)selected_nodes[i]).get("type", ""));
	}

	Node *edited_root = editor_interface->get_edited_scene_root();
	if (edited_root) {
		_append_unique_class(class_names, edited_root->get_class());
	}

	ScriptEditor *script_editor = ScriptEditor::get_singleton();
	if (script_editor) {
		Ref<Script> current_script = script_editor->call("get_current_script");
		if (current_script.is_valid()) {
			_append_unique_class(class_names, current_script->get_instance_base_type());
		}
	}

	TypedArray<Dictionary> references;
	for (int i = 0; i < class_names.size(); i++) {
		Dictionary args;
		args["class_name"] = class_names[i];
		Variant result = ReferenceTools::tool_get_class_reference(args);
		if (result.get_type() == Variant::DICTIONARY) {
			references.push_back(_trim_reference_entry(result));
		}
	}

	if (!references.is_empty()) {
		context["classes"] = references;
	} else {
		context["note"] = "No focused class reference data is currently available.";
	}
#else
	context["error"] = "Reference context is only available in editor builds.";
#endif

	return context;
}
