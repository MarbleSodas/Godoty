/**************************************************************************/
/*  ai_settings_panel.cpp                                                 */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#ifdef TOOLS_ENABLED

#include "ai_settings_panel.h"

#include "editor/settings/editor_settings.h"
#include "editor/themes/editor_scale.h"

#include "scene/gui/button.h"
#include "scene/gui/label.h"
#include "scene/gui/line_edit.h"
#include "scene/gui/margin_container.h"
#include "scene/gui/menu_button.h"
#include "scene/gui/option_button.h"
#include "scene/gui/panel_container.h"
#include "scene/gui/popup_menu.h"

namespace {

static const char *AI_SETTING_PROVIDER_TYPE = "_ai_agent/provider_type";
static const char *AI_SETTING_API_KEY = "_ai_agent/api_key";
static const char *AI_SETTING_MODEL_NAME = "_ai_agent/model_name";
static const char *AI_SETTING_BASE_URL = "_ai_agent/base_url";

bool _has_global_provider_config(EditorSettings *p_settings) {
	return p_settings->has_setting(AI_SETTING_PROVIDER_TYPE) ||
			p_settings->has_setting(AI_SETTING_API_KEY) ||
			p_settings->has_setting(AI_SETTING_MODEL_NAME) ||
			p_settings->has_setting(AI_SETTING_BASE_URL);
}

void _save_global_provider_config(EditorSettings *p_settings, const Ref<AIAgentConfig> &p_config) {
	p_settings->set(AI_SETTING_PROVIDER_TYPE, (int)p_config->get_provider_type());
	p_settings->set(AI_SETTING_API_KEY, p_config->get_api_key());
	p_settings->set(AI_SETTING_MODEL_NAME, p_config->get_model_name());
	p_settings->set(AI_SETTING_BASE_URL, p_config->get_base_url());
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
	p_config->apply_provider_defaults(p_config->get_model_name().is_empty(), false);
	_save_global_provider_config(p_settings, p_config);
	return true;
}

} // namespace

void AISettingsPanel::_bind_methods() {
	ADD_SIGNAL(MethodInfo("config_changed",
			PropertyInfo(Variant::OBJECT, "config", PROPERTY_HINT_RESOURCE_TYPE, "AIAgentConfig", PROPERTY_USAGE_DEFAULT, "AIAgentConfig")));
}

