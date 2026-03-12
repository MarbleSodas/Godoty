/**************************************************************************/
/*  ai_tool_registry.h                                                    */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "core/object/object.h"
#include "core/variant/callable.h"
#include "core/variant/dictionary.h"
#include "core/variant/typed_array.h"

class AIToolRegistry : public Object {
	GDCLASS(AIToolRegistry, Object);

	static AIToolRegistry *singleton;

protected:
	static void _bind_methods();

public:
	struct ToolDefinition {
		String name;
		String description;
		Dictionary parameters_schema; // JSON Schema for function parameters.
		Callable handler;
		bool requires_approval = false;
	};

private:
	HashMap<String, ToolDefinition> tools;

public:
	static AIToolRegistry *get_singleton();

	// Register a new tool that AI agents can call.
	void register_tool(const String &p_name, const String &p_description,
			const Dictionary &p_parameters_schema, const Callable &p_handler,
			bool p_requires_approval = false);

	// Unregister a tool by name.
	void unregister_tool(const String &p_name);

	// Check if a tool exists.
	bool has_tool(const String &p_name) const;

	// Get all tool schemas formatted for LLM function calling.
	TypedArray<Dictionary> get_tool_schemas() const;

	// Get schema for a specific tool.
	Dictionary get_tool_schema(const String &p_name) const;

	// Execute a tool by name with the given arguments.
	// Returns the result as a Variant (typically a String or Dictionary).
	Variant execute_tool(const String &p_name, const Dictionary &p_arguments);

	// Get list of all registered tool names.
	PackedStringArray get_tool_names() const;

	// Check if a tool requires user approval before execution.
	bool tool_requires_approval(const String &p_name) const;

	// Get the total number of registered tools.
	int get_tool_count() const;

	AIToolRegistry();
	~AIToolRegistry();
};
