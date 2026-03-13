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
#include "scene/gui/box_container.h"
#include "scene/gui/line_edit.h"
#include "scene/gui/option_button.h"
#include "scene/gui/button.h"

class Label;

class AISettingsPanel : public VBoxContainer {
	GDCLASS(AISettingsPanel, VBoxContainer);

	Label *provider_summary_label = nullptr;
	OptionButton *provider_select = nullptr;
	HBoxContainer *api_key_row = nullptr;
	LineEdit *api_key_input = nullptr;
	Label *api_key_hint_label = nullptr;
	LineEdit *base_url_input = nullptr;
	Button *save_button = nullptr;
	Vector<Button *> provider_cards;
	HBoxContainer *base_url_container = nullptr;
	Label *selected_model_label = nullptr;
	int selected_provider_index = 0;

	Ref<AIAgentConfig> config;

	void _apply_theme();
	void _on_provider_changed(int p_index);
	void _refresh_provider_ui();
	void _save_config();
	void _load_config();
	void _create_provider_cards();
	void _on_card_selected(int p_index);
	void _update_base_url_visibility();

protected:
	static void _bind_methods();
	void _notification(int p_what);

public:
	Ref<AIAgentConfig> get_config() const;

	AISettingsPanel();
};

#endif // TOOLS_ENABLED