void AISettingsPanel::_create_provider_cards() {
	// Find the cards container (should be the VBoxContainer we created in constructor)
	VBoxContainer *cards_container = nullptr;
	for (int i = 0; i < get_child_count(); i++) {
		Node *child = get_child(i);
		if (child->get_class() == "PanelContainer") {
			PanelContainer *pc = Object::cast_to<PanelContainer>(child);
			if (pc && pc->get_child_count() > 0) {
				MarginContainer *mc = Object::cast_to<MarginContainer>(pc->get_child(0));
				if (mc && mc->get_child_count() > 0) {
					VBoxContainer *vbc = Object::cast_to<VBoxContainer>(mc->get_child(0));
					if (vbc && vbc->get_child_count() > 2) { // Has multiple children after title/subtitle
						cards_container = vbc;
						break;
					}
				}
			}
		}
	}

	if (!cards_container) {
		return;
	}

	// Clear any existing cards
	for (Button *btn : provider_cards) {
		if (btn) {
			btn->queue_free();
		}
	}
	provider_cards.clear();

	// Create card for each provider
	for (int i = 0; i < 5; i++) {
		Button *card = memnew(Button);
		card->set_toggle_mode(true);
		card->set_button_group(nullptr); // Manual selection management
		card->connect("pressed", callable_mp(this, &AISettingsPanel::_on_card_selected).bind(i));
		card->set_meta("provider_index", i);

		// Card layout: HBox with icon, name, tagline
		HBoxContainer *card_layout = memnew(HBoxContainer);
		card_layout->add_theme_constant_override("separation", 12 * EDSCALE);
		card->add_child(card_layout);

		// Provider icon (colored rect)
		PanelContainer *icon_bg = memnew(PanelContainer);
		icon_bg->set_custom_minimum_size(Size2(24 * EDSCALE, 24 * EDSCALE));
		card_layout->add_child(icon_bg);

		Color provider_color;
		String provider_letter;
		switch (i) {
			case 0: provider_color = Color(0.063, 0.635, 0.498); provider_letter = "O"; break; // OpenAI green
			case 1: provider_color = Color(0.851, 0.467, 0.341); provider_letter = "A"; break; // Anthropic
			case 2: provider_color = Color(0.976, 0.725, 0.188); provider_letter = "M"; break; // MiniMax
			case 3: provider_color = Color(0.2, 0.2, 0.2); provider_letter = "L"; break; // Local
			case 4: provider_color = Color(0.4, 0.4, 0.4); provider_letter = "C"; break; // Custom
		}
		icon_bg->add_theme_color_override("panel_color", provider_color);

		Label *letter = memnew(Label);
		letter->set_text(provider_letter);
		letter->set_horizontal_alignment(HORIZONTAL_ALIGNMENT_CENTER);
		icon_bg->add_child(letter);

		// Name and tagline
		VBoxContainer *text_layout = memnew(VBoxContainer);
		card_layout->add_child(text_layout);

		Label *name = memnew(Label);
		name->set_text(ai_agent_get_provider_descriptor((AIAgentConfig::ProviderType)i).name);
		name->add_theme_font_size_override("font_size", int(14 * EDSCALE));
		text_layout->add_child(name);

		Label *tagline = memnew(Label);
		tagline->set_text(ai_agent_get_provider_descriptor((AIAgentConfig::ProviderType)i).description);
		tagline->add_theme_color_override("font_color", get_theme_color("font_placeholder_color", "Editor"));
		tagline->add_theme_font_size_override("font_size", int(11 * EDSCALE));
		text_layout->add_child(tagline);

		// Add to container and tracking vector
		cards_container->add_child(card);
		provider_cards.push_back(card);
	}
}

void AISettingsPanel::_on_card_selected(int p_index) {
	// Update visual selection state - set pressed for all cards
	for (int i = 0; i < provider_cards.size(); i++) {
		if (provider_cards[i]) {
			provider_cards[i]->set_pressed(i == p_index);
		}
	}

	selected_provider_index = p_index;

	// Update config
	if (config.is_valid()) {
		config->set_provider_type((AIAgentConfig::ProviderType)p_index);
		config->apply_provider_defaults(true, true); // Force model to default
	}

	// Update UI
	if (selected_model_label && config.is_valid()) {
		selected_model_label->set_text(config->get_model_name());
	}

	_refresh_provider_ui();
	_update_base_url_visibility();
}

void AISettingsPanel::_update_base_url_visibility() {
	if (base_url_container) {
		bool is_custom = (selected_provider_index == AIAgentConfig::PROVIDER_CUSTOM);
		base_url_container->set_visible(is_custom);
	}
}

