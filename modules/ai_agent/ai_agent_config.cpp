/**************************************************************************/
/*  ai_agent_config.cpp                                                   */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "ai_agent_config.h"

void AIAgentConfig::_bind_methods() {
	ClassDB::bind_method(D_METHOD("set_provider_type", "type"), &AIAgentConfig::set_provider_type);
	ClassDB::bind_method(D_METHOD("get_provider_type"), &AIAgentConfig::get_provider_type);
	ClassDB::bind_method(D_METHOD("set_api_key", "key"), &AIAgentConfig::set_api_key);
	ClassDB::bind_method(D_METHOD("get_api_key"), &AIAgentConfig::get_api_key);
	ClassDB::bind_method(D_METHOD("set_model_name", "name"), &AIAgentConfig::set_model_name);
	ClassDB::bind_method(D_METHOD("get_model_name"), &AIAgentConfig::get_model_name);
	ClassDB::bind_method(D_METHOD("set_base_url", "url"), &AIAgentConfig::set_base_url);
	ClassDB::bind_method(D_METHOD("get_base_url"), &AIAgentConfig::get_base_url);
	ClassDB::bind_method(D_METHOD("set_temperature", "temperature"), &AIAgentConfig::set_temperature);
	ClassDB::bind_method(D_METHOD("get_temperature"), &AIAgentConfig::get_temperature);
	ClassDB::bind_method(D_METHOD("set_max_tokens", "max_tokens"), &AIAgentConfig::set_max_tokens);
	ClassDB::bind_method(D_METHOD("get_max_tokens"), &AIAgentConfig::get_max_tokens);
	ClassDB::bind_method(D_METHOD("set_system_prompt", "prompt"), &AIAgentConfig::set_system_prompt);
	ClassDB::bind_method(D_METHOD("get_system_prompt"), &AIAgentConfig::get_system_prompt);
	ClassDB::bind_method(D_METHOD("set_enabled_tools", "tools"), &AIAgentConfig::set_enabled_tools);
	ClassDB::bind_method(D_METHOD("get_enabled_tools"), &AIAgentConfig::get_enabled_tools);
	ClassDB::bind_method(D_METHOD("set_stream_responses", "stream"), &AIAgentConfig::set_stream_responses);
	ClassDB::bind_method(D_METHOD("get_stream_responses"), &AIAgentConfig::get_stream_responses);
	ClassDB::bind_method(D_METHOD("get_effective_base_url"), &AIAgentConfig::get_effective_base_url);

	ADD_GROUP("Provider", "");
	ADD_PROPERTY(PropertyInfo(Variant::INT, "provider_type", PROPERTY_HINT_ENUM, "OpenAI,Anthropic,MiniMax,Local,Custom"), "set_provider_type", "get_provider_type");
	ADD_PROPERTY(PropertyInfo(Variant::STRING, "api_key", PROPERTY_HINT_PASSWORD), "set_api_key", "get_api_key");
	ADD_PROPERTY(PropertyInfo(Variant::STRING, "model_name"), "set_model_name", "get_model_name");
	ADD_PROPERTY(PropertyInfo(Variant::STRING, "base_url", PROPERTY_HINT_NONE, "", PROPERTY_USAGE_DEFAULT), "set_base_url", "get_base_url");

	ADD_GROUP("Generation", "");
	ADD_PROPERTY(PropertyInfo(Variant::FLOAT, "temperature", PROPERTY_HINT_RANGE, "0.0,2.0,0.01"), "set_temperature", "get_temperature");
	ADD_PROPERTY(PropertyInfo(Variant::INT, "max_tokens", PROPERTY_HINT_RANGE, "1,200000,1"), "set_max_tokens", "get_max_tokens");
	ADD_PROPERTY(PropertyInfo(Variant::BOOL, "stream_responses"), "set_stream_responses", "get_stream_responses");

	ADD_GROUP("Prompt", "");
	ADD_PROPERTY(PropertyInfo(Variant::STRING, "system_prompt", PROPERTY_HINT_MULTILINE_TEXT), "set_system_prompt", "get_system_prompt");

	ADD_GROUP("Tools", "");
	ADD_PROPERTY(PropertyInfo(Variant::PACKED_STRING_ARRAY, "enabled_tools"), "set_enabled_tools", "get_enabled_tools");

	BIND_ENUM_CONSTANT(PROVIDER_OPENAI);
	BIND_ENUM_CONSTANT(PROVIDER_ANTHROPIC);
	BIND_ENUM_CONSTANT(PROVIDER_MINIMAX);
	BIND_ENUM_CONSTANT(PROVIDER_LOCAL);
	BIND_ENUM_CONSTANT(PROVIDER_CUSTOM);
}

void AIAgentConfig::set_provider_type(ProviderType p_type) {
	provider_type = p_type;
	emit_changed();
}

AIAgentConfig::ProviderType AIAgentConfig::get_provider_type() const {
	return provider_type;
}

void AIAgentConfig::set_api_key(const String &p_key) {
	api_key = p_key;
	emit_changed();
}

String AIAgentConfig::get_api_key() const {
	return api_key;
}

void AIAgentConfig::set_model_name(const String &p_name) {
	model_name = p_name;
	emit_changed();
}

String AIAgentConfig::get_model_name() const {
	return model_name;
}

void AIAgentConfig::set_base_url(const String &p_url) {
	base_url = p_url;
	emit_changed();
}

String AIAgentConfig::get_base_url() const {
	return base_url;
}

void AIAgentConfig::set_temperature(float p_temp) {
	temperature = CLAMP(p_temp, 0.0f, 2.0f);
	emit_changed();
}

float AIAgentConfig::get_temperature() const {
	return temperature;
}

void AIAgentConfig::set_max_tokens(int p_max) {
	max_tokens = MAX(1, p_max);
	emit_changed();
}

int AIAgentConfig::get_max_tokens() const {
	return max_tokens;
}

void AIAgentConfig::set_system_prompt(const String &p_prompt) {
	system_prompt = p_prompt;
	emit_changed();
}

String AIAgentConfig::get_system_prompt() const {
	return system_prompt;
}

void AIAgentConfig::set_enabled_tools(const PackedStringArray &p_tools) {
	enabled_tools = p_tools;
	emit_changed();
}

PackedStringArray AIAgentConfig::get_enabled_tools() const {
	return enabled_tools;
}

void AIAgentConfig::set_stream_responses(bool p_stream) {
	stream_responses = p_stream;
	emit_changed();
}

bool AIAgentConfig::get_stream_responses() const {
	return stream_responses;
}

String AIAgentConfig::get_effective_base_url() const {
	if (!base_url.is_empty()) {
		return base_url;
	}
	switch (provider_type) {
		case PROVIDER_OPENAI:
			return "https://api.openai.com/v1";
		case PROVIDER_ANTHROPIC:
			return "https://api.anthropic.com/v1";
		case PROVIDER_MINIMAX:
			return "https://api.minimax.chat/v1";
		case PROVIDER_LOCAL:
			return "http://localhost:11434"; // Ollama default.
		case PROVIDER_CUSTOM:
			return "";
	}
	return "";
}
