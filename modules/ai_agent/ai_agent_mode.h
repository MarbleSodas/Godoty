/**************************************************************************/
/*  ai_agent_mode.h                                                       */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "ai_agent_config.h"

enum AIAgentModeId {
	AI_AGENT_MODE_ASK,
	AI_AGENT_MODE_EDIT,
	AI_AGENT_MODE_PLAN,
	AI_AGENT_MODE_DEBUG,
	AI_AGENT_MODE_ORCHESTRATE,
};

struct AIProviderDescriptor {
	AIAgentConfig::ProviderType provider_type = AIAgentConfig::PROVIDER_OPENAI;
	String name;
	String description;
	String icon_name;
	String default_model;
	String default_base_url;
	String api_key_placeholder;
	PackedStringArray recommended_models;
	bool requires_api_key = true;
	bool supports_temperature = false;
	bool supports_max_output_tokens = true;
	int max_output_tokens_limit = 4096;
	int default_context_window = 32768;
};

struct AIAgentModeProfile {
	AIAgentModeId id = AI_AGENT_MODE_ASK;
	String title;
	String description;
	String icon_name;
	String harness_prompt;
	PackedStringArray allowed_tools;
	float temperature = 0.0f;
	int preferred_max_output_tokens = 4096;
};

struct ResolvedAgentRunConfig {
	AIProviderDescriptor provider;
	AIAgentModeProfile mode;
	String model_name;
	String base_url;
	PackedStringArray allowed_tools;
	bool use_temperature = false;
	float temperature = 0.0f;
	bool use_max_output_tokens = true;
	int max_output_tokens = 4096;
	bool stream_responses = true;
	int estimated_context_window = 32768;
};

String ai_agent_mode_get_name(AIAgentModeId p_mode);
AIProviderDescriptor ai_agent_get_provider_descriptor(AIAgentConfig::ProviderType p_provider);
AIAgentModeProfile ai_agent_get_mode_profile(AIAgentModeId p_mode);
ResolvedAgentRunConfig ai_agent_resolve_run_config(const Ref<AIAgentConfig> &p_config, AIAgentModeId p_mode, const PackedStringArray &p_available_tools);
int ai_agent_estimate_model_context_window(const AIProviderDescriptor &p_provider, const String &p_model_name);

VARIANT_ENUM_CAST(AIAgentModeId);
