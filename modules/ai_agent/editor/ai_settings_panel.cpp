/**************************************************************************/
/*  ai_settings_panel.cpp                                                 */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#ifdef TOOLS_ENABLED

#include "ai_settings_panel.h"

#include "modules/ai_agent/ai_tool_registry.h"

#include "scene/gui/button.h"
#include "scene/gui/check_box.h"
#include "scene/gui/label.h"
#include "scene/gui/line_edit.h"
#include "scene/gui/option_button.h"
#include "scene/gui/scroll_container.h"
#include "scene/gui/separator.h"
#include "scene/gui/spin_box.h"
#include "scene/gui/text_edit.h"

#include "editor/settings/editor_settings.h"

void AISettingsPanel::_bind_methods() {
	ADD_SIGNAL(MethodInfo("config_changed",
			PropertyInfo(Variant::OBJECT, "config", PROPERTY_HINT_RESOURCE_TYPE, "AIAgentConfig", PROPERTY_USAGE_DEFAULT, "AIAgentConfig")));
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

	add_child(memnew(HSeparator));

	stream_responses_checkbox = memnew(CheckBox);
	stream_responses_checkbox->set_text("Stream responses");
	stream_responses_checkbox->set_pressed(true);
	add_child(stream_responses_checkbox);

	allow_all_tools_checkbox = memnew(CheckBox);
	allow_all_tools_checkbox->set_text("Allow all registered tools");
	allow_all_tools_checkbox->set_pressed(true);
	allow_all_tools_checkbox->connect("toggled", callable_mp(this, &AISettingsPanel::_on_allow_all_tools_toggled));
	add_child(allow_all_tools_checkbox);

	Label *tools_label = memnew(Label);
	tools_label->set_text("Enabled Tools:");
	add_child(tools_label);

	ScrollContainer *tools_scroll = memnew(ScrollContainer);
	tools_scroll->set_custom_minimum_size(Size2(0, 120));
	tools_scroll->set_v_size_flags(SIZE_EXPAND_FILL);
	add_child(tools_scroll);

	tool_list_container = memnew(VBoxContainer);
	tool_list_container->set_h_size_flags(SIZE_EXPAND_FILL);
	tools_scroll->add_child(tool_list_container);

	// --- Save button ---
	save_button = memnew(Button);
	save_button->set_text("Save Settings");
	save_button->connect("pressed", callable_mp(this, &AISettingsPanel::_save_config));
	add_child(save_button);

	// Initialize config.
	config.instantiate();
}

void AISettingsPanel::_notification(int p_what) {
	if (p_what == NOTIFICATION_ENTER_TREE) {
		_refresh_tool_list();
		_load_config();
		emit_signal("config_changed", config);
	}
}

void AISettingsPanel::_on_provider_changed(int p_index) {
	int provider = provider_select->get_item_id(p_index);
	// Update model placeholder and default value based on provider.
	switch (provider) {
		case AIAgentConfig::PROVIDER_OPENAI:
			model_input->set_placeholder("e.g., gpt-4o, gpt-4o-mini");
			if (model_input->get_text().is_empty()) {
				model_input->set_text("gpt-4o");
			}
			max_tokens_spin->set_value(4096);
			break;
		case AIAgentConfig::PROVIDER_ANTHROPIC:
			model_input->set_placeholder("e.g., claude-sonnet-4-20250514, claude-3-5-sonnet");
			if (model_input->get_text().is_empty()) {
				model_input->set_text("claude-sonnet-4-20250514");
			}
			max_tokens_spin->set_value(4096);
			break;
		case AIAgentConfig::PROVIDER_MINIMAX:
			model_input->set_placeholder("e.g., MiniMax-M1, MiniMax-Text-01");
			if (model_input->get_text().is_empty()) {
				model_input->set_text("MiniMax-M1");
			}
			max_tokens_spin->set_value(4096);
			break;
		case AIAgentConfig::PROVIDER_LOCAL:
			model_input->set_placeholder("e.g., llama3, codellama, mistral");
			max_tokens_spin->set_value(4096);
			break;
		default:
			model_input->set_placeholder("Model identifier");
			break;
	}
}

void AISettingsPanel::_on_allow_all_tools_toggled(bool p_pressed) {
	for (const KeyValue<String, CheckBox *> &E : tool_checkboxes) {
		if (E.value) {
			E.value->set_disabled(p_pressed);
		}
	}
}