AISettingsPanel::AISettingsPanel() {
	set_name("AISettings");
	set_visible(false);
	set_h_size_flags(SIZE_EXPAND_FILL);
	add_theme_constant_override("separation", 12 * EDSCALE);

	Label *title = memnew(Label);
	title->set_text("Connect a Provider");
	title->set_theme_type_variation("HeaderSmall");
	add_child(title);

	Label *subtitle = memnew(Label);
	subtitle->set_text("Set a provider once. Godoty handles prompts, token budgets, and mode behavior automatically.");
	subtitle->set_autowrap_mode(TextServer::AUTOWRAP_WORD_SMART);
	add_child(subtitle);

	PanelContainer *setup_card = memnew(PanelContainer);
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

	/*
	{
		HBoxContainer *row = memnew(HBoxContainer);
		row->add_theme_constant_override("separation", 10 * EDSCALE);
		setup_content->add_child(row);

		Label *lbl = memnew(Label);
		lbl->set_text("Provider");
		lbl->set_custom_minimum_size(Size2(110 * EDSCALE, 0));
		row->add_child(lbl);

		provider_select = memnew(OptionButton);
		provider_select->set_h_size_flags(SIZE_EXPAND_FILL);
		provider_select->add_item("OpenAI", AIAgentConfig::PROVIDER_OPENAI);
		provider_select->add_item("Anthropic", AIAgentConfig::PROVIDER_ANTHROPIC);
		provider_select->add_item("MiniMax", AIAgentConfig::PROVIDER_MINIMAX);
		provider_select->add_item("Local (Ollama)", AIAgentConfig::PROVIDER_LOCAL);
		provider_select->add_item("Custom", AIAgentConfig::PROVIDER_CUSTOM);
		provider_select->connect("item_selected", callable_mp(this, &AISettingsPanel::_on_provider_changed));
		row->add_child(provider_select);
	}
	*/

	// Create provider cards container
	VBoxContainer *cards_container = memnew(VBoxContainer);
	cards_container->add_theme_constant_override("separation", 8 * EDSCALE);
	setup_content->add_child(cards_container);

	// Create provider cards
	_create_provider_cards();

	provider_summary_label = memnew(Label);
	provider_summary_label->set_autowrap_mode(TextServer::AUTOWRAP_WORD_SMART);
	setup_content->add_child(provider_summary_label);

	api_key_row = memnew(HBoxContainer);
	api_key_row->add_theme_constant_override("separation", 10 * EDSCALE);
	setup_content->add_child(api_key_row);

	Label *api_key_label = memnew(Label);
	api_key_label->set_text("API Key");
	api_key_label->set_custom_minimum_size(Size2(110 * EDSCALE, 0));
	api_key_row->add_child(api_key_label);

	api_key_input = memnew(LineEdit);
	api_key_input->set_secret(true);
	api_key_input->set_h_size_flags(SIZE_EXPAND_FILL);
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
		lbl->set_custom_minimum_size(Size2(110 * EDSCALE, 0));
		row->add_child(lbl);

		selected_model_label = memnew(Label);
		selected_model_label->set_h_size_flags(SIZE_EXPAND_FILL);
		selected_model_label->set_text(config.is_valid() ? config->get_model_name() : "gpt-5-mini");
		row->add_child(selected_model_label);
	}

	base_url_container = memnew(HBoxContainer);
	base_url_container->add_theme_constant_override("separation", 10 * EDSCALE);
	base_url_container->set_visible(false); // Hidden by default
	setup_content->add_child(base_url_container);
	{
		HBoxContainer *row = memnew(HBoxContainer);
		row->add_theme_constant_override("separation", 10 * EDSCALE);
		base_url_container->add_child(row);

		Label *lbl = memnew(Label);
		lbl->set_text("Base URL");
		lbl->set_custom_minimum_size(Size2(110 * EDSCALE, 0));
		row->add_child(lbl);

		base_url_input = memnew(LineEdit);
		base_url_input->set_placeholder("https://api.example.com/v1");
		base_url_input->set_h_size_flags(SIZE_EXPAND_FILL);
		row->add_child(base_url_input);
	}

	// Set selected_provider_index before calling _update_base_url_visibility()
	config.instantiate();
	config->apply_provider_defaults(true, true);
	selected_provider_index = (int)config->get_provider_type();

	_update_base_url_visibility();

	HBoxContainer *action_row = memnew(HBoxContainer);
	action_row->add_theme_constant_override("separation", 8 * EDSCALE);
	setup_content->add_child(action_row);

	save_button = memnew(Button);
	save_button->set_text("Save Connection");
	save_button->connect("pressed", callable_mp(this, &AISettingsPanel::_save_config));
	action_row->add_child(save_button);

	action_row->add_spacer();

	Label *quick_note = memnew(Label);
	quick_note->set_text("Saved globally for this editor install. Provider changes reset the model to that provider's default.");
	quick_note->set_autowrap_mode(TextServer::AUTOWRAP_WORD_SMART);
	quick_note->set_h_size_flags(SIZE_EXPAND_FILL);
	action_row->add_child(quick_note);

	config.instantiate();
	config->apply_provider_defaults(true, true);
	selected_provider_index = (int)config->get_provider_type();
	_apply_theme();
}

