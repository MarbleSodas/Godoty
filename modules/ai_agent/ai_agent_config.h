/**************************************************************************/
/*  ai_agent_config.h                                                     */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "core/io/resource.h"

class AIAgentConfig : public Resource {
	GDCLASS(AIAgentConfig, Resource);

public:
	enum ProviderType {
		PROVIDER_OPENAI,
		PROVIDER_ANTHROPIC,
		PROVIDER_LOCAL,
		PROVIDER_CUSTOM,
	};

protected:
	static void _bind_methods();

private:
	ProviderType provider_type = PROVIDER_OPENAI;
	String api_key;
	String model_name = "gpt-4o";
	String base_url;
	float temperature = 0.7f;
	int max_tokens = 4096;
	String system_prompt;
	PackedStringArray enabled_tools;
	bool stream_responses = true;

public:
	void set_provider_type(ProviderType p_type);
	ProviderType get_provider_type() const;

	void set_api_key(const String &p_key);
	String get_api_key() const;

	void set_model_name(const String &p_name);
	String get_model_name() const;

	void set_base_url(const String &p_url);
	String get_base_url() const;

	void set_temperature(float p_temp);
	float get_temperature() const;

	void set_max_tokens(int p_max);
	int get_max_tokens() const;

	void set_system_prompt(const String &p_prompt);
	String get_system_prompt() const;

	void set_enabled_tools(const PackedStringArray &p_tools);
	PackedStringArray get_enabled_tools() const;

	void set_stream_responses(bool p_stream);
	bool get_stream_responses() const;

	// Get the appropriate default base URL for the selected provider.
	String get_effective_base_url() const;

	AIAgentConfig() {}
};

VARIANT_ENUM_CAST(AIAgentConfig::ProviderType);
