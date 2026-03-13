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
	ClassDB::bind_method(D_METHOD("register_tool", "name", "description", "parameters_schema", "handler", "requires_approval"),
			&AIToolRegistry::register_tool, DEFVAL(false));
	ClassDB::bind_method(D_METHOD("unregister_tool", "name"), &AIToolRegistry::unregister_tool);
	ClassDB::bind_method(D_METHOD("has_tool", "name"), &AIToolRegistry::has_tool);
	ClassDB::bind_method(D_METHOD("get_tool_schemas"), &AIToolRegistry::get_tool_schemas);
	ClassDB::bind_method(D_METHOD("get_tool_schema", "name"), &AIToolRegistry::get_tool_schema);
	ClassDB::bind_method(D_METHOD("execute_tool", "name", "arguments"), &AIToolRegistry::execute_tool);
	ClassDB::bind_method(D_METHOD("get_tool_names"), &AIToolRegistry::get_tool_names);
	ClassDB::bind_method(D_METHOD("tool_requires_approval", "name"), &AIToolRegistry::tool_requires_approval);
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
		bool p_requires_approval) {
	ToolDefinition def;
	def.name = p_name;
	def.description = p_description;
	def.parameters_schema = p_parameters_schema;
	def.handler = p_handler;
	def.requires_approval = p_requires_approval;
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

Variant AIToolRegistry::execute_tool(const String &p_name, const Dictionary &p_arguments) {
	ERR_FAIL_COND_V_MSG(!tools.has(p_name), Variant(),
			vformat("AI tool '%s' not found in registry.", p_name));

	const ToolDefinition &def = tools[p_name];

	Variant result;
	Callable::CallError error;
	const Variant *args[1] = { (const Variant *)&p_arguments };
	def.handler.callp(args, 1, result, error);

	if (error.error != Callable::CallError::CALL_OK) {
		ERR_PRINT(vformat("Error executing AI tool '%s': call error %d", p_name, error.error));
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

int AIToolRegistry::get_tool_count() const {
	return tools.size();
}
