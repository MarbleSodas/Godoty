/**************************************************************************/
/*  ai_settings_panel.cpp                                                 */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#ifdef TOOLS_ENABLED

#include "ai_settings_panel.h"

#include "modules/ai_agent/ai_agent_mode.h"
#include "modules/ai_agent/providers/ai_provider.h"
#include "modules/ai_agent/providers/anthropic_provider.h"
#include "modules/ai_agent/providers/local_provider.h"
#include "modules/ai_agent/providers/minimax_provider.h"
#include "modules/ai_agent/providers/openai_provider.h"

#include "editor/editor_string_names.h"
#include "editor/settings/editor_settings.h"
#include "editor/themes/editor_scale.h"

#include "core/os/os.h"
#include "scene/gui/button.h"
#include "scene/gui/flow_container.h"
#include "scene/gui/label.h"
#include "scene/gui/line_edit.h"
#include "scene/gui/margin_container.h"
#include "scene/gui/panel_container.h"
#include "scene/main/timer.h"
#include "scene/resources/style_box_flat.h"

namespace {

static const char *AI_SETTING_ACTIVE_PROVIDER_TYPE = "_ai_agent/active_provider_type";
static const char *AI_SETTING_PROVIDER_TYPE = "_ai_agent/provider_type";
static const char *AI_SETTING_APPROVAL_POLICY = "_ai_agent/approval_policy";
static const char *AI_SETTING_API_KEY = "_ai_agent/api_key";
static const char *AI_SETTING_MODEL_NAME = "_ai_agent/model_name";
static const char *AI_SETTING_BASE_URL = "_ai_agent/base_url";
static constexpr uint64_t MODEL_SUGGESTION_CACHE_TTL_MSEC = 2 * 60 * 1000;
static constexpr double MODEL_SUGGESTION_REFRESH_DEBOUNCE_SEC = 0.45;

String _mode_override_setting_key(AIAgentModeId p_mode) {
	return vformat("_ai_agent/mode_overrides/%s/model_name", ai_agent_mode_get_name(p_mode).to_lower());
}

PackedInt32Array _mode_override_modes() {
	PackedInt32Array modes;
	modes.push_back((int)AI_AGENT_MODE_ASK);
	modes.push_back((int)AI_AGENT_MODE_EDIT);
	modes.push_back((int)AI_AGENT_MODE_PLAN);
	modes.push_back((int)AI_AGENT_MODE_DEBUG);
	return modes;
}

String _provider_settings_prefix(AIAgentConfig::ProviderType p_provider) {
	switch (p_provider) {
		case AIAgentConfig::PROVIDER_OPENAI:
			return "_ai_agent/providers/openai";
		case AIAgentConfig::PROVIDER_ANTHROPIC:
			return "_ai_agent/providers/anthropic";
		case AIAgentConfig::PROVIDER_MINIMAX:
			return "_ai_agent/providers/minimax";
		case AIAgentConfig::PROVIDER_LOCAL:
			return "_ai_agent/providers/local";
		case AIAgentConfig::PROVIDER_CUSTOM:
			return "_ai_agent/providers/custom";
	}

	return "_ai_agent/providers/openai";
}

String _provider_setting_key(AIAgentConfig::ProviderType p_provider, const String &p_suffix) {
	return _provider_settings_prefix(p_provider).path_join(p_suffix);
}

bool _has_saved_provider_entries(EditorSettings *p_settings) {
	for (int i = 0; i <= (int)AIAgentConfig::PROVIDER_CUSTOM; i++) {
		const AIAgentConfig::ProviderType provider = (AIAgentConfig::ProviderType)i;
		if (p_settings->has_setting(_provider_setting_key(provider, "is_saved"))) {
			return true;
		}
	}
	return p_settings->has_setting(AI_SETTING_ACTIVE_PROVIDER_TYPE);
}

bool _has_global_provider_config(EditorSettings *p_settings) {
	return p_settings->has_setting(AI_SETTING_PROVIDER_TYPE) ||
			p_settings->has_setting(AI_SETTING_API_KEY) ||
			p_settings->has_setting(AI_SETTING_MODEL_NAME) ||
			p_settings->has_setting(AI_SETTING_BASE_URL);
}

void _save_provider_configs(EditorSettings *p_settings, const Ref<AIAgentConfig> &p_config) {
	p_settings->set(AI_SETTING_ACTIVE_PROVIDER_TYPE, (int)p_config->get_provider_type());
	p_settings->set(AI_SETTING_APPROVAL_POLICY, (int)p_config->get_approval_policy());

	for (int i = 0; i <= (int)AIAgentConfig::PROVIDER_CUSTOM; i++) {
		const AIAgentConfig::ProviderType provider = (AIAgentConfig::ProviderType)i;
		p_settings->set(_provider_setting_key(provider, "api_key"), p_config->get_provider_api_key(provider));
		p_settings->set(_provider_setting_key(provider, "model_name"), p_config->get_provider_model_name(provider));
		p_settings->set(_provider_setting_key(provider, "base_url"), p_config->get_provider_base_url(provider));
		p_settings->set(_provider_setting_key(provider, "is_saved"), p_config->is_provider_saved(provider));
	}
	const PackedInt32Array modes = _mode_override_modes();
	for (int i = 0; i < modes.size(); i++) {
		const AIAgentModeId mode = (AIAgentModeId)modes[i];
		const String key = _mode_override_setting_key(mode);
		if (p_config->has_mode_model_override((int)mode)) {
			p_settings->set(key, p_config->get_mode_model_override((int)mode));
		} else if (p_settings->has_setting(key)) {
			p_settings->erase(key);
		}
	}

	EditorSettings::save();
}

bool _load_legacy_project_config(EditorSettings *p_settings, const Ref<AIAgentConfig> &p_config) {
	const int legacy_provider = (int)p_settings->get_project_metadata("ai_agent", "provider_type", -1);
	const String legacy_api_key = p_settings->get_project_metadata("ai_agent", "api_key", String());
	const String legacy_model_name = p_settings->get_project_metadata("ai_agent", "model_name", String());
	const String legacy_base_url = p_settings->get_project_metadata("ai_agent", "base_url", String());

	const bool has_legacy_values = legacy_provider != -1 || !legacy_api_key.is_empty() || !legacy_model_name.is_empty() || !legacy_base_url.is_empty();
	if (!has_legacy_values) {
		return false;
	}

	if (legacy_provider != -1) {
		p_config->set_provider_type((AIAgentConfig::ProviderType)legacy_provider);
	}
	p_config->set_api_key(legacy_api_key);
	p_config->set_model_name(legacy_model_name);
	p_config->set_base_url(legacy_base_url);
	p_config->set_provider_saved(p_config->get_provider_type(), true);
	p_config->apply_provider_defaults(p_config->get_model_name().is_empty(), false);
	_save_provider_configs(p_settings, p_config);
	return true;
}

} // namespace