void AISettingsPanel::_refresh_tool_list() {
	if (!tool_list_container) {
		return;
	}

	for (const KeyValue<String, CheckBox *> &E : tool_checkboxes) {
		if (E.value) {
			E.value->queue_free();
		}
	}
	tool_checkboxes.clear();

	AIToolRegistry *registry = AIToolRegistry::get_singleton();
	if (!registry) {
		return;
	}

	PackedStringArray tool_names = registry->get_tool_names();
	for (int i = 0; i < tool_names.size(); i++) {
		CheckBox *tool_checkbox = memnew(CheckBox);
		tool_checkbox->set_text(tool_names[i]);
		tool_checkbox->set_pressed(true);
		tool_list_container->add_child(tool_checkbox);
		tool_checkboxes[tool_names[i]] = tool_checkbox;
	}

	_on_allow_all_tools_toggled(allow_all_tools_checkbox && allow_all_tools_checkbox->is_pressed());
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
	config->set_stream_responses(stream_responses_checkbox->is_pressed());

	PackedStringArray enabled_tools;
	if (!allow_all_tools_checkbox->is_pressed()) {
		for (const KeyValue<String, CheckBox *> &E : tool_checkboxes) {
			if (E.value && E.value->is_pressed()) {
				enabled_tools.push_back(E.key);
			}
		}
	}
	config->set_enabled_tools(enabled_tools);

	EditorSettings *settings = EditorSettings::get_singleton();
	if (settings) {
		settings->set_project_metadata("ai_agent", "provider_type", (int)config->get_provider_type());
		settings->set_project_metadata("ai_agent", "api_key", config->get_api_key());
		settings->set_project_metadata("ai_agent", "model_name", config->get_model_name());
		settings->set_project_metadata("ai_agent", "base_url", config->get_base_url());
		settings->set_project_metadata("ai_agent", "temperature", (double)config->get_temperature());
		settings->set_project_metadata("ai_agent", "max_tokens", config->get_max_tokens());
		settings->set_project_metadata("ai_agent", "system_prompt", config->get_system_prompt());
		settings->set_project_metadata("ai_agent", "stream_responses", config->get_stream_responses());
		settings->set_project_metadata("ai_agent", "enabled_tools", config->get_enabled_tools());
		settings->save_project_metadata();
	}

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

	config->set_provider_type((AIAgentConfig::ProviderType)(int)settings->get_project_metadata("ai_agent", "provider_type", (int)AIAgentConfig::PROVIDER_OPENAI));
	config->set_api_key(settings->get_project_metadata("ai_agent", "api_key", String()));
	config->set_model_name(settings->get_project_metadata("ai_agent", "model_name", String("gpt-4o")));
	config->set_base_url(settings->get_project_metadata("ai_agent", "base_url", String()));
	config->set_temperature((float)(double)settings->get_project_metadata("ai_agent", "temperature", 0.7));
	config->set_max_tokens((int)settings->get_project_metadata("ai_agent", "max_tokens", 4096));
	config->set_system_prompt(settings->get_project_metadata("ai_agent", "system_prompt", String()));
	config->set_stream_responses(settings->get_project_metadata("ai_agent", "stream_responses", true));
	config->set_enabled_tools(settings->get_project_metadata("ai_agent", "enabled_tools", PackedStringArray()));

	// Update UI fields from config.
	provider_select->select(config->get_provider_type());
	api_key_input->set_text(config->get_api_key());
	model_input->set_text(config->get_model_name());
	base_url_input->set_text(config->get_base_url());
	temperature_spin->set_value(config->get_temperature());
	max_tokens_spin->set_value(config->get_max_tokens());
	system_prompt_input->set_text(config->get_system_prompt());
	stream_responses_checkbox->set_pressed(config->get_stream_responses());
	allow_all_tools_checkbox->set_pressed(config->get_enabled_tools().is_empty());

	for (const KeyValue<String, CheckBox *> &E : tool_checkboxes) {
		if (!E.value) {
			continue;
		}
		E.value->set_pressed(config->get_enabled_tools().is_empty() || config->get_enabled_tools().has(E.key));
	}

	_on_allow_all_tools_toggled(allow_all_tools_checkbox->is_pressed());
	_on_provider_changed(provider_select->get_selected());
}

Ref<AIAgentConfig> AISettingsPanel::get_config() const {
	return config;
}

#endif // TOOLS_ENABLED
