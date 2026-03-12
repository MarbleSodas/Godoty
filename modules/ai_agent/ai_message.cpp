/**************************************************************************/
/*  ai_message.cpp                                                        */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "ai_message.h"

void AIMessage::_bind_methods() {
	ClassDB::bind_method(D_METHOD("set_role", "role"), &AIMessage::set_role);
	ClassDB::bind_method(D_METHOD("get_role"), &AIMessage::get_role);
	ClassDB::bind_method(D_METHOD("set_content", "content"), &AIMessage::set_content);
	ClassDB::bind_method(D_METHOD("get_content"), &AIMessage::get_content);
	ClassDB::bind_method(D_METHOD("set_tool_calls", "tool_calls"), &AIMessage::set_tool_calls);
	ClassDB::bind_method(D_METHOD("get_tool_calls"), &AIMessage::get_tool_calls);
	ClassDB::bind_method(D_METHOD("set_tool_call_id", "id"), &AIMessage::set_tool_call_id);
	ClassDB::bind_method(D_METHOD("get_tool_call_id"), &AIMessage::get_tool_call_id);
	ClassDB::bind_method(D_METHOD("set_metadata", "metadata"), &AIMessage::set_metadata);
	ClassDB::bind_method(D_METHOD("get_metadata"), &AIMessage::get_metadata);
	ClassDB::bind_method(D_METHOD("has_tool_calls"), &AIMessage::has_tool_calls);
	ClassDB::bind_method(D_METHOD("to_dict"), &AIMessage::to_dict);
	ClassDB::bind_static_method("AIMessage", D_METHOD("from_dict", "dict"), &AIMessage::from_dict);
	ClassDB::bind_static_method("AIMessage", D_METHOD("create_system", "content"), &AIMessage::create_system);
	ClassDB::bind_static_method("AIMessage", D_METHOD("create_user", "content"), &AIMessage::create_user);
	ClassDB::bind_static_method("AIMessage", D_METHOD("create_assistant", "content", "tool_calls"), &AIMessage::create_assistant, DEFVAL(TypedArray<Dictionary>()));
	ClassDB::bind_static_method("AIMessage", D_METHOD("create_tool_result", "tool_call_id", "content"), &AIMessage::create_tool_result);

	ADD_PROPERTY(PropertyInfo(Variant::INT, "role", PROPERTY_HINT_ENUM, "System,User,Assistant,Tool"), "set_role", "get_role");
	ADD_PROPERTY(PropertyInfo(Variant::STRING, "content", PROPERTY_HINT_MULTILINE_TEXT), "set_content", "get_content");
	ADD_PROPERTY(PropertyInfo(Variant::ARRAY, "tool_calls", PROPERTY_HINT_ARRAY_TYPE, vformat("%s/%s:%s", Variant::DICTIONARY, PROPERTY_HINT_NONE, "")), "set_tool_calls", "get_tool_calls");
	ADD_PROPERTY(PropertyInfo(Variant::STRING, "tool_call_id"), "set_tool_call_id", "get_tool_call_id");
	ADD_PROPERTY(PropertyInfo(Variant::DICTIONARY, "metadata"), "set_metadata", "get_metadata");

	BIND_ENUM_CONSTANT(ROLE_SYSTEM);
	BIND_ENUM_CONSTANT(ROLE_USER);
	BIND_ENUM_CONSTANT(ROLE_ASSISTANT);
	BIND_ENUM_CONSTANT(ROLE_TOOL);
}

void AIMessage::set_role(Role p_role) {
	role = p_role;
}

AIMessage::Role AIMessage::get_role() const {
	return role;
}

void AIMessage::set_content(const String &p_content) {
	content = p_content;
}

String AIMessage::get_content() const {
	return content;
}

void AIMessage::set_tool_calls(const TypedArray<Dictionary> &p_tool_calls) {
	tool_calls = p_tool_calls;
}

TypedArray<Dictionary> AIMessage::get_tool_calls() const {
	return tool_calls;
}

void AIMessage::set_tool_call_id(const String &p_id) {
	tool_call_id = p_id;
}

String AIMessage::get_tool_call_id() const {
	return tool_call_id;
}

void AIMessage::set_metadata(const Dictionary &p_metadata) {
	metadata = p_metadata;
}

Dictionary AIMessage::get_metadata() const {
	return metadata;
}

bool AIMessage::has_tool_calls() const {
	return tool_calls.size() > 0;
}

Dictionary AIMessage::to_dict() const {
	Dictionary dict;
	switch (role) {
		case ROLE_SYSTEM:
			dict["role"] = "system";
			break;
		case ROLE_USER:
			dict["role"] = "user";
			break;
		case ROLE_ASSISTANT:
			dict["role"] = "assistant";
			break;
		case ROLE_TOOL:
			dict["role"] = "tool";
			break;
	}
	dict["content"] = content;
	if (tool_calls.size() > 0) {
		dict["tool_calls"] = tool_calls;
	}
	if (!tool_call_id.is_empty()) {
		dict["tool_call_id"] = tool_call_id;
	}
	if (!metadata.is_empty()) {
		dict["metadata"] = metadata;
	}
	return dict;
}

Ref<AIMessage> AIMessage::from_dict(const Dictionary &p_dict) {
	Ref<AIMessage> msg;
	msg.instantiate();
	String role_str = p_dict.get("role", "user");
	if (role_str == "system") {
		msg->set_role(ROLE_SYSTEM);
	} else if (role_str == "user") {
		msg->set_role(ROLE_USER);
	} else if (role_str == "assistant") {
		msg->set_role(ROLE_ASSISTANT);
	} else if (role_str == "tool") {
		msg->set_role(ROLE_TOOL);
	}
	msg->set_content(p_dict.get("content", ""));
	if (p_dict.has("tool_calls")) {
		msg->set_tool_calls(p_dict["tool_calls"]);
	}
	if (p_dict.has("tool_call_id")) {
		msg->set_tool_call_id(p_dict["tool_call_id"]);
	}
	if (p_dict.has("metadata")) {
		msg->set_metadata(p_dict["metadata"]);
	}
	return msg;
}

Ref<AIMessage> AIMessage::create_system(const String &p_content) {
	Ref<AIMessage> msg;
	msg.instantiate();
	msg->set_role(ROLE_SYSTEM);
	msg->set_content(p_content);
	return msg;
}

Ref<AIMessage> AIMessage::create_user(const String &p_content) {
	Ref<AIMessage> msg;
	msg.instantiate();
	msg->set_role(ROLE_USER);
	msg->set_content(p_content);
	return msg;
}

Ref<AIMessage> AIMessage::create_assistant(const String &p_content, const TypedArray<Dictionary> &p_tool_calls) {
	Ref<AIMessage> msg;
	msg.instantiate();
	msg->set_role(ROLE_ASSISTANT);
	msg->set_content(p_content);
	msg->set_tool_calls(p_tool_calls);
	return msg;
}

Ref<AIMessage> AIMessage::create_tool_result(const String &p_tool_call_id, const String &p_content) {
	Ref<AIMessage> msg;
	msg.instantiate();
	msg->set_role(ROLE_TOOL);
	msg->set_content(p_content);
	msg->set_tool_call_id(p_tool_call_id);
	return msg;
}