void AISettingsPanel::_bind_methods() {
	ADD_SIGNAL(MethodInfo("config_changed",
			PropertyInfo(Variant::OBJECT, "config", PROPERTY_HINT_RESOURCE_TYPE, "AIAgentConfig", PROPERTY_USAGE_DEFAULT, "AIAgentConfig")));
	ADD_SIGNAL(MethodInfo("model_suggestions_changed"));
}

void AISettingsPanel::_create_provider_cards() {
	ERR_FAIL_NULL(provider_cards_container);

	for (Button *btn : provider_cards) {
		if (btn) {
			btn->queue_free();
		}
	}
	provider_cards.clear();

	for (int i = 0; i < 5; i++) {
		const AIProviderDescriptor descriptor = ai_agent_get_provider_descriptor((AIAgentConfig::ProviderType)i);

		Button *card = memnew(Button);
		card->set_toggle_mode(true);
		card->set_flat(false);
		card->set_text_alignment(HORIZONTAL_ALIGNMENT_LEFT);
		card->set_icon_alignment(HORIZONTAL_ALIGNMENT_LEFT);
		card->add_theme_constant_override("h_separation", (int)Math::round(8.0f * EDSCALE));
		card->set_text(descriptor.name);
		card->set_tooltip_text(descriptor.description);
		card->set_h_size_flags(SIZE_EXPAND_FILL);
		card->set_custom_minimum_size(Size2(0, 38 * EDSCALE));
		card->connect("pressed", callable_mp(this, &AISettingsPanel::_on_card_selected).bind(i));
		provider_cards_container->add_child(card);
		provider_cards.push_back(card);
	}
}

void AISettingsPanel::_on_card_selected(int p_index) {
	if (selected_provider_index == p_index) {
		return;
	}

	if (config.is_valid()) {
		_commit_fields_to_provider(false);
		_commit_mode_overrides_to_config();
		EditorSettings *settings = EditorSettings::get_singleton();
		if (settings) {
			_save_provider_configs(settings, config);
		}
		config->set_provider_type((AIAgentConfig::ProviderType)p_index);
		config->apply_provider_defaults(false, false);
	}

	selected_provider_index = p_index;
	_apply_selected_provider_state();
	_load_selected_provider_into_fields();
	_update_base_url_visibility();
	_refresh_provider_ui();
	_apply_theme();
	_ensure_model_suggestions((AIAgentConfig::ProviderType)selected_provider_index);
	emit_signal("config_changed", config);
}

void AISettingsPanel::_update_base_url_visibility() {
	if (base_url_container) {
		base_url_container->set_visible(selected_provider_index == AIAgentConfig::PROVIDER_CUSTOM);
	}
}

void AISettingsPanel::_load_selected_provider_into_fields() {
	if (config.is_null()) {
		return;
	}

	loading_provider_fields = true;
	const AIAgentConfig::ProviderType provider = (AIAgentConfig::ProviderType)selected_provider_index;
	if (api_key_input) {
		api_key_input->set_text(config->get_provider_api_key(provider));
	}
	if (model_input) {
		model_input->set_text(config->get_provider_model_name(provider));
	}
	if (base_url_input) {
		base_url_input->set_text(config->get_provider_base_url(provider));
	}
	loading_provider_fields = false;
}

void AISettingsPanel::_commit_fields_to_provider(bool p_mark_saved) {
	if (config.is_null() || loading_provider_fields) {
		return;
	}

	const AIAgentConfig::ProviderType provider = (AIAgentConfig::ProviderType)selected_provider_index;
	config->set_provider_type(provider);
	config->set_provider_api_key(provider, api_key_input ? api_key_input->get_text().strip_edges() : String());
	config->set_provider_model_name(provider, model_input ? model_input->get_text().strip_edges() : String());
	config->set_provider_base_url(provider, base_url_input ? base_url_input->get_text().strip_edges() : String());
	config->apply_provider_defaults(config->get_provider_model_name(provider).is_empty(), false);
	if (p_mark_saved) {
		config->set_provider_saved(provider, true);
	}
}

void AISettingsPanel::_load_mode_overrides_into_fields() {
	if (config.is_null()) {
		return;
	}

	loading_provider_fields = true;
	_populate_mode_override_dropdowns();
	loading_provider_fields = false;
}

void AISettingsPanel::_commit_mode_overrides_to_config() {
	if (config.is_null() || loading_provider_fields) {
		return;
	}

	for (int i = 0; i < mode_override_rows.size(); i++) {
		String model_name = "";
		if (mode_override_rows[i].input && mode_override_rows[i].input->get_item_count() > 0) {
			const int selected = mode_override_rows[i].input->get_selected();
			if (selected > 0) {
				model_name = mode_override_rows[i].input->get_item_metadata(selected);
			}
		}
		config->set_mode_model_override((int)mode_override_rows[i].mode, model_name);
	}
}

void AISettingsPanel::_apply_selected_provider_state() {
	if (config.is_valid()) {
		selected_provider_index = (int)config->get_provider_type();
	}

	for (int i = 0; i < provider_cards.size(); i++) {
		if (provider_cards[i]) {
			provider_cards[i]->set_pressed(i == selected_provider_index);
		}
	}
}

void AISettingsPanel::_populate_mode_override_dropdowns() {
	const AIAgentConfig::ProviderType provider = (AIAgentConfig::ProviderType)selected_provider_index;
	const PackedStringArray suggestions = _get_merged_model_suggestions(provider);
	for (int i = 0; i < mode_override_rows.size(); i++) {
		OptionButton *ob = mode_override_rows[i].input;
		if (!ob) continue;

		String current_selection;
		if (ob->get_item_count() > 0 && ob->get_selected() > 0) {
			current_selection = ob->get_item_metadata(ob->get_selected());
		} else if (config.is_valid()) {
			current_selection = config->get_mode_model_override((int)mode_override_rows[i].mode);
		}
		
		ob->clear();
		ob->add_item("Use provider default");
		ob->set_item_metadata(0, "");

		bool found = false;
		for (int j = 0; j < suggestions.size(); j++) {
			if (suggestions[j].is_empty()) continue;
			ob->add_item(suggestions[j]);
			ob->set_item_metadata(ob->get_item_count() - 1, suggestions[j]);
			if (suggestions[j] == current_selection) {
				ob->select(ob->get_item_count() - 1);
				found = true;
			}
		}

		if (!found && !current_selection.is_empty()) {
			ob->add_item(current_selection);
			ob->set_item_metadata(ob->get_item_count() - 1, current_selection);
			ob->select(ob->get_item_count() - 1);
		} else if (current_selection.is_empty()) {
			ob->select(0);
		}
	}
}

