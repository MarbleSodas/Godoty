/**************************************************************************/
/*  ai_agent_plugin.h                                                     */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#ifdef TOOLS_ENABLED

#include "editor/plugins/editor_plugin.h"

class AIChatPanel;
class AISettingsPanel;
class AIAgentConfig;

class AIAgentPlugin : public EditorPlugin {
	GDCLASS(AIAgentPlugin, EditorPlugin);

	AIChatPanel *chat_panel = nullptr;
	AISettingsPanel *settings_panel = nullptr;
	Button *status_button = nullptr;

	void _on_config_changed(const Ref<AIAgentConfig> &p_config);
	void _toggle_ai_panel();
	void _update_status_indicator(bool p_connected);
	void _refresh_ui_icons();

protected:
	static void _bind_methods();
	void _notification(int p_what);

public:
	String get_plugin_name() const override { return "AI Agent"; }
	bool has_main_screen() const override { return false; }

	void _make_visible(bool p_visible);

	AIAgentPlugin();
	~AIAgentPlugin();
};

#endif // TOOLS_ENABLED
