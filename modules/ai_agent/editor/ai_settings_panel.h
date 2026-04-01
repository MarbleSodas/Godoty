/**************************************************************************/
/*  ai_settings_panel.h                                                   */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#ifdef TOOLS_ENABLED

#include "core/templates/vector.h"
#include "modules/ai_agent/ai_agent_config.h"
#include "modules/ai_agent/ai_agent_mode.h"
#include "scene/gui/box_container.h"
#include "scene/gui/button.h"
#include "scene/gui/line_edit.h"
#include "scene/gui/option_button.h"

class Label;
class PanelContainer;
class HFlowContainer;
class Timer;
class AIProvider;

class AISettingsPanel : public VBoxContainer {
	GDCLASS(AISettingsPanel, VBoxContainer);

	struct ModeOverrideRow {
		AIAgentModeId mode = AI_AGENT_MODE_ASK;
		Label *label = nullptr;
		OptionButton *input = nullptr;
	};

	struct ModelSuggestionState {
		PackedStringArray discovered_models;
		String cache_key;
		String error_message;
		uint64_t fetched_msec = 0;
		int request_id = 0;
		bool loading = false;
		Ref<AIProvider> active_provider;
	};

	Label *eyebrow_label = nullptr;
	Label *title_label = nullptr;
	Label *subtitle_label = nullptr;
	Label *provider_summary_label = nullptr;
	Label *quick_note_label = nullptr;
	HBoxContainer *api_key_row = nullptr;
	LineEdit *api_key_input = nullptr;
	Label *api_key_hint_label = nullptr;
	LineEdit *model_input = nullptr;
	Label *model_hint_label = nullptr;
	Label *model_suggestions_status_label = nullptr;
	LineEdit *base_url_input = nullptr;
	Button *approval_ask_button = nullptr;
	Button *approval_always_allow_button = nullptr;
	Button *refresh_model_suggestions_button = nullptr;
	Button *save_button = nullptr;
	Vector<Button *> provider_cards;
	Vector<Button *> model_suggestion_buttons;
	Vector<ModeOverrideRow> mode_override_rows;
	Vector<ModelSuggestionState> model_suggestion_states;
	PanelContainer *setup_card = nullptr;
	VBoxContainer *provider_cards_container = nullptr;
	VBoxContainer *base_url_container = nullptr;
	HFlowContainer *model_suggestions_flow = nullptr;
	Timer *model_suggestion_refresh_timer = nullptr;
	int selected_provider_index = 0;
	bool loading_provider_fields = false;

	Ref<AIAgentConfig> config;

	void _apply_theme();
	void _refresh_theme_dependent_state();
	void _refresh_provider_ui();
	void _save_config();
	void _load_config();
	void _load_selected_provider_into_fields();
	void _commit_fields_to_provider(bool p_mark_saved);
	void _load_mode_overrides_into_fields();
	void _commit_mode_overrides_to_config();
	void _apply_selected_provider_state();
	void _populate_mode_override_dropdowns();
	void _create_provider_cards();
	void _create_mode_override_rows(VBoxContainer *p_parent);
	void _set_approval_policy(AIAgentConfig::ApprovalPolicy p_policy, bool p_persist = true);
	void _on_card_selected(int p_index);
	void _on_provider_field_changed(const String &p_text);
	void _on_refresh_model_suggestions_pressed();
	void _on_model_suggestion_refresh_timeout();
	void _on_model_suggestion_pressed(const String &p_model);
	void _on_model_suggestions_discovered(const PackedStringArray &p_models, const String &p_error, int p_provider_index, int p_request_id, const String &p_cache_key);
	void _release_model_suggestion_provider(int p_provider_index, int p_request_id);
	void _update_base_url_visibility();
	String _build_model_suggestion_cache_key(AIAgentConfig::ProviderType p_provider) const;
	Ref<AIProvider> _create_provider_for_suggestions(AIAgentConfig::ProviderType p_provider) const;
	void _invalidate_model_suggestions(AIAgentConfig::ProviderType p_provider, bool p_clear_results = false);
	void _refresh_model_suggestion_chips();
	void _ensure_model_suggestions(AIAgentConfig::ProviderType p_provider, bool p_force_refresh = false);
	PackedStringArray _get_merged_model_suggestions(AIAgentConfig::ProviderType p_provider) const;

protected:
	static void _bind_methods();
	void _notification(int p_what);

public:
	Ref<AIAgentConfig> get_config() const;
	void persist_config();
	PackedStringArray get_suggested_models(AIAgentConfig::ProviderType p_provider) const;
	void ensure_model_suggestions(AIAgentConfig::ProviderType p_provider, bool p_force_refresh = false);

	AISettingsPanel();
};

#endif // TOOLS_ENABLED