void AISettingsPanel::_create_mode_override_rows(VBoxContainer *p_parent) {
	ERR_FAIL_NULL(p_parent);

	Label *title = memnew(Label);
	title->set_text("Mode Overrides");
	p_parent->add_child(title);

	Label *hint = memnew(Label);
	hint->set_text("Optional per-mode models. Leave blank to use the provider model above.");
	hint->set_autowrap_mode(TextServer::AUTOWRAP_WORD_SMART);
	p_parent->add_child(hint);

	const PackedInt32Array modes = _mode_override_modes();
	for (int i = 0; i < modes.size(); i++) {
		const AIAgentModeId mode = (AIAgentModeId)modes[i];

		HBoxContainer *row = memnew(HBoxContainer);
		row->add_theme_constant_override("separation", 8 * EDSCALE);
		p_parent->add_child(row);

		ModeOverrideRow mode_row;
		mode_row.mode = mode;
		mode_row.label = memnew(Label);
		mode_row.label->set_text(ai_agent_mode_get_name(mode));
		mode_row.label->set_custom_minimum_size(Size2(104 * EDSCALE, 0));
		row->add_child(mode_row.label);

		mode_row.input = memnew(OptionButton);
		mode_row.input->set_h_size_flags(SIZE_EXPAND_FILL);
		mode_row.input->set_custom_minimum_size(Size2(0, 36 * EDSCALE));
		mode_row.input->set_text_overrun_behavior(TextServer::OVERRUN_TRIM_ELLIPSIS);
		row->add_child(mode_row.input);

		mode_override_rows.push_back(mode_row);
	}
}

void AISettingsPanel::_set_approval_policy(AIAgentConfig::ApprovalPolicy p_policy, bool p_persist) {
	if (config.is_null()) {
		return;
	}

	config->set_approval_policy(p_policy);
	if (approval_ask_button) {
		approval_ask_button->set_pressed(p_policy == AIAgentConfig::APPROVAL_ASK);
	}
	if (approval_always_allow_button) {
		approval_always_allow_button->set_pressed(p_policy == AIAgentConfig::APPROVAL_ALWAYS_ALLOW);
	}

	if (p_persist) {
		persist_config();
	}
}

String AISettingsPanel::_build_model_suggestion_cache_key(AIAgentConfig::ProviderType p_provider) const {
	const AIProviderDescriptor descriptor = ai_agent_get_provider_descriptor(p_provider);
	const bool is_selected_provider = selected_provider_index == (int)p_provider;
	const String api_key = is_selected_provider && api_key_input ? api_key_input->get_text().strip_edges() : (config.is_valid() ? config->get_provider_api_key(p_provider) : String());
	String base_url = is_selected_provider && base_url_input ? base_url_input->get_text().strip_edges() : (config.is_valid() ? config->get_provider_base_url(p_provider) : String());
	if (base_url.is_empty()) {
		base_url = descriptor.default_base_url;
	}
	const String local_format = p_provider == AIAgentConfig::PROVIDER_LOCAL ? "ollama" : "default";
	return vformat("%d|%s|%s|%s", (int)p_provider, api_key, base_url, local_format);
}

Ref<AIProvider> AISettingsPanel::_create_provider_for_suggestions(AIAgentConfig::ProviderType p_provider) const {
	Ref<AIProvider> provider;
	switch (p_provider) {
		case AIAgentConfig::PROVIDER_OPENAI: {
			Ref<OpenAIProvider> openai;
			openai.instantiate();
			provider = openai;
		} break;
		case AIAgentConfig::PROVIDER_ANTHROPIC: {
			Ref<AnthropicProvider> anthropic;
			anthropic.instantiate();
			provider = anthropic;
		} break;
		case AIAgentConfig::PROVIDER_MINIMAX: {
			Ref<MiniMaxProvider> minimax;
			minimax.instantiate();
			provider = minimax;
		} break;
		case AIAgentConfig::PROVIDER_LOCAL: {
			Ref<LocalLLMProvider> local;
			local.instantiate();
			local->set_use_ollama_format(true);
			provider = local;
		} break;
		case AIAgentConfig::PROVIDER_CUSTOM: {
			Ref<OpenAIProvider> custom;
			custom.instantiate();
			provider = custom;
		} break;
	}

	if (provider.is_null()) {
		return provider;
	}

	const AIProviderDescriptor descriptor = ai_agent_get_provider_descriptor(p_provider);
	const bool is_selected_provider = selected_provider_index == (int)p_provider;
	const String api_key = is_selected_provider && api_key_input ? api_key_input->get_text().strip_edges() : (config.is_valid() ? config->get_provider_api_key(p_provider) : String());
	String base_url = is_selected_provider && base_url_input ? base_url_input->get_text().strip_edges() : (config.is_valid() ? config->get_provider_base_url(p_provider) : String());
	String model_name = is_selected_provider && model_input ? model_input->get_text().strip_edges() : (config.is_valid() ? config->get_provider_model_name(p_provider) : String());

	if (base_url.is_empty()) {
		base_url = descriptor.default_base_url;
	}
	if (model_name.is_empty()) {
		model_name = descriptor.default_model;
	}

	provider->set_api_key(api_key);
	provider->set_base_url(base_url);
	provider->set_model_name(model_name);
	return provider;
}

void AISettingsPanel::_invalidate_model_suggestions(AIAgentConfig::ProviderType p_provider, bool p_clear_results) {
	if (p_provider < 0 || p_provider >= model_suggestion_states.size()) {
		return;
	}

	ModelSuggestionState &state = model_suggestion_states.write[(int)p_provider];
	state.request_id++;
	state.loading = false;
	state.fetched_msec = 0;
	state.cache_key = "";
	state.active_provider.unref();
	if (p_clear_results) {
		state.discovered_models.clear();
		state.error_message = "";
	}
}

PackedStringArray AISettingsPanel::_get_merged_model_suggestions(AIAgentConfig::ProviderType p_provider) const {
	PackedStringArray models;
	if (p_provider >= 0 && p_provider < model_suggestion_states.size()) {
		models = model_suggestion_states[(int)p_provider].discovered_models;
	}

	const PackedStringArray curated = ai_agent_get_provider_descriptor(p_provider).recommended_models;
	for (int i = 0; i < curated.size(); i++) {
		if (!models.has(curated[i])) {
			models.push_back(curated[i]);
		}
	}

	return models;
}

