/**************************************************************************/
/*  ai_agent_config.cpp                                                   */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "ai_agent_config.h"
#include "ai_agent_mode.h"

void AIAgentConfig::_bind_methods() {
	ClassDB::bind_method(D_METHOD("set_provider_type", "type"), &AIAgentConfig::set_provider_type);
	ClassDB::bind_method(D_METHOD("get_provider_type"), &AIAgentConfig::get_provider_type);
	ClassDB::bind_method(D_METHOD("set_approval_policy", "policy"), &AIAgentConfig::set_approval_policy);
	ClassDB::bind_method(D_METHOD("get_approval_policy"), &AIAgentConfig::get_approval_policy);
	ClassDB::bind_method(D_METHOD("set_api_key", "key"), &AIAgentConfig::set_api_key);
	ClassDB::bind_method(D_METHOD("get_api_key"), &AIAgentConfig::get_api_key);
	ClassDB::bind_method(D_METHOD("set_model_name", "name"), &AIAgentConfig::set_model_name);
	ClassDB::bind_method(D_METHOD("get_model_name"), &AIAgentConfig::get_model_name);
	ClassDB::bind_method(D_METHOD("set_base_url", "url"), &AIAgentConfig::set_base_url);
	ClassDB::bind_method(D_METHOD("get_base_url"), &AIAgentConfig::get_base_url);
	ClassDB::bind_method(D_METHOD("get_provider_name"), &AIAgentConfig::get_provider_name);
	ClassDB::bind_method(D_METHOD("get_provider_description"), &AIAgentConfig::get_provider_description);
	ClassDB::bind_method(D_METHOD("get_default_model_name"), &AIAgentConfig::get_default_model_name);
	ClassDB::bind_method(D_METHOD("get_api_key_placeholder"), &AIAgentConfig::get_api_key_placeholder);
	ClassDB::bind_method(D_METHOD("get_recommended_models"), &AIAgentConfig::get_recommended_models);
	ClassDB::bind_method(D_METHOD("provider_requires_api_key"), &AIAgentConfig::provider_requires_api_key);
	ClassDB::bind_method(D_METHOD("is_configured"), &AIAgentConfig::is_configured);
	ClassDB::bind_method(D_METHOD("apply_provider_defaults", "force_model", "reset_base_url"), &AIAgentConfig::apply_provider_defaults, DEFVAL(false), DEFVAL(false));
	ClassDB::bind_method(D_METHOD("get_effective_base_url"), &AIAgentConfig::get_effective_base_url);
	ClassDB::bind_method(D_METHOD("set_mode_model_override", "mode", "model"), &AIAgentConfig::set_mode_model_override);
	ClassDB::bind_method(D_METHOD("get_mode_model_override", "mode"), &AIAgentConfig::get_mode_model_override);
	ClassDB::bind_method(D_METHOD("clear_mode_model_override", "mode"), &AIAgentConfig::clear_mode_model_override);
	ClassDB::bind_method(D_METHOD("has_mode_model_override", "mode"), &AIAgentConfig::has_mode_model_override);

	ADD_GROUP("Provider", "");
	ADD_PROPERTY(PropertyInfo(Variant::INT, "provider_type", PROPERTY_HINT_ENUM, "OpenAI,Anthropic,MiniMax,Local,Custom"), "set_provider_type", "get_provider_type");
	ADD_PROPERTY(PropertyInfo(Variant::INT, "approval_policy", PROPERTY_HINT_ENUM, "Ask,Always Allow"), "set_approval_policy", "get_approval_policy");
	ADD_PROPERTY(PropertyInfo(Variant::STRING, "api_key", PROPERTY_HINT_PASSWORD), "set_api_key", "get_api_key");
	ADD_PROPERTY(PropertyInfo(Variant::STRING, "model_name"), "set_model_name", "get_model_name");
	ADD_PROPERTY(PropertyInfo(Variant::STRING, "base_url", PROPERTY_HINT_NONE, "", PROPERTY_USAGE_DEFAULT), "set_base_url", "get_base_url");

	BIND_ENUM_CONSTANT(PROVIDER_OPENAI);
	BIND_ENUM_CONSTANT(PROVIDER_ANTHROPIC);
	BIND_ENUM_CONSTANT(PROVIDER_MINIMAX);
	BIND_ENUM_CONSTANT(PROVIDER_LOCAL);
	BIND_ENUM_CONSTANT(PROVIDER_CUSTOM);
	BIND_ENUM_CONSTANT(APPROVAL_ASK);
	BIND_ENUM_CONSTANT(APPROVAL_ALWAYS_ALLOW);
}

