/**************************************************************************/
/*  ai_tool_registry.cpp                                                  */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "ai_tool_registry.h"
#include "core/io/json.h"

AIToolRegistry *AIToolRegistry::singleton = nullptr;

void AIToolRegistry::_bind_methods() {
	ClassDB::bind_method(D_METHOD("unregister_tool", "name"), &AIToolRegistry::unregister_tool);
	ClassDB::bind_method(D_METHOD("has_tool", "name"), &AIToolRegistry::has_tool);
	ClassDB::bind_method(D_METHOD("get_tool_schemas"), &AIToolRegistry::get_tool_schemas);
	ClassDB::bind_method(D_METHOD("get_tool_schema", "name"), &AIToolRegistry::get_tool_schema);
	ClassDB::bind_method(D_METHOD("get_tool_usage_guide", "enabled_tools"), &AIToolRegistry::get_tool_usage_guide, DEFVAL(PackedStringArray()));
	ClassDB::bind_method(D_METHOD("execute_tool", "name", "arguments"), &AIToolRegistry::execute_tool);
	ClassDB::bind_method(D_METHOD("get_tool_names"), &AIToolRegistry::get_tool_names);
	ClassDB::bind_method(D_METHOD("tool_requires_approval", "name"), &AIToolRegistry::tool_requires_approval);
	ClassDB::bind_method(D_METHOD("is_tool_parallel_safe", "name"), &AIToolRegistry::is_tool_parallel_safe);
	ClassDB::bind_method(D_METHOD("get_tool_count"), &AIToolRegistry::get_tool_count);

	ADD_SIGNAL(MethodInfo("tool_registered", PropertyInfo(Variant::STRING, "name")));
	ADD_SIGNAL(MethodInfo("tool_unregistered", PropertyInfo(Variant::STRING, "name")));
	ADD_SIGNAL(MethodInfo("tool_executed",
			PropertyInfo(Variant::STRING, "name"),
			PropertyInfo(Variant::DICTIONARY, "arguments"),
			PropertyInfo(Variant::NIL, "result")));
}

AIToolRegistry::AIToolRegistry() {
	singleton = this;
}

AIToolRegistry::~AIToolRegistry() {
	singleton = nullptr;
}

AIToolRegistry *AIToolRegistry::get_singleton() {
	return singleton;
}

void AIToolRegistry::register_tool(const String &p_name, const String &p_description,
		const Dictionary &p_parameters_schema, const Callable &p_handler,
		bool p_requires_approval, ExecutionPolicy p_execution_policy, bool p_parallel_safe,
		const String &p_usage_hint, const String &p_output_hint) {
	ERR_FAIL_COND_MSG(p_name.strip_edges().is_empty(), "AI tool registration requires a non-empty tool name.");
	ERR_FAIL_COND_MSG(p_handler.is_null() || !p_handler.is_valid(), vformat("AI tool '%s' must be registered with a valid callable.", p_name));

	bool callable_is_valid = false;
	const int argument_count = p_handler.get_argument_count(&callable_is_valid);
	ERR_FAIL_COND_MSG(callable_is_valid && argument_count != 1,
			vformat("AI tool '%s' must accept exactly one Dictionary argument, but the callable reports %d argument(s).", p_name, argument_count));

	ToolDefinition def;
	def.name = p_name;
	def.description = p_description;
	def.parameters_schema = p_parameters_schema;
	def.handler = p_handler;
	def.usage_hint = p_usage_hint;
	def.output_hint = p_output_hint;
	def.requires_approval = p_requires_approval;
	def.execution_policy = p_execution_policy;
	def.parallel_safe = p_parallel_safe;
	tools[p_name] = def;
	emit_signal("tool_registered", p_name);
}

void AIToolRegistry::unregister_tool(const String &p_name) {
	if (tools.has(p_name)) {
		tools.erase(p_name);
		emit_signal("tool_unregistered", p_name);
	}
}

bool AIToolRegistry::has_tool(const String &p_name) const {
	return tools.has(p_name);
}

TypedArray<Dictionary> AIToolRegistry::get_tool_schemas() const {
	TypedArray<Dictionary> schemas;
	for (const KeyValue<String, ToolDefinition> &E : tools) {
		schemas.push_back(get_tool_schema(E.key));
	}
	return schemas;
}

Dictionary AIToolRegistry::get_tool_schema(const String &p_name) const {
	ERR_FAIL_COND_V(!tools.has(p_name), Dictionary());

	const ToolDefinition &def = tools[p_name];

	// OpenAI function calling format.
	Dictionary schema;
	schema["type"] = "function";

	Dictionary func;
	func["name"] = def.name;
	func["description"] = def.description;
	func["parameters"] = def.parameters_schema;

	schema["function"] = func;
	return schema;
}

String AIToolRegistry::get_tool_usage_guide(const PackedStringArray &p_enabled_tools) const {
	PackedStringArray tool_names = p_enabled_tools;
	if (tool_names.is_empty()) {
		tool_names = get_tool_names();
	}

	String guide;
	for (int i = 0; i < tool_names.size(); i++) {
		const String &tool_name = tool_names[i];
		if (!tools.has(tool_name)) {
			continue;
		}

		const ToolDefinition &def = tools[tool_name];
		if (def.usage_hint.is_empty() && def.output_hint.is_empty()) {
			continue;
		}

		if (!guide.is_empty()) {
			guide += "\n";
		}
		guide += "- " + def.name + ": ";
		if (!def.usage_hint.is_empty()) {
			guide += def.usage_hint.strip_edges();
		}
		if (!def.output_hint.is_empty()) {
			if (!def.usage_hint.is_empty()) {
				guide += " ";
			}
			guide += "Returns " + def.output_hint.strip_edges() + ".";
		}
	}

	return guide;
}

Variant AIToolRegistry::execute_tool(const String &p_name, const Dictionary &p_arguments) {
	ERR_FAIL_COND_V_MSG(!tools.has(p_name), Variant(),
			vformat("AI tool '%s' not found in registry.", p_name));

	const ToolDefinition &def = tools[p_name];

	Variant result;
	Callable::CallError error;
	const Variant argument = p_arguments;
	const Variant *args[1] = { &argument };
	def.handler.callp(args, 1, result, error);

	if (error.error != Callable::CallError::CALL_OK) {
		ERR_PRINT(vformat("Error executing AI tool '%s': %s", p_name, Variant::get_callable_error_text(def.handler, args, 1, error)));
		return vformat("Error: Failed to execute tool '%s'", p_name);
	}

	emit_signal("tool_executed", p_name, p_arguments, result);
	return result;
}

PackedStringArray AIToolRegistry::get_tool_names() const {
	PackedStringArray names;
	for (const KeyValue<String, ToolDefinition> &E : tools) {
		names.push_back(E.key);
	}
	return names;
}

bool AIToolRegistry::tool_requires_approval(const String &p_name) const {
	if (!tools.has(p_name)) {
		return true; // Unknown tools require approval by default.
	}
	return tools[p_name].requires_approval;
}

AIToolRegistry::ExecutionPolicy AIToolRegistry::get_tool_execution_policy(const String &p_name) const {
	if (!tools.has(p_name)) {
		return EXECUTION_MUTATING_EDITOR;
	}
	return tools[p_name].execution_policy;
}

bool AIToolRegistry::is_tool_parallel_safe(const String &p_name) const {
	if (!tools.has(p_name)) {
		return false;
	}
	return tools[p_name].parallel_safe;
}

int AIToolRegistry::get_tool_count() const {
	return tools.size();
}