void AISettingsPanel::_refresh_model_suggestion_chips() {
	if (!model_suggestions_flow || !model_suggestions_status_label) {
		return;
	}

	for (int i = 0; i < model_suggestion_buttons.size(); i++) {
		if (model_suggestion_buttons[i]) {
			model_suggestion_buttons[i]->queue_free();
		}
	}
	model_suggestion_buttons.clear();

	const AIAgentConfig::ProviderType provider = (AIAgentConfig::ProviderType)selected_provider_index;
	const ModelSuggestionState &state = model_suggestion_states[selected_provider_index];
	const PackedStringArray suggestions = _get_merged_model_suggestions(provider);
	const String selected_model = model_input ? model_input->get_text().strip_edges() : String();

	for (int i = 0; i < suggestions.size(); i++) {
		Button *suggestion = memnew(Button);
		suggestion->set_text(suggestions[i]);
		suggestion->set_tooltip_text("Use this model");
		suggestion->set_toggle_mode(false);
		suggestion->set_focus_mode(FOCUS_NONE);
		suggestion->set_disabled(suggestions[i] == selected_model);
		suggestion->connect("pressed", callable_mp(this, &AISettingsPanel::_on_model_suggestion_pressed).bind(suggestions[i]));
		model_suggestions_flow->add_child(suggestion);
		model_suggestion_buttons.push_back(suggestion);
	}

	if (state.loading) {
		model_suggestions_status_label->set_text("Loading live model suggestions...");
	} else if (!state.error_message.is_empty()) {
		model_suggestions_status_label->set_text(state.error_message + " Showing curated suggestions.");
	} else if (!state.discovered_models.is_empty()) {
		model_suggestions_status_label->set_text("Showing live suggestions from the provider.");
	} else {
		model_suggestions_status_label->set_text("Showing curated suggestions.");
	}

	_populate_mode_override_dropdowns();
	_apply_theme();
}

void AISettingsPanel::_ensure_model_suggestions(AIAgentConfig::ProviderType p_provider, bool p_force_refresh) {
	if (p_provider < 0 || p_provider >= model_suggestion_states.size()) {
		return;
	}

	ModelSuggestionState &state = model_suggestion_states.write[(int)p_provider];
	const String cache_key = _build_model_suggestion_cache_key(p_provider);
	const uint64_t now = OS::get_singleton()->get_ticks_msec();
	if (!p_force_refresh && state.loading && state.cache_key == cache_key) {
		return;
	}
	if (!p_force_refresh && state.fetched_msec != 0 && state.cache_key == cache_key && now - state.fetched_msec < MODEL_SUGGESTION_CACHE_TTL_MSEC) {
		if ((int)p_provider == selected_provider_index) {
			_refresh_model_suggestion_chips();
		}
		return;
	}

	const AIProviderDescriptor descriptor = ai_agent_get_provider_descriptor(p_provider);
	const bool is_selected_provider = selected_provider_index == (int)p_provider;
	const String api_key = is_selected_provider && api_key_input ? api_key_input->get_text().strip_edges() : (config.is_valid() ? config->get_provider_api_key(p_provider) : String());
	String base_url = is_selected_provider && base_url_input ? base_url_input->get_text().strip_edges() : (config.is_valid() ? config->get_provider_base_url(p_provider) : String());
	if (base_url.is_empty()) {
		base_url = descriptor.default_base_url;
	}

	state.request_id++;
	state.cache_key = cache_key;
	state.loading = false;
	state.error_message = "";
	state.active_provider.unref();

	if (descriptor.requires_api_key && api_key.is_empty()) {
		state.discovered_models.clear();
		state.error_message = "Add an API key to load live models.";
		if ((int)p_provider == selected_provider_index) {
			_refresh_model_suggestion_chips();
		}
		emit_signal("model_suggestions_changed");
		return;
	}

	if (base_url.is_empty()) {
		state.discovered_models.clear();
		state.error_message = "Enter a base URL to load live models.";
		if ((int)p_provider == selected_provider_index) {
			_refresh_model_suggestion_chips();
		}
		emit_signal("model_suggestions_changed");
		return;
	}

	Ref<AIProvider> provider = _create_provider_for_suggestions(p_provider);
	if (provider.is_null() || !provider->supports_model_discovery()) {
		state.discovered_models.clear();
		state.error_message = "";
		if ((int)p_provider == selected_provider_index) {
			_refresh_model_suggestion_chips();
		}
		emit_signal("model_suggestions_changed");
		return;
	}

	state.loading = true;
	state.active_provider = provider;
	const int request_id = state.request_id;
	const Error request_error = provider->request_available_models(callable_mp(this, &AISettingsPanel::_on_model_suggestions_discovered).bind((int)p_provider, request_id, cache_key));
	if (request_error != OK) {
		state.loading = false;
		state.active_provider.unref();
		state.discovered_models.clear();
		state.error_message = "Unable to start live model discovery.";
	}

	if ((int)p_provider == selected_provider_index) {
		_refresh_model_suggestion_chips();
	}
	emit_signal("model_suggestions_changed");
}

void AISettingsPanel::_on_provider_field_changed(const String &p_text) {
	(void)p_text;
	if (loading_provider_fields) {
		return;
	}

	_invalidate_model_suggestions((AIAgentConfig::ProviderType)selected_provider_index, true);
	if (model_suggestion_refresh_timer) {
		model_suggestion_refresh_timer->start(MODEL_SUGGESTION_REFRESH_DEBOUNCE_SEC);
	}
	_refresh_model_suggestion_chips();
	emit_signal("model_suggestions_changed");
}

void AISettingsPanel::_on_refresh_model_suggestions_pressed() {
	_ensure_model_suggestions((AIAgentConfig::ProviderType)selected_provider_index, true);
}

void AISettingsPanel::_on_model_suggestion_refresh_timeout() {
	_ensure_model_suggestions((AIAgentConfig::ProviderType)selected_provider_index, true);
}

void AISettingsPanel::_on_model_suggestion_pressed(const String &p_model) {
	if (!model_input) {
		return;
	}
	model_input->set_text(p_model);
	_refresh_model_suggestion_chips();
	emit_signal("model_suggestions_changed");
}

void AISettingsPanel::_on_model_suggestions_discovered(const PackedStringArray &p_models, const String &p_error, int p_provider_index, int p_request_id, const String &p_cache_key) {
	if (p_provider_index < 0 || p_provider_index >= model_suggestion_states.size()) {
		return;
	}

	ModelSuggestionState &state = model_suggestion_states.write[p_provider_index];
	if (state.request_id != p_request_id || state.cache_key != p_cache_key) {
		return;
	}

	state.loading = false;
	state.error_message = p_error;
	state.discovered_models = p_models;
	state.fetched_msec = p_models.is_empty() ? 0 : OS::get_singleton()->get_ticks_msec();
	callable_mp(this, &AISettingsPanel::_release_model_suggestion_provider).call_deferred(p_provider_index, p_request_id);

	if (p_provider_index == selected_provider_index) {
		_refresh_model_suggestion_chips();
	}
	emit_signal("model_suggestions_changed");
}