AIAgentConfig::ProviderSettings &AIAgentConfig::_get_provider_settings_mutable(ProviderType p_type) {
	HashMap<int, ProviderSettings>::Iterator it = provider_settings.find((int)p_type);
	if (it != provider_settings.end()) {
		return it->value;
	}

	ProviderSettings defaults;
	defaults.model_name = ai_agent_get_provider_descriptor(p_type).default_model;
	provider_settings.insert((int)p_type, defaults);
	return provider_settings[(int)p_type];
}

const AIAgentConfig::ProviderSettings *AIAgentConfig::_get_provider_settings_const(ProviderType p_type) const {
	HashMap<int, ProviderSettings>::ConstIterator it = provider_settings.find((int)p_type);
	if (it == provider_settings.end()) {
		return nullptr;
	}
	return &it->value;
}

bool AIAgentConfig::_set_provider_settings(ProviderType p_type, const ProviderSettings &p_settings) {
	const int key = (int)p_type;
	HashMap<int, ProviderSettings>::Iterator it = provider_settings.find(key);
	if (it != provider_settings.end() && it->value.api_key == p_settings.api_key &&
			it->value.model_name == p_settings.model_name &&
			it->value.base_url == p_settings.base_url &&
			it->value.is_saved == p_settings.is_saved) {
		return false;
	}

	provider_settings.insert(key, p_settings);
	return true;
}

void AIAgentConfig::set_provider_type(ProviderType p_type) {
	if (active_provider_type == p_type) {
		return;
	}
	active_provider_type = p_type;
	emit_changed();
}

AIAgentConfig::ProviderType AIAgentConfig::get_provider_type() const {
	return active_provider_type;
}

void AIAgentConfig::set_approval_policy(ApprovalPolicy p_policy) {
	if (approval_policy == p_policy) {
		return;
	}
	approval_policy = p_policy;
	emit_changed();
}

AIAgentConfig::ApprovalPolicy AIAgentConfig::get_approval_policy() const {
	return approval_policy;
}

void AIAgentConfig::set_api_key(const String &p_key) {
	set_provider_api_key(active_provider_type, p_key);
}

String AIAgentConfig::get_api_key() const {
	return get_provider_api_key(active_provider_type);
}

void AIAgentConfig::set_model_name(const String &p_name) {
	set_provider_model_name(active_provider_type, p_name);
}

String AIAgentConfig::get_model_name() const {
	return get_provider_model_name(active_provider_type);
}

void AIAgentConfig::set_base_url(const String &p_url) {
	set_provider_base_url(active_provider_type, p_url);
}

String AIAgentConfig::get_base_url() const {
	return get_provider_base_url(active_provider_type);
}

void AIAgentConfig::set_provider_api_key(ProviderType p_type, const String &p_key) {
	ProviderSettings settings = _get_provider_settings_mutable(p_type);
	if (settings.api_key == p_key) {
		return;
	}
	settings.api_key = p_key;
	if (_set_provider_settings(p_type, settings)) {
		emit_changed();
	}
}

String AIAgentConfig::get_provider_api_key(ProviderType p_type) const {
	const ProviderSettings *settings = _get_provider_settings_const(p_type);
	return settings ? settings->api_key : String();
}

void AIAgentConfig::set_provider_model_name(ProviderType p_type, const String &p_name) {
	ProviderSettings settings = _get_provider_settings_mutable(p_type);
	if (settings.model_name == p_name) {
		return;
	}
	settings.model_name = p_name;
	if (_set_provider_settings(p_type, settings)) {
		emit_changed();
	}
}

String AIAgentConfig::get_provider_model_name(ProviderType p_type) const {
	const ProviderSettings *settings = _get_provider_settings_const(p_type);
	if (!settings) {
		return ai_agent_get_provider_descriptor(p_type).default_model;
	}
	return settings->model_name.is_empty() ? ai_agent_get_provider_descriptor(p_type).default_model : settings->model_name;
}

void AIAgentConfig::set_provider_base_url(ProviderType p_type, const String &p_url) {
	ProviderSettings settings = _get_provider_settings_mutable(p_type);
	if (settings.base_url == p_url) {
		return;
	}
	settings.base_url = p_url;
	if (_set_provider_settings(p_type, settings)) {
		emit_changed();
	}
}

