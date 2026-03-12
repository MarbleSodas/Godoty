/**************************************************************************/
/*  ai_settings_panel.h                                                   */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#ifdef TOOLS_ENABLED

#include "modules/ai_agent/ai_agent_config.h"
#include "scene/gui/box_container.h"

class LineEdit;
class OptionButton;
class SpinBox;
class TextEdit;

class AISettingsPanel : public VBoxContainer {
	GDCLASS(AISettingsPanel, VBoxContainer);

	OptionButton *provider_select = nullptr;
	LineEdit *api_key_input = nullptr;
	LineEdit *model_input = nullptr;
	LineEdit *base_url_input = nullptr;
	SpinBox *temperature_spin = nullptr;
	SpinBox *max_tokens_spin = nullptr;
	TextEdit *system_prompt_input = nullptr;
	Button *save_button = nullptr;

	Ref<AIAgentConfig> config;

	void _on_provider_changed(int p_index);
	void _save_config();
	void _load_config();

protected:
	static void _bind_methods();

public:
	Ref<AIAgentConfig> get_config() const;

	AISettingsPanel();
};

#endif // TOOLS_ENABLED