void AISettingsPanel::_release_model_suggestion_provider(int p_provider_index, int p_request_id) {
	if (p_provider_index < 0 || p_provider_index >= model_suggestion_states.size()) {
		return;
	}

	ModelSuggestionState &state = model_suggestion_states.write[p_provider_index];
	if (state.request_id != p_request_id) {
		return;
	}

	state.active_provider.unref();
}

AISettingsPanel::AISettingsPanel() {
	set_name("AISettings");
	set_h_size_flags(SIZE_EXPAND_FILL);
	set_v_size_flags(SIZE_EXPAND_FILL);
	add_theme_constant_override("separation", 10 * EDSCALE);
	model_suggestion_states.resize(5);

	eyebrow_label = memnew(Label);
	eyebrow_label->set_text("SETTINGS");
	add_child(eyebrow_label);

	title_label = memnew(Label);
	title_label->set_text("Providers");
	title_label->set_theme_type_variation("HeaderSmall");
	add_child(title_label);

	subtitle_label = memnew(Label);
	subtitle_label->set_text("Choose a provider, add credentials, and route each mode through the model that fits best.");
	subtitle_label->set_autowrap_mode(TextServer::AUTOWRAP_WORD_SMART);
	add_child(subtitle_label);

	setup_card = memnew(PanelContainer);
	add_child(setup_card);

	MarginContainer *setup_margin = memnew(MarginContainer);
	setup_margin->add_theme_constant_override("margin_left", 14 * EDSCALE);
	setup_margin->add_theme_constant_override("margin_top", 14 * EDSCALE);
	setup_margin->add_theme_constant_override("margin_right", 14 * EDSCALE);
	setup_margin->add_theme_constant_override("margin_bottom", 14 * EDSCALE);
	setup_card->add_child(setup_margin);

	VBoxContainer *setup_content = memnew(VBoxContainer);
	setup_content->add_theme_constant_override("separation", 10 * EDSCALE);
	setup_margin->add_child(setup_content);

	Label *provider_label = memnew(Label);
	provider_label->set_text("Provider");
	setup_content->add_child(provider_label);

	provider_cards_container = memnew(VBoxContainer);
	provider_cards_container->add_theme_constant_override("separation", 6 * EDSCALE);
	setup_content->add_child(provider_cards_container);
	_create_provider_cards();

	provider_summary_label = memnew(Label);
	provider_summary_label->set_autowrap_mode(TextServer::AUTOWRAP_WORD_SMART);
	setup_content->add_child(provider_summary_label);

	api_key_row = memnew(HBoxContainer);
	api_key_row->add_theme_constant_override("separation", 10 * EDSCALE);
	setup_content->add_child(api_key_row);

	Label *api_key_label = memnew(Label);
	api_key_label->set_text("API Key");
	api_key_label->set_custom_minimum_size(Size2(104 * EDSCALE, 0));
	api_key_row->add_child(api_key_label);

	api_key_input = memnew(LineEdit);
	api_key_input->set_secret(true);
	api_key_input->set_h_size_flags(SIZE_EXPAND_FILL);
	api_key_input->set_custom_minimum_size(Size2(0, 36 * EDSCALE));
	api_key_row->add_child(api_key_input);

	api_key_hint_label = memnew(Label);
	api_key_hint_label->set_autowrap_mode(TextServer::AUTOWRAP_WORD_SMART);
	setup_content->add_child(api_key_hint_label);

	{
		HBoxContainer *row = memnew(HBoxContainer);
		row->add_theme_constant_override("separation", 10 * EDSCALE);
		setup_content->add_child(row);

		Label *lbl = memnew(Label);
		lbl->set_text("Model");
		lbl->set_custom_minimum_size(Size2(104 * EDSCALE, 0));
		row->add_child(lbl);

		model_input = memnew(LineEdit);
		model_input->set_h_size_flags(SIZE_EXPAND_FILL);
		model_input->set_custom_minimum_size(Size2(0, 36 * EDSCALE));
		row->add_child(model_input);

		refresh_model_suggestions_button = memnew(Button);
		refresh_model_suggestions_button->set_text("Refresh");
		refresh_model_suggestions_button->set_custom_minimum_size(Size2(0, 30 * EDSCALE));
		refresh_model_suggestions_button->connect("pressed", callable_mp(this, &AISettingsPanel::_on_refresh_model_suggestions_pressed));
		row->add_child(refresh_model_suggestions_button);
	}

	model_hint_label = memnew(Label);
	model_hint_label->set_autowrap_mode(TextServer::AUTOWRAP_WORD_SMART);
	setup_content->add_child(model_hint_label);

	model_suggestions_status_label = memnew(Label);
	model_suggestions_status_label->set_autowrap_mode(TextServer::AUTOWRAP_WORD_SMART);
	setup_content->add_child(model_suggestions_status_label);

	model_suggestions_flow = memnew(HFlowContainer);
	model_suggestions_flow->set_h_size_flags(SIZE_EXPAND_FILL);
	model_suggestions_flow->add_theme_constant_override("h_separation", 6 * EDSCALE);
	model_suggestions_flow->add_theme_constant_override("v_separation", 6 * EDSCALE);
	setup_content->add_child(model_suggestions_flow);

	base_url_container = memnew(VBoxContainer);
	base_url_container->add_theme_constant_override("separation", 6 * EDSCALE);
	setup_content->add_child(base_url_container);
	{
		HBoxContainer *row = memnew(HBoxContainer);
		row->add_theme_constant_override("separation", 10 * EDSCALE);
		base_url_container->add_child(row);

		Label *lbl = memnew(Label);
		lbl->set_text("Base URL");
		lbl->set_custom_minimum_size(Size2(104 * EDSCALE, 0));
		row->add_child(lbl);

		base_url_input = memnew(LineEdit);
		base_url_input->set_h_size_flags(SIZE_EXPAND_FILL);
		base_url_input->set_custom_minimum_size(Size2(0, 36 * EDSCALE));
		row->add_child(base_url_input);
	}

	_create_mode_override_rows(setup_content);

	{
		HBoxContainer *row = memnew(HBoxContainer);
		row->add_theme_constant_override("separation", 10 * EDSCALE);
		setup_content->add_child(row);

		Label *lbl = memnew(Label);
		lbl->set_text("Tool Approvals");
		lbl->set_custom_minimum_size(Size2(104 * EDSCALE, 0));
		row->add_child(lbl);

		HBoxContainer *approval_row = memnew(HBoxContainer);
		approval_row->set_h_size_flags(SIZE_EXPAND_FILL);
		approval_row->add_theme_constant_override("separation", 4 * EDSCALE);
		row->add_child(approval_row);

		approval_ask_button = memnew(Button);
		approval_ask_button->set_text("Ask");
		approval_ask_button->set_toggle_mode(true);
		approval_ask_button->connect("pressed", callable_mp(this, &AISettingsPanel::_set_approval_policy).bind(AIAgentConfig::APPROVAL_ASK, true));
		approval_row->add_child(approval_ask_button);

		approval_always_allow_button = memnew(Button);
		approval_always_allow_button->set_text("Always Allow");
		approval_always_allow_button->set_toggle_mode(true);
		approval_always_allow_button->connect("pressed", callable_mp(this, &AISettingsPanel::_set_approval_policy).bind(AIAgentConfig::APPROVAL_ALWAYS_ALLOW, true));
		approval_row->add_child(approval_always_allow_button);
	}

	HBoxContainer *action_row = memnew(HBoxContainer);
	action_row->add_theme_constant_override("separation", 8 * EDSCALE);
	setup_content->add_child(action_row);

	save_button = memnew(Button);
	save_button->set_text("Connect");
	save_button->set_custom_minimum_size(Size2(0, 36 * EDSCALE));
	save_button->connect("pressed", callable_mp(this, &AISettingsPanel::_save_config));
	action_row->add_child(save_button);

	action_row->add_spacer();

	quick_note_label = memnew(Label);
	quick_note_label->set_text("Saved globally for this editor.");
	quick_note_label->set_autowrap_mode(TextServer::AUTOWRAP_WORD_SMART);
	quick_note_label->set_h_size_flags(SIZE_EXPAND_FILL);
	action_row->add_child(quick_note_label);

	config.instantiate();
	config->apply_provider_defaults(true, true);
	selected_provider_index = (int)config->get_provider_type();
	_update_base_url_visibility();

	model_suggestion_refresh_timer = memnew(Timer);
	model_suggestion_refresh_timer->set_one_shot(true);
	model_suggestion_refresh_timer->set_wait_time(MODEL_SUGGESTION_REFRESH_DEBOUNCE_SEC);
	model_suggestion_refresh_timer->connect("timeout", callable_mp(this, &AISettingsPanel::_on_model_suggestion_refresh_timeout));
	add_child(model_suggestion_refresh_timer);

	api_key_input->connect("text_changed", callable_mp(this, &AISettingsPanel::_on_provider_field_changed));
	base_url_input->connect("text_changed", callable_mp(this, &AISettingsPanel::_on_provider_field_changed));
}

