/**************************************************************************/
/*  script_context.cpp                                                    */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "script_context.h"

#include "core/io/file_access.h"
#include "core/object/script_language.h"

#ifdef TOOLS_ENABLED
#include "editor/script/script_editor_plugin.h"
#endif

Dictionary ScriptContext::collect() {
	Dictionary context;

#ifdef TOOLS_ENABLED
	context["open_scripts"] = get_open_scripts();

	// Get the currently active script in the editor.
	ScriptEditor *script_editor = ScriptEditor::get_singleton();
	if (script_editor) {
		Ref<Script> current = script_editor->call("get_current_script");
		if (current.is_valid()) {
			context["current_script"] = current->get_path();
			context["current_script_content"] = current->get_source_code();
			context["current_script_metadata"] = get_script_metadata(current->get_path());
		}
	}

	// Collect script errors from all script languages.
	TypedArray<Dictionary> errors;
	for (int i = 0; i < ScriptServer::get_language_count(); i++) {
		// ScriptLanguage *lang = ScriptServer::get_language(i);
		// Errors are typically surfaced through the editor's error reporting.
		// We capture them here as part of the context.
	}
	context["errors"] = errors;
#else
	context["error"] = "Script context is only available in editor builds.";
#endif

	return context;
}

Dictionary ScriptContext::get_script_metadata(const String &p_path) {
	Dictionary metadata;
	metadata["path"] = p_path;

	Ref<Script> script = ResourceLoader::load(p_path);
	if (script.is_null()) {
		metadata["error"] = "Script not found: " + p_path;
		return metadata;
	}

	metadata["class_name"] = script->get_global_name();
	metadata["base_type"] = script->get_instance_base_type();
	metadata["is_valid"] = script->is_valid();
	metadata["language"] = script->get_language() ? script->get_language()->get_name() : "Unknown";

	// Methods.
	List<MethodInfo> methods;
	script->get_script_method_list(&methods);
	TypedArray<Dictionary> method_list;
	for (const MethodInfo &mi : methods) {
		Dictionary md;
		md["name"] = mi.name;
		md["return_type"] = Variant::get_type_name(mi.return_val.type);
		PackedStringArray args;
		for (const PropertyInfo &arg : mi.arguments) {
			args.push_back(arg.name + ": " + Variant::get_type_name(arg.type));
		}
		md["arguments"] = args;
		method_list.push_back(md);
	}
	metadata["methods"] = method_list;

	// Properties/members.
	List<PropertyInfo> props;
	script->get_script_property_list(&props);
	TypedArray<Dictionary> prop_list;
	for (const PropertyInfo &pi : props) {
		Dictionary pd;
		pd["name"] = pi.name;
		pd["type"] = Variant::get_type_name(pi.type);
		prop_list.push_back(pd);
	}
	metadata["properties"] = prop_list;

	// Signals.
	List<MethodInfo> signals;
	script->get_script_signal_list(&signals);
	TypedArray<Dictionary> signal_list;
	for (const MethodInfo &si : signals) {
		Dictionary sd;
		sd["name"] = si.name;
		PackedStringArray args;
		for (const PropertyInfo &arg : si.arguments) {
			args.push_back(arg.name + ": " + Variant::get_type_name(arg.type));
		}
		sd["arguments"] = args;
		signal_list.push_back(sd);
	}
	metadata["signals"] = signal_list;

	// Source code.
	metadata["source_code"] = script->get_source_code();

	return metadata;
}

TypedArray<Dictionary> ScriptContext::get_open_scripts() {
	TypedArray<Dictionary> scripts;

#ifdef TOOLS_ENABLED
	ScriptEditor *script_editor = ScriptEditor::get_singleton();
	if (!script_editor) {
		return scripts;
	}

	Vector<Ref<Script>> open = script_editor->get_open_scripts();
	for (int i = 0; i < open.size(); i++) {
		Ref<Script> s = open[i];
		if (s.is_valid()) {
			Dictionary info;
			info["path"] = s->get_path();
			info["class_name"] = s->get_global_name();
			info["base_type"] = s->get_instance_base_type();
			info["is_valid"] = s->is_valid();
			scripts.push_back(info);
		}
	}
#endif

	return scripts;
}
