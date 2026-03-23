/**************************************************************************/
/*  ai_agent_config.h                                                     */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "core/io/resource.h"
#include "core/templates/hash_map.h"
#include "core/templates/vector.h"

class AIAgentConfig : public Resource {
	GDCLASS(AIAgentConfig, Resource);

public:
	enum ProviderType {
		PROVIDER_OPENAI,
		PROVIDER_ANTHROPIC,
		PROVIDER_MINIMAX,
		PROVIDER_LOCAL,
		PROVIDER_CUSTOM,
	};

	enum ApprovalPolicy {
		APPROVAL_ASK,
		APPROVAL_ALWAYS_ALLOW,
	};

	struct ProviderSettings {
		String api_key;
		String model_name;
		String base_url;
		bool is_saved = false;
	};

protected:
	static void _bind_methods();

private:
	ProviderType active_provider_type = PROVIDER_OPENAI;
	ApprovalPolicy approval_policy = APPROVAL_ASK;
	HashMap<int, ProviderSettings> provider_settings;
	HashMap<int, String> mode_model_overrides; // AIAgentModeId -> model_name.

	ProviderSettings &_get_provider_settings_mutable(ProviderType p_type);
	const ProviderSettings *_get_provider_settings_const(ProviderType p_type) const;
	bool _set_provider_settings(ProviderType p_type, const ProviderSettings &p_settings);

public:
	void set_provider_type(ProviderType p_type);
	ProviderType get_provider_type() const;
	void set_approval_policy(ApprovalPolicy p_policy);
	ApprovalPolicy get_approval_policy() const;

	void set_api_key(const String &p_key);
	String get_api_key() const;

	void set_model_name(const String &p_name);
	String get_model_name() const;

	void set_base_url(const String &p_url);
	String get_base_url() const;

	void set_provider_api_key(ProviderType p_type, const String &p_key);
	String get_provider_api_key(ProviderType p_type) const;

	void set_provider_model_name(ProviderType p_type, const String &p_name);
	String get_provider_model_name(ProviderType p_type) const;

	void set_provider_base_url(ProviderType p_type, const String &p_url);
	String get_provider_base_url(ProviderType p_type) const;

	void set_provider_saved(ProviderType p_type, bool p_saved);
	bool is_provider_saved(ProviderType p_type) const;
	bool is_provider_configured(ProviderType p_type) const;
	Vector<ProviderType> get_saved_provider_types() const;

	// Per-mode model overrides.
	void set_mode_model_override(int p_mode, const String &p_model);
	String get_mode_model_override(int p_mode) const;
	void clear_mode_model_override(int p_mode);
	bool has_mode_model_override(int p_mode) const;

	String get_provider_name() const;
	String get_provider_description() const;
	String get_default_model_name() const;
	String get_api_key_placeholder() const;
	PackedStringArray get_recommended_models() const;
	bool provider_requires_api_key() const;
	bool is_configured() const;
	void apply_provider_defaults(bool p_force_model = false, bool p_reset_base_url = false);

	// Get the appropriate default base URL for the selected provider.
	String get_effective_base_url() const;

	AIAgentConfig() {}
};

VARIANT_ENUM_CAST(AIAgentConfig::ProviderType);
VARIANT_ENUM_CAST(AIAgentConfig::ApprovalPolicy);