void AISettingsPanel::_notification(int p_what) {
	if (p_what == NOTIFICATION_POSTINITIALIZE) {
		_refresh_theme_dependent_state();
	} else if (p_what == NOTIFICATION_ENTER_TREE) {
		_load_config();
		emit_signal("config_changed", config);
	} else if (p_what == NOTIFICATION_THEME_CHANGED) {
		_refresh_theme_dependent_state();
	}
}

void AISettingsPanel::_refresh_theme_dependent_state() {
	_apply_theme();
}

void AISettingsPanel::_apply_theme() {
	const Color accent = get_theme_color("accent_color", "Editor");
	const Color muted = get_theme_color("font_placeholder_color", "Editor");
	const Color strong = get_theme_color("font_color", "Editor");
	const Color background = get_theme_color("dark_color_1", "Editor");
	const Color surface = get_theme_color("dark_color_2", "Editor");
	const Color shell_fill = background.lerp(surface, 0.4f);
	const Color shell_border = strong.lerp(surface, 0.92f);
	const Color field_fill = background.lerp(surface, 0.2f);
	const Color field_border = strong.lerp(surface, 0.93f);
	const Color field_focus_border = accent.lerp(surface, 0.38f);
	const Color card_fill = background.lerp(surface, 0.24f);
	const Color card_fill_hover = background.lerp(surface, 0.31f);
	const Color card_fill_active = background.lerp(surface, 0.36f);
	const Color card_border_active = accent.lerp(surface, 0.46f);
	const Color chip_fill = background.lerp(surface, 0.28f);
	const Color chip_fill_active = background.lerp(surface, 0.36f);
	const Color chip_border = strong.lerp(surface, 0.91f);
	const Color primary_fill = background.lerp(accent, 0.14f);
	const Color primary_fill_hover = background.lerp(accent, 0.2f);
	const Color primary_fill_pressed = background.lerp(accent, 0.24f);
	const int field_radius = (int)Math::round(8.0f * EDSCALE);
	const int card_radius = (int)Math::round(12.0f * EDSCALE);
	const int chip_radius = (int)Math::round(8.0f * EDSCALE);

	auto make_style = [&](const Color &p_fill, const Color &p_border, int p_radius, int p_padding_h = 0, int p_padding_v = 0) {
		Ref<StyleBoxFlat> style;
		style.instantiate();
		style->set_bg_color(p_fill);
		style->set_border_color(p_border);
		style->set_border_width_all(1);
		style->set_corner_radius_all(p_radius);
		style->set_content_margin(SIDE_LEFT, p_padding_h);
		style->set_content_margin(SIDE_TOP, p_padding_v);
		style->set_content_margin(SIDE_RIGHT, p_padding_h);
		style->set_content_margin(SIDE_BOTTOM, p_padding_v);
		return style;
	};

	auto apply_field_theme = [&](LineEdit *p_input) {
		if (!p_input) {
			return;
		}
		p_input->set_custom_minimum_size(Size2(0, 36 * EDSCALE));
		p_input->add_theme_style_override("normal", make_style(field_fill, strong.lerp(surface, 0.95f), field_radius, 12 * EDSCALE, 8 * EDSCALE));
		p_input->add_theme_style_override("focus", make_style(field_fill, field_focus_border, field_radius, 12 * EDSCALE, 8 * EDSCALE));
		p_input->add_theme_color_override("font_color", strong);
		p_input->add_theme_color_override("font_placeholder_color", muted);
	};

	if (eyebrow_label) {
		eyebrow_label->add_theme_color_override("font_color", accent);
	}
	if (title_label) {
		title_label->add_theme_color_override("font_color", strong);
	}
	if (subtitle_label) {
		subtitle_label->add_theme_color_override("font_color", muted.lerp(strong, 0.22f));
	}
	if (setup_card) {
		setup_card->add_theme_style_override("panel", make_style(shell_fill, shell_border, card_radius));
	}
	if (provider_summary_label) {
		provider_summary_label->add_theme_color_override("font_color", muted.lerp(strong, 0.18f));
	}
	if (api_key_hint_label) {
		api_key_hint_label->add_theme_color_override("font_color", muted);
	}
	if (model_hint_label) {
		model_hint_label->add_theme_color_override("font_color", muted);
	}
	if (model_suggestions_status_label) {
		model_suggestions_status_label->add_theme_color_override("font_color", muted.lerp(strong, 0.16f));
	}
	if (quick_note_label) {
		quick_note_label->add_theme_color_override("font_color", muted);
	}
	apply_field_theme(api_key_input);
	apply_field_theme(model_input);
	apply_field_theme(base_url_input);
	for (int i = 0; i < mode_override_rows.size(); i++) {
		if (mode_override_rows[i].label) {
			mode_override_rows[i].label->add_theme_color_override("font_color", strong);
		}
	}

	for (int i = 0; i < provider_cards.size(); i++) {
		Button *card = provider_cards[i];
		if (!card) {
			continue;
		}
		const AIProviderDescriptor descriptor = ai_agent_get_provider_descriptor((AIAgentConfig::ProviderType)i);
		if (!descriptor.icon_name.is_empty()) {
			card->set_button_icon(get_theme_icon(descriptor.icon_name, EditorStringName(EditorIcons)));
		}
		card->set_custom_minimum_size(Size2(0, 38 * EDSCALE));
		card->add_theme_constant_override("icon_max_width", (int)Math::round(14.0f * EDSCALE));
		card->add_theme_color_override("font_hover_color", strong);
		card->add_theme_color_override("font_pressed_color", strong);
		card->add_theme_color_override("font_color", strong);
		card->add_theme_color_override("icon_normal_color", i == selected_provider_index ? accent : muted.lerp(strong, 0.62f));
		card->add_theme_color_override("icon_hover_color", strong);
		card->add_theme_color_override("icon_pressed_color", strong);
		card->add_theme_style_override("normal", make_style(i == selected_provider_index ? card_fill_active : card_fill, i == selected_provider_index ? card_border_active : chip_border, field_radius, 10 * EDSCALE, 8 * EDSCALE));
		card->add_theme_style_override("hover", make_style(i == selected_provider_index ? card_fill_active : card_fill_hover, card_border_active, field_radius, 10 * EDSCALE, 8 * EDSCALE));
		card->add_theme_style_override("pressed", make_style(card_fill_active, card_border_active, field_radius, 10 * EDSCALE, 8 * EDSCALE));
		card->add_theme_style_override("hover_pressed", make_style(card_fill_active, card_border_active, field_radius, 10 * EDSCALE, 8 * EDSCALE));
	}
	if (save_button) {
		save_button->set_custom_minimum_size(Size2(0, 36 * EDSCALE));
	}
	auto apply_toggle_button_theme = [&](Button *p_button, bool p_active) {
		if (!p_button) {
			return;
		}
		p_button->set_custom_minimum_size(Size2(0, 30 * EDSCALE));
		p_button->add_theme_style_override("normal", make_style(p_active ? chip_fill_active : chip_fill, p_active ? card_border_active : chip_border, chip_radius, 10 * EDSCALE, 6 * EDSCALE));
		p_button->add_theme_style_override("hover", make_style(p_active ? chip_fill_active : card_fill_hover, card_border_active, chip_radius, 10 * EDSCALE, 6 * EDSCALE));
		p_button->add_theme_style_override("pressed", make_style(chip_fill_active, card_border_active, chip_radius, 10 * EDSCALE, 6 * EDSCALE));
		p_button->add_theme_style_override("hover_pressed", make_style(chip_fill_active, card_border_active, chip_radius, 10 * EDSCALE, 6 * EDSCALE));
		p_button->add_theme_color_override("font_color", strong);
		p_button->add_theme_color_override("font_hover_color", strong);
		p_button->add_theme_color_override("font_pressed_color", strong);
		p_button->add_theme_color_override("font_hover_pressed_color", strong);
	};
	apply_toggle_button_theme(approval_ask_button, config.is_valid() && config->get_approval_policy() == AIAgentConfig::APPROVAL_ASK);
	apply_toggle_button_theme(approval_always_allow_button, config.is_valid() && config->get_approval_policy() == AIAgentConfig::APPROVAL_ALWAYS_ALLOW);
	apply_toggle_button_theme(refresh_model_suggestions_button, false);
	for (int i = 0; i < model_suggestion_buttons.size(); i++) {
		if (model_suggestion_buttons[i]) {
			apply_toggle_button_theme(model_suggestion_buttons[i], false);
		}
	}
}

