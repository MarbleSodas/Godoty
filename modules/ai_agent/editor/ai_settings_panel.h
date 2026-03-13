/**************************************************************************/
/*  ai_settings_panel.h                                                   */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#ifdef TOOLS_ENABLED

#include "modules/ai_agent/ai_agent_config.h"
#include "scene/gui/control.h"
#include "scene/gui/container.h"
#include "scene/gui/box_container.h"

#include "scene/gui/line_edit.h"
#include "scene/gui/option_button.h"
#include "scene/gui/spin_box.h"
#include "scene/gui/text_edit.h"
#include "scene/gui/button.h"
#include "scene/gui/check_box.h"
#include "scene/gui/scroll_container.h"

class AISettingsPanel : public VBoxContainer {
	GDCLASS(AISettingsPanel, VBoxContainer);

	OptionButton *provider_select = nullptr;
	LineEdit *api_key_input = nullptr;
	LineEdit *model_input = nullptr;
	LineEdit *base_url_input = nullptr;
	SpinBox *temperature_spin = nullptr;
	SpinBox *max_tokens_spin = nullptr;
	TextEdit *system_prompt_input = nullptr;
	CheckBox *stream_responses_checkbox = nullptr;
	CheckBox *allow_all_tools_checkbox = nullptr;
	VBoxContainer *tool_list_container = nullptr;
	Button *save_button = nullptr;

	Ref<AIAgentConfig> config;
	HashMap<String, CheckBox *> tool_checkboxes;

	void _on_provider_changed(int p_index);
	void _on_allow_all_tools_toggled(bool p_pressed);
	void _refresh_tool_list();
	void _save_config();
	void _load_config();

protected:
	static void _bind_methods();
	void _notification(int p_what);

public:
	Ref<AIAgentConfig> get_config() const;

	AISettingsPanel();
};

#endif // TOOLS_ENABLED
