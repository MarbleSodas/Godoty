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

namespace {

String _detect_script_language_name(const String &p_path) {
	const String extension = p_path.get_extension().to_lower();
	if (extension == "gd") {
		return "GDScript";
	}
	if (extension == "cs") {
		return "C#";
	}
	if (extension == "gdextension") {
		return "GDExtension";
	}
	return extension.is_empty() ? "Unknown" : extension.to_upper();
}

String _extract_identifier(const String &p_text) {
	String identifier;
	for (int i = 0; i < p_text.length(); i++) {
		const char32_t c = p_text[i];
		if ((c >= 'A' && c <= 'Z') ||
				(c >= 'a' && c <= 'z') ||
				(c >= '0' && c <= '9') ||
				c == '_' || c == '.') {
			identifier += String::chr(c);
		} else {
			break;
		}
	}
	return identifier;
}

String _extract_assignment_name(String p_line) {
	p_line = p_line.strip_edges();
	while (p_line.begins_with("@")) {
		const int space_pos = p_line.find(" ");
		if (space_pos == -1) {
			return String();
		}
		p_line = p_line.substr(space_pos + 1).strip_edges();
	}
	if (!p_line.begins_with("var ")) {
		return String();
	}
	return _extract_identifier(p_line.substr(4).strip_edges());
}

PackedStringArray _extract_argument_names(const String &p_args_text) {
	PackedStringArray args;
	PackedStringArray parts = p_args_text.split(",", false);
	for (int i = 0; i < parts.size(); i++) {
		String part = parts[i].strip_edges();
		if (part.is_empty()) {
			continue;
		}
		const int equals_pos = part.find("=");
		if (equals_pos != -1) {
			part = part.left(equals_pos).strip_edges();
		}
		const int colon_pos = part.find(":");
		if (colon_pos != -1) {
			part = part.left(colon_pos).strip_edges();
		}
		part = _extract_identifier(part);
		if (!part.is_empty()) {
			args.push_back(part);
		}
	}
	return args;
}

Dictionary _build_fallback_script_metadata(const String &p_path, const String &p_source, const String &p_load_error) {
	Dictionary metadata;
	const String language_name = _detect_script_language_name(p_path);
	metadata["path"] = p_path;
	metadata["language"] = language_name;
	metadata["is_valid"] = false;
	metadata["metadata_source"] = "fallback_parse";
	metadata["load_error"] = p_load_error;
	metadata["source_code"] = p_source;

	String class_name;
	String base_type;
	TypedArray<Dictionary> methods;
	TypedArray<Dictionary> properties;
	TypedArray<Dictionary> signals;

	PackedStringArray lines = p_source.split("\n", false);
	for (int i = 0; i < lines.size(); i++) {
		const String stripped = lines[i].strip_edges();
		if (stripped.is_empty() || stripped.begins_with("#")) {
			continue;
		}

		if (class_name.is_empty() && stripped.begins_with("class_name ")) {
			class_name = _extract_identifier(stripped.substr(11).strip_edges());
			continue;
		}
		if (base_type.is_empty() && stripped.begins_with("extends ")) {
			base_type = _extract_identifier(stripped.substr(8).strip_edges());
			continue;
		}
		if (stripped.begins_with("signal ")) {
			const int open_paren = stripped.find("(");
			const int close_paren = open_paren == -1 ? -1 : stripped.find(")", open_paren + 1);
			Dictionary signal_info;
			signal_info["name"] = _extract_identifier(stripped.substr(7).strip_edges());
			signal_info["arguments"] = (open_paren == -1 || close_paren == -1) ? PackedStringArray() : _extract_argument_names(stripped.substr(open_paren + 1, close_paren - open_paren - 1));
			signals.push_back(signal_info);
			continue;
		}

		String func_line = stripped;
		if (func_line.begins_with("static func ")) {
			func_line = func_line.substr(7).strip_edges();
		}
		if (func_line.begins_with("func ")) {
			const int open_paren = func_line.find("(");
			const int close_paren = func_line.find(")", open_paren + 1);
			Dictionary method_info;
			method_info["name"] = open_paren == -1 ? _extract_identifier(func_line.substr(5).strip_edges()) : _extract_identifier(func_line.substr(5, open_paren - 5).strip_edges());
			method_info["arguments"] = (open_paren == -1 || close_paren == -1) ? PackedStringArray() : _extract_argument_names(func_line.substr(open_paren + 1, close_paren - open_paren - 1));
			method_info["return_type"] = "Variant";
			methods.push_back(method_info);
			continue;
		}

		const String property_name = _extract_assignment_name(stripped);
		if (!property_name.is_empty()) {
			Dictionary property_info;
			property_info["name"] = property_name;
			property_info["type"] = "Variant";
			properties.push_back(property_info);
		}
	}

	if (base_type.is_empty() && language_name == "GDScript") {
		base_type = "RefCounted";
	}

	metadata["class_name"] = class_name;
	metadata["base_type"] = base_type;
	metadata["methods"] = methods;
	metadata["properties"] = properties;
	metadata["signals"] = signals;
	return metadata;
}

} // namespace

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

	Ref<Script> script = ResourceLoader::load(p_path, "Script", ResourceFormatLoader::CACHE_MODE_IGNORE);
	if (script.is_null()) {
		Ref<FileAccess> file = FileAccess::open(p_path, FileAccess::READ);
		if (!file.is_valid()) {
			metadata["error"] = "Script not found: " + p_path;
			return metadata;
		}
		return _build_fallback_script_metadata(p_path, file->get_as_text(), "Script could not be loaded for reflective inspection.");
	}
	if (!script->is_valid()) {
		String source_code = script->get_source_code();
		if (source_code.is_empty()) {
			Ref<FileAccess> file = FileAccess::open(p_path, FileAccess::READ);
			if (file.is_valid()) {
				source_code = file->get_as_text();
			}
		}
		return _build_fallback_script_metadata(p_path, source_code, "Script loaded but failed validation for reflective inspection.");
	}

	metadata["class_name"] = script->get_global_name();
	metadata["base_type"] = script->get_instance_base_type();
	metadata["is_valid"] = script->is_valid();
	metadata["language"] = script->get_language() ? script->get_language()->get_name() : "Unknown";
	metadata["metadata_source"] = "script_runtime";

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
