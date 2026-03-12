/**************************************************************************/
/*  ai_message.h                                                          */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "core/io/resource.h"
#include "core/variant/dictionary.h"
#include "core/variant/typed_array.h"

class AIMessage : public RefCounted {
	GDCLASS(AIMessage, RefCounted);

public:
	enum Role {
		ROLE_SYSTEM,
		ROLE_USER,
		ROLE_ASSISTANT,
		ROLE_TOOL,
	};

protected:
	static void _bind_methods();

private:
	Role role = ROLE_USER;
	String content;
	TypedArray<Dictionary> tool_calls; // Array of {id, name, arguments} dicts.
	String tool_call_id; // For ROLE_TOOL responses.
	Dictionary metadata;

public:
	void set_role(Role p_role);
	Role get_role() const;

	void set_content(const String &p_content);
	String get_content() const;

	void set_tool_calls(const TypedArray<Dictionary> &p_tool_calls);
	TypedArray<Dictionary> get_tool_calls() const;

	void set_tool_call_id(const String &p_id);
	String get_tool_call_id() const;

	void set_metadata(const Dictionary &p_metadata);
	Dictionary get_metadata() const;

	// Convenience methods.
	bool has_tool_calls() const;
	Dictionary to_dict() const;
	static Ref<AIMessage> from_dict(const Dictionary &p_dict);
	static Ref<AIMessage> create_system(const String &p_content);
	static Ref<AIMessage> create_user(const String &p_content);
	static Ref<AIMessage> create_assistant(const String &p_content, const TypedArray<Dictionary> &p_tool_calls = TypedArray<Dictionary>());
	static Ref<AIMessage> create_tool_result(const String &p_tool_call_id, const String &p_content);

	AIMessage() {}
};

VARIANT_ENUM_CAST(AIMessage::Role);