void AISettingsPanel::_refresh_provider_ui() {
	if (config.is_null()) {
		return;
	}

	const AIAgentConfig::ProviderType provider = (AIAgentConfig::ProviderType)selected_provider_index;
	config->set_provider_type(provider);
	const String default_model = config->get_default_model_name();
	const String effective_url = config->get_effective_base_url();
	String provider_guidance;
	String model_guidance;

	switch (provider) {
		case AIAgentConfig::PROVIDER_OPENAI:
			provider_guidance = "Good fit for fast, Copilot-style coding help in this panel, but it still uses your own OpenAI API key rather than GitHub Copilot auth.";
			model_guidance = "Prefer gpt-5-mini for fast editor help and gpt-5 when you want stronger reasoning with the same provider.";
			break;
		case AIAgentConfig::PROVIDER_ANTHROPIC:
			provider_guidance = "Best when you want slower, more deliberate planning, debugging, and explanation quality.";
			model_guidance = "Keep Sonnet as the default for balanced coding and planning. Use lighter models only when latency matters more than depth.";
			break;
		case AIAgentConfig::PROVIDER_MINIMAX:
			provider_guidance = "Default here. MiniMax M2.7 is the current official flagship, while M2.1 still shows up in OpenCode guidance as a solid coding-agent option.";
			model_guidance = "Prefer MiniMax-M2.7 by default, try MiniMax-M2.7-highspeed for lower latency, and keep MiniMax-M2.1 available for coding-agent-oriented experimentation.";
			break;
		case AIAgentConfig::PROVIDER_LOCAL:
			provider_guidance = "Useful for private or offline-friendly workflows when you already have a local or gateway-hosted model available.";
			model_guidance = "Enter the exact local model name your server exposes. Smaller coding models will feel faster but may need more guidance.";
			break;
		case AIAgentConfig::PROVIDER_CUSTOM:
			provider_guidance = "Use this for OpenAI-compatible gateways such as OpenCode Zen or similar proxy services. GitHub Copilot device-login providers are out of scope for this panel.";
			model_guidance = "Enter the exact model ID exposed by your gateway. This is the best path when you want OpenCode-style hosted routing without adding a new native provider here.";
			break;
	}

	if (provider_summary_label) {
		String summary = config->get_provider_description();
		if (!provider_guidance.is_empty()) {
			summary += " " + provider_guidance;
		}
		if (config->is_provider_saved(provider)) {
			summary += " Saved and available in chat model selection.";
		} else {
			summary += " Press Connect to save this provider and expose it in the chat model menu.";
		}
		provider_summary_label->set_text(summary);
	}
	if (api_key_input) {
		api_key_input->set_placeholder(config->get_api_key_placeholder());
	}
	if (api_key_hint_label) {
		String hint = "Saved globally in editor settings.";
		if (!config->provider_requires_api_key()) {
			hint += " Leave blank unless your local gateway requires auth.";
		}
		api_key_hint_label->set_text(hint);
	}
	if (model_input) {
		model_input->set_placeholder(default_model);
	}
	if (model_hint_label) {
		model_hint_label->set_text(model_guidance.is_empty() ? "Changes follow the provider default automatically, but you can type any compatible model." : model_guidance);
	}
	_refresh_model_suggestion_chips();
	if (approval_ask_button) {
		approval_ask_button->set_pressed(config->get_approval_policy() == AIAgentConfig::APPROVAL_ASK);
	}
	if (approval_always_allow_button) {
		approval_always_allow_button->set_pressed(config->get_approval_policy() == AIAgentConfig::APPROVAL_ALWAYS_ALLOW);
	}
	if (base_url_input) {
		base_url_input->set_placeholder(effective_url.is_empty() ? "Required for custom providers" : effective_url);
	}
}

