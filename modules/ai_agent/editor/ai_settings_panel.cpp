/**************************************************************************/
/*  ai_settings_panel.cpp                                                 */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#ifdef TOOLS_ENABLED

#include "ai_settings_panel.h"

#include "scene/gui/button.h"
#include "scene/gui/label.h"
#include "scene/gui/line_edit.h"
#include "scene/gui/option_button.h"
#include "scene/gui/separator.h"
#include "scene/gui/spin_box.h"
#include "scene/gui/text_edit.h"

void AISettingsPanel::_bind_methods() {
	// Internal bindings only.
}

AISettingsPanel::AISettingsPanel() {
	set_name("AISettings");
	set_visible(false); // Hidden by default; toggled from chat panel.

	Label *title = memnew(Label);
	title->set_text("AI Agent Settings");
	add_child(title);

	add_child(memnew(HSeparator));

	// --- Provider selection ---
	{
		HBoxContainer *row = memnew(HBoxContainer);
		add_child(row);
		Label *lbl = memnew(Label);
		lbl->set_text("Provider:");
		lbl->set_custom_minimum_size(Size2(120, 0));
		row->add_child(lbl);
		provider_select = memnew(OptionButton);
		provider_select->add_item("OpenAI", AIAgentConfig::PROVIDER_OPENAI);
		provider_select->add_item("Anthropic", AIAgentConfig::PROVIDER_ANTHROPIC);
		provider_select->add_item("MiniMax", AIAgentConfig::PROVIDER_MINIMAX);
		provider_select->add_item("Local (Ollama)", AIAgentConfig::PROVIDER_LOCAL);
		provider_select->add_item("Custom", AIAgentConfig::PROVIDER_CUSTOM);
		provider_select->set_h_size_flags(SIZE_EXPAND_FILL);
		provider_select->connect("item_selected", callable_mp(this, &AISettingsPanel::_on_provider_changed));
		row->add_child(provider_select);
	}

	// --- API Key ---
	{
		HBoxContainer *row = memnew(HBoxContainer);
		add_child(row);
		Label *lbl = memnew(Label);
		lbl->set_text("API Key:");
		lbl->set_custom_minimum_size(Size2(120, 0));
		row->add_child(lbl);
		api_key_input = memnew(LineEdit);
		api_key_input->set_secret(true);
		api_key_input->set_placeholder("Enter your API key...");
		api_key_input->set_h_size_flags(SIZE_EXPAND_FILL);
		row->add_child(api_key_input);
	}

	// --- Model ---
	{
		HBoxContainer *row = memnew(HBoxContainer);
		add_child(row);
		Label *lbl = memnew(Label);
		lbl->set_text("Model:");
		lbl->set_custom_minimum_size(Size2(120, 0));
		row->add_child(lbl);
		model_input = memnew(LineEdit);
		model_input->set_placeholder("e.g., gpt-4o, claude-3.5-sonnet, MiniMax-M1");
		model_input->set_h_size_flags(SIZE_EXPAND_FILL);
		row->add_child(model_input);
	}

	// --- Base URL ---
	{
		HBoxContainer *row = memnew(HBoxContainer);
		add_child(row);
		Label *lbl = memnew(Label);
		lbl->set_text("Base URL:");
		lbl->set_custom_minimum_size(Size2(120, 0));
		row->add_child(lbl);
		base_url_input = memnew(LineEdit);
		base_url_input->set_placeholder("Leave empty for default");
		base_url_input->set_h_size_flags(SIZE_EXPAND_FILL);
		row->add_child(base_url_input);
	}

	// --- Temperature ---
	{
		HBoxContainer *row = memnew(HBoxContainer);
		add_child(row);
		Label *lbl = memnew(Label);
		lbl->set_text("Temperature:");
		lbl->set_custom_minimum_size(Size2(120, 0));
		row->add_child(lbl);
		temperature_spin = memnew(SpinBox);
		temperature_spin->set_min(0.0);
		temperature_spin->set_max(2.0);
		temperature_spin->set_step(0.1);
		temperature_spin->set_value(0.7);
		temperature_spin->set_h_size_flags(SIZE_EXPAND_FILL);
		row->add_child(temperature_spin);
	}

	// --- Max Tokens ---
	{
		HBoxContainer *row = memnew(HBoxContainer);
		add_child(row);
		Label *lbl = memnew(Label);
		lbl->set_text("Max Tokens:");
		lbl->set_custom_minimum_size(Size2(120, 0));
		row->add_child(lbl);
		max_tokens_spin = memnew(SpinBox);
		max_tokens_spin->set_min(100);
		max_tokens_spin->set_max(128000);
		max_tokens_spin->set_step(100);
		max_tokens_spin->set_value(4096);
		max_tokens_spin->set_h_size_flags(SIZE_EXPAND_FILL);
		row->add_child(max_tokens_spin);
	}

	add_child(memnew(HSeparator));

	// --- System Prompt ---
	{
		Label *lbl = memnew(Label);
		lbl->set_text("System Prompt:");
		add_child(lbl);
		system_prompt_input = memnew(TextEdit);
		system_prompt_input->set_custom_minimum_size(Size2(0, 80));
		system_prompt_input->set_placeholder("You are a helpful AI assistant integrated into the Godoty game engine editor...");
		system_prompt_input->set_line_wrapping_mode(TextEdit::LineWrappingMode::LINE_WRAPPING_BOUNDARY);
		add_child(system_prompt_input);
	}

	// --- Save button ---
	save_button = memnew(Button);
	save_button->set_text("Save Settings");
	save_button->connect("pressed", callable_mp(this, &AISettingsPanel::_save_config));
	add_child(save_button);

	// Initialize config.
	config.instantiate();
}