String AIAgentConfig::get_provider_base_url(ProviderType p_type) const {
	const ProviderSettings *settings = _get_provider_settings_const(p_type);
	return settings ? settings->base_url : String();
}

void AIAgentConfig::set_provider_saved(ProviderType p_type, bool p_saved) {
	ProviderSettings settings = _get_provider_settings_mutable(p_type);
	if (settings.is_saved == p_saved) {
		return;
	}
	settings.is_saved = p_saved;
	if (_set_provider_settings(p_type, settings)) {
		emit_changed();
	}
}

bool AIAgentConfig::is_provider_saved(ProviderType p_type) const {
	const ProviderSettings *settings = _get_provider_settings_const(p_type);
	return settings ? settings->is_saved : false;
}

bool AIAgentConfig::is_provider_configured(ProviderType p_type) const {
	if (!is_provider_saved(p_type)) {
		return false;
	}
	if (!ai_agent_get_provider_descriptor(p_type).requires_api_key) {
		return true;
	}
	return !get_provider_api_key(p_type).is_empty();
}

Vector<AIAgentConfig::ProviderType> AIAgentConfig::get_saved_provider_types() const {
	Vector<ProviderType> providers;
	for (int i = 0; i <= (int)PROVIDER_CUSTOM; i++) {
		const ProviderType provider = (ProviderType)i;
		if (is_provider_saved(provider)) {
			providers.push_back(provider);
		}
	}
	return providers;
}

String AIAgentConfig::get_provider_name() const {
	return ai_agent_get_provider_descriptor(active_provider_type).name;
}

String AIAgentConfig::get_provider_description() const {
	return ai_agent_get_provider_descriptor(active_provider_type).description;
}

String AIAgentConfig::get_default_model_name() const {
	return ai_agent_get_provider_descriptor(active_provider_type).default_model;
}

String AIAgentConfig::get_api_key_placeholder() const {
	return ai_agent_get_provider_descriptor(active_provider_type).api_key_placeholder;
}

PackedStringArray AIAgentConfig::get_recommended_models() const {
	return ai_agent_get_provider_descriptor(active_provider_type).recommended_models;
}

bool AIAgentConfig::provider_requires_api_key() const {
	return ai_agent_get_provider_descriptor(active_provider_type).requires_api_key;
}

bool AIAgentConfig::is_configured() const {
	return is_provider_configured(active_provider_type);
}

void AIAgentConfig::apply_provider_defaults(bool p_force_model, bool p_reset_base_url) {
	bool changed = false;
	ProviderSettings settings = _get_provider_settings_mutable(active_provider_type);
	const String default_model = ai_agent_get_provider_descriptor(active_provider_type).default_model;

	if (p_force_model || settings.model_name.is_empty()) {
		if (settings.model_name != default_model) {
			settings.model_name = default_model;
			changed = true;
		}
	}

	if (p_reset_base_url && !settings.base_url.is_empty()) {
		settings.base_url = "";
		changed = true;
	}

	if (changed && _set_provider_settings(active_provider_type, settings)) {
		emit_changed();
	}
}

String AIAgentConfig::get_effective_base_url() const {
	const String base_url = get_provider_base_url(active_provider_type);
	if (!base_url.is_empty()) {
		return base_url;
	}
	return ai_agent_get_provider_descriptor(active_provider_type).default_base_url;
}

void AIAgentConfig::set_mode_model_override(int p_mode, const String &p_model) {
	if (p_model.is_empty()) {
		mode_model_overrides.erase(p_mode);
	} else {
		mode_model_overrides.insert(p_mode, p_model);
	}
	emit_changed();
}

String AIAgentConfig::get_mode_model_override(int p_mode) const {
	HashMap<int, String>::ConstIterator it = mode_model_overrides.find(p_mode);
	if (it != mode_model_overrides.end()) {
		return it->value;
	}
	return String();
}

void AIAgentConfig::clear_mode_model_override(int p_mode) {
	if (mode_model_overrides.has(p_mode)) {
		mode_model_overrides.erase(p_mode);
		emit_changed();
	}
}

bool AIAgentConfig::has_mode_model_override(int p_mode) const {
	return mode_model_overrides.has(p_mode) && !mode_model_overrides[p_mode].is_empty();
}