void AISettingsPanel::_save_config() {
	if (config.is_null()) {
		config.instantiate();
	}

	_commit_fields_to_provider(true);
	_commit_mode_overrides_to_config();

	persist_config();
}

void AISettingsPanel::persist_config() {
	if (config.is_null()) {
		return;
	}

	EditorSettings *settings = EditorSettings::get_singleton();
	if (settings) {
		_save_provider_configs(settings, config);
	}

	_apply_selected_provider_state();
	_load_selected_provider_into_fields();
	_load_mode_overrides_into_fields();
	_update_base_url_visibility();
	_refresh_provider_ui();
	_apply_theme();
	_invalidate_model_suggestions((AIAgentConfig::ProviderType)selected_provider_index, true);
	_ensure_model_suggestions((AIAgentConfig::ProviderType)selected_provider_index, true);
	emit_signal("config_changed", config);
}

void AISettingsPanel::_load_config() {
	EditorSettings *settings = EditorSettings::get_singleton();
	if (!settings) {
		return;
	}

	if (config.is_null()) {
		config.instantiate();
	}

	if (_has_saved_provider_entries(settings)) {
		if (settings->has_setting(AI_SETTING_ACTIVE_PROVIDER_TYPE)) {
			config->set_provider_type((AIAgentConfig::ProviderType)(int)settings->get_setting(AI_SETTING_ACTIVE_PROVIDER_TYPE));
		}
		if (settings->has_setting(AI_SETTING_APPROVAL_POLICY)) {
			config->set_approval_policy((AIAgentConfig::ApprovalPolicy)(int)settings->get_setting(AI_SETTING_APPROVAL_POLICY));
		}

		for (int i = 0; i <= (int)AIAgentConfig::PROVIDER_CUSTOM; i++) {
			const AIAgentConfig::ProviderType provider = (AIAgentConfig::ProviderType)i;
			const String api_key_key = _provider_setting_key(provider, "api_key");
			const String model_key = _provider_setting_key(provider, "model_name");
			const String base_url_key = _provider_setting_key(provider, "base_url");
			const String saved_key = _provider_setting_key(provider, "is_saved");

			if (settings->has_setting(api_key_key)) {
				config->set_provider_api_key(provider, (String)settings->get_setting(api_key_key));
			}
			if (settings->has_setting(model_key)) {
				config->set_provider_model_name(provider, (String)settings->get_setting(model_key));
			}
			if (settings->has_setting(base_url_key)) {
				config->set_provider_base_url(provider, (String)settings->get_setting(base_url_key));
			}
			if (settings->has_setting(saved_key)) {
				config->set_provider_saved(provider, (bool)settings->get_setting(saved_key));
			}
			config->set_provider_type(provider);
			config->apply_provider_defaults(config->get_provider_model_name(provider).is_empty(), false);
		}
		const PackedInt32Array modes = _mode_override_modes();
		for (int i = 0; i < modes.size(); i++) {
			const AIAgentModeId mode = (AIAgentModeId)modes[i];
			const String key = _mode_override_setting_key(mode);
			if (settings->has_setting(key)) {
				config->set_mode_model_override((int)mode, (String)settings->get_setting(key));
			}
		}
		if (settings->has_setting(AI_SETTING_ACTIVE_PROVIDER_TYPE)) {
			config->set_provider_type((AIAgentConfig::ProviderType)(int)settings->get_setting(AI_SETTING_ACTIVE_PROVIDER_TYPE));
		}
	} else if (_has_global_provider_config(settings)) {
		if (settings->has_setting(AI_SETTING_PROVIDER_TYPE)) {
			config->set_provider_type((AIAgentConfig::ProviderType)(int)settings->get_setting(AI_SETTING_PROVIDER_TYPE));
		}
		if (settings->has_setting(AI_SETTING_APPROVAL_POLICY)) {
			config->set_approval_policy((AIAgentConfig::ApprovalPolicy)(int)settings->get_setting(AI_SETTING_APPROVAL_POLICY));
		}
		config->set_api_key(settings->has_setting(AI_SETTING_API_KEY) ? (String)settings->get_setting(AI_SETTING_API_KEY) : String());
		config->set_model_name(settings->has_setting(AI_SETTING_MODEL_NAME) ? (String)settings->get_setting(AI_SETTING_MODEL_NAME) : String());
		config->set_base_url(settings->has_setting(AI_SETTING_BASE_URL) ? (String)settings->get_setting(AI_SETTING_BASE_URL) : String());
		config->set_provider_saved(config->get_provider_type(), true);
		config->apply_provider_defaults(config->get_model_name().is_empty(), false);
		_save_provider_configs(settings, config);
	} else {
		if (settings->has_setting(AI_SETTING_APPROVAL_POLICY)) {
			config->set_approval_policy((AIAgentConfig::ApprovalPolicy)(int)settings->get_setting(AI_SETTING_APPROVAL_POLICY));
		}
		_load_legacy_project_config(settings, config);
	}

	selected_provider_index = (int)config->get_provider_type();
	_update_base_url_visibility();
	_apply_selected_provider_state();
	_load_selected_provider_into_fields();
	_load_mode_overrides_into_fields();
	_refresh_provider_ui();
	_apply_theme();
	_ensure_model_suggestions((AIAgentConfig::ProviderType)selected_provider_index);
}

Ref<AIAgentConfig> AISettingsPanel::get_config() const {
	return config;
}

PackedStringArray AISettingsPanel::get_suggested_models(AIAgentConfig::ProviderType p_provider) const {
	return _get_merged_model_suggestions(p_provider);
}

void AISettingsPanel::ensure_model_suggestions(AIAgentConfig::ProviderType p_provider, bool p_force_refresh) {
	_ensure_model_suggestions(p_provider, p_force_refresh);
}

#endif // TOOLS_ENABLED