void AISettingsPanel::_on_provider_changed(int p_index) {
	int provider = provider_select->get_item_id(p_index);
	// Update model placeholder based on provider.
	switch (provider) {
		case AIAgentConfig::PROVIDER_OPENAI:
			model_input->set_placeholder("e.g., gpt-4o, gpt-4o-mini");
			break;
		case AIAgentConfig::PROVIDER_ANTHROPIC:
			model_input->set_placeholder("e.g., claude-3.5-sonnet, claude-3-haiku");
			break;
		case AIAgentConfig::PROVIDER_MINIMAX:
			model_input->set_placeholder("e.g., MiniMax-M1, MiniMax-Text-01");
			break;
		case AIAgentConfig::PROVIDER_LOCAL:
			model_input->set_placeholder("e.g., llama3, codellama, mistral");
			break;
		default:
			model_input->set_placeholder("Model identifier");
			break;
	}
}

void AISettingsPanel::_save_config() {
	if (config.is_null()) {
		config.instantiate();
	}

	config->set_provider_type((AIAgentConfig::ProviderType)provider_select->get_selected_id());
	config->set_api_key(api_key_input->get_text());
	config->set_model_name(model_input->get_text());
	config->set_base_url(base_url_input->get_text());
	config->set_temperature(temperature_spin->get_value());
	config->set_max_tokens((int)max_tokens_spin->get_value());
	config->set_system_prompt(system_prompt_input->get_text());
}

void AISettingsPanel::_load_config() {
	if (config.is_null()) {
		return;
	}

	provider_select->select(config->get_provider_type());
	api_key_input->set_text(config->get_api_key());
	model_input->set_text(config->get_model_name());
	base_url_input->set_text(config->get_base_url());
	temperature_spin->set_value(config->get_temperature());
	max_tokens_spin->set_value(config->get_max_tokens());
	system_prompt_input->set_text(config->get_system_prompt());
}

Ref<AIAgentConfig> AISettingsPanel::get_config() const {
	return config;
}

#endif // TOOLS_ENABLED