void AISettingsPanel::_notification(int p_what) {
	if (p_what == NOTIFICATION_ENTER_TREE) {
		_load_config();
		emit_signal("config_changed", config);
	} else if (p_what == NOTIFICATION_THEME_CHANGED) {
		_apply_theme();
	}
}

void AISettingsPanel::_apply_theme() {
	Color accent = get_theme_color("accent_color", "Editor");
	Color muted = get_theme_color("font_placeholder_color", "Editor");

	if (provider_summary_label) {
		provider_summary_label->add_theme_color_override("font_color", accent);
	}
	if (api_key_hint_label) {
		api_key_hint_label->add_theme_color_override("font_color", muted);
	}
}

void AISettingsPanel::_on_provider_changed(int p_index) {
	if (config.is_valid()) {
		config->set_provider_type((AIAgentConfig::ProviderType)provider_select->get_item_id(p_index));
		config->apply_provider_defaults(true, true);
	}

	if (selected_model_label) {
		selected_model_label->set_text(config->get_model_name());
	}
	if (base_url_input) {
		base_url_input->set_text("");
	}

	_refresh_provider_ui();
}

void AISettingsPanel::_refresh_provider_ui() {
	if (config.is_null()) {
		return;
	}

	const String default_model = config->get_default_model_name();
	const String effective_url = config->get_effective_base_url();

	if (provider_summary_label) {
		provider_summary_label->set_text(config->get_provider_description());
	}
	if (api_key_input) {
		api_key_input->set_placeholder(config->get_api_key_placeholder());
	}
	if (api_key_hint_label) {
		String hint = "Saved globally in the editor settings.";
		if (!config->provider_requires_api_key()) {
			hint += " Leave blank unless your local gateway requires authentication.";
		}
		api_key_hint_label->set_text(hint);
	}
	if (selected_model_label) {
		selected_model_label->set_text(default_model);
	}
	if (base_url_input) {
		base_url_input->set_placeholder(effective_url.is_empty() ? "Required for custom providers" : effective_url);
	}
}

void AISettingsPanel::_save_config() {
	if (config.is_null()) {
		config.instantiate();
	}

	config->set_provider_type((AIAgentConfig::ProviderType)selected_provider_index);
	config->set_api_key(api_key_input->get_text().strip_edges());
	config->set_model_name(""); // Model is read-only, use provider default
	config->set_base_url(base_url_input ? base_url_input->get_text().strip_edges() : String());
	config->apply_provider_defaults(true, false); // Force model to provider default

	EditorSettings *settings = EditorSettings::get_singleton();
	if (settings) {
		_save_global_provider_config(settings, config);
	}

	_refresh_provider_ui();
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

	if (_has_global_provider_config(settings)) {
		if (settings->has_setting(AI_SETTING_PROVIDER_TYPE)) {
			config->set_provider_type((AIAgentConfig::ProviderType)(int)settings->get_setting(AI_SETTING_PROVIDER_TYPE));
		}
		if (settings->has_setting(AI_SETTING_API_KEY)) {
			config->set_api_key((String)settings->get_setting(AI_SETTING_API_KEY));
		}
		if (settings->has_setting(AI_SETTING_MODEL_NAME)) {
			config->set_model_name((String)settings->get_setting(AI_SETTING_MODEL_NAME));
		}
		if (settings->has_setting(AI_SETTING_BASE_URL)) {
			config->set_base_url((String)settings->get_setting(AI_SETTING_BASE_URL));
		}
	} else {
		_load_legacy_project_config(settings, config);
	}

	config->apply_provider_defaults(config->get_model_name().is_empty(), false);

	// Update selected_provider_index and refresh visibility based on loaded provider
	selected_provider_index = (int)config->get_provider_type();
	_update_base_url_visibility();

	for (int i = 0; i < provider_select->get_item_count(); i++) {
		if (provider_select->get_item_id(i) == (int)config->get_provider_type()) {
			provider_select->select(i);
			break;
		}
	}

	api_key_input->set_text(config->get_api_key());
	base_url_input->set_text(config->get_base_url());
	_refresh_provider_ui();
}

Ref<AIAgentConfig> AISettingsPanel::get_config() const {
	return config;
}

#endif // TOOLS_ENABLED
