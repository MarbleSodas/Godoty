/**************************************************************************/
/*  ai_agent_plugin.cpp                                                   */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#ifdef TOOLS_ENABLED

#include "ai_agent_plugin.h"
#include "ai_chat_panel.h"
#include "ai_settings_panel.h"

#include "editor/editor_interface.h"
#include "editor/editor_node.h"
#include "scene/gui/box_container.h"
#include "scene/gui/button.h"

void AIAgentPlugin::_bind_methods() {
	// No additional bindings needed beyond EditorPlugin.
}

AIAgentPlugin::AIAgentPlugin() {
	// Create the chat panel and add it as a bottom panel.
	chat_panel = memnew(AIChatPanel);
	chat_panel->set_custom_minimum_size(Size2(0, 250));
	add_control_to_bottom_panel(chat_panel, "AI Agent");

	// Create settings panel (accessible via chat panel's settings button).
	settings_panel = memnew(AISettingsPanel);
	chat_panel->set_settings_panel(settings_panel);

	// Status bar button.
	status_button = memnew(Button);
	status_button->set_text("AI");
	status_button->set_tooltip_text("Toggle AI Agent Panel (Ctrl+Shift+A)");
	status_button->set_flat(true);
	status_button->connect("pressed", callable_mp(this, &AIAgentPlugin::_toggle_ai_panel));
	add_control_to_container(EditorPlugin::CONTAINER_TOOLBAR, status_button);

	// Register keyboard shortcut.
	Ref<Shortcut> shortcut;
	shortcut.instantiate();
	Ref<InputEventKey> key;
	key.instantiate();
	key->set_keycode(Key::A);
	key->set_ctrl_pressed(true);
	key->set_shift_pressed(true);
	shortcut->set_events(Array::make(key));
	status_button->set_shortcut(shortcut);

	_update_status_indicator(false);
}

AIAgentPlugin::~AIAgentPlugin() {
	// Panels are freed by the editor when removed.
}

void AIAgentPlugin::_notification(int p_what) {
	if (p_what == NOTIFICATION_ENTER_TREE) {
		// Plugin is now in the editor tree.
	} else if (p_what == NOTIFICATION_EXIT_TREE) {
		if (chat_panel) {
			remove_control_from_bottom_panel(chat_panel);
			memdelete(chat_panel);
			chat_panel = nullptr;
		}
		if (status_button) {
			remove_control_from_container(EditorPlugin::CONTAINER_TOOLBAR, status_button);
			memdelete(status_button);
			status_button = nullptr;
		}
	}
}

void AIAgentPlugin::_make_visible(bool p_visible) {
	if (chat_panel) {
		chat_panel->set_visible(p_visible);
	}
}

void AIAgentPlugin::_toggle_ai_panel() {
	if (chat_panel) {
		make_bottom_panel_item_visible(chat_panel);
	}
}

void AIAgentPlugin::_update_status_indicator(bool p_connected) {
	if (!status_button) {
		return;
	}
	if (p_connected) {
		status_button->set_text("AI ●");
		status_button->set_tooltip_text("AI Agent: Connected");
	} else {
		status_button->set_text("AI ○");
		status_button->set_tooltip_text("AI Agent: Not configured — Click to open");
	}
}

#endif // TOOLS_ENABLED
