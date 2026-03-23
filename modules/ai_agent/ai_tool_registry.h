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
	enum ExecutionPolicy {
		EXECUTION_READ_ONLY,
		EXECUTION_MUTATING_FILE,
		EXECUTION_MUTATING_SCENE,
		EXECUTION_MUTATING_EDITOR,
	};

	struct ToolDefinition {
		String name;
		String description;
		Dictionary parameters_schema; // JSON Schema for function parameters.
		Callable handler;
		String usage_hint;
		String output_hint;
		bool requires_approval = false;
		ExecutionPolicy execution_policy = EXECUTION_READ_ONLY;
		bool parallel_safe = false;
	};

private:
	HashMap<String, ToolDefinition> tools;

public:
	static AIToolRegistry *get_singleton();

	// Register a new tool that AI agents can call.
	void register_tool(const String &p_name, const String &p_description,
			const Dictionary &p_parameters_schema, const Callable &p_handler,
			bool p_requires_approval = false,
			ExecutionPolicy p_execution_policy = EXECUTION_READ_ONLY,
			bool p_parallel_safe = false,
			const String &p_usage_hint = String(),
			const String &p_output_hint = String());

	// Unregister a tool by name.
	void unregister_tool(const String &p_name);

	// Check if a tool exists.
	bool has_tool(const String &p_name) const;

	// Get all tool schemas formatted for LLM function calling.
	TypedArray<Dictionary> get_tool_schemas() const;

	// Get schema for a specific tool.
	Dictionary get_tool_schema(const String &p_name) const;
	String get_tool_usage_guide(const PackedStringArray &p_enabled_tools = PackedStringArray()) const;

	// Execute a tool by name with the given arguments.
	// Returns the result as a Variant (typically a String or Dictionary).
	Variant execute_tool(const String &p_name, const Dictionary &p_arguments);

	// Get list of all registered tool names.
	PackedStringArray get_tool_names() const;

	// Check if a tool requires user approval before execution.
	bool tool_requires_approval(const String &p_name) const;
	ExecutionPolicy get_tool_execution_policy(const String &p_name) const;
	bool is_tool_parallel_safe(const String &p_name) const;

	// Get the total number of registered tools.
	int get_tool_count() const;

	AIToolRegistry();
	~AIToolRegistry();
};
