/**************************************************************************/
/*  ai_agent_plugin.cpp                                                   */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#ifdef TOOLS_ENABLED

#include "ai_agent_plugin.h"
#include "../ai_agent_config.h"
#include "ai_chat_panel.h"
#include "ai_settings_panel.h"

#include "editor/docks/editor_dock.h"
#include "editor/editor_string_names.h"
#include "editor/editor_interface.h"
#include "editor/editor_node.h"
#include "editor/themes/editor_scale.h"
#include "scene/gui/box_container.h"
#include "scene/gui/button.h"

namespace {
AIAgentPlugin *ai_agent_plugin_singleton = nullptr;
}

void AIAgentPlugin::_bind_methods() {
	// No additional bindings needed beyond EditorPlugin.
}

AIAgentPlugin::AIAgentPlugin() {
	if (ai_agent_plugin_singleton != nullptr) {
		return;
	}
	ai_agent_plugin_singleton = this;

	Ref<Shortcut> shortcut;
	shortcut.instantiate();
	Ref<InputEventKey> key;
	key.instantiate();
	key->set_keycode(Key::A);
	key->set_ctrl_pressed(true);
	key->set_shift_pressed(true);
	Array events;
	events.push_back(key);
	shortcut->set_name("Toggle AI Agent Panel");
	shortcut->set_events(events);

	// Create the chat panel and place it in the right dock.
	chat_panel = memnew(AIChatPanel);
	chat_panel->set_name("AI Agent");
	chat_panel->set_custom_minimum_size(Size2(0, 320 * EDSCALE));
	add_control_to_dock(EditorPlugin::DOCK_SLOT_RIGHT_UL, chat_panel, shortcut);

	// Create settings panel (accessible via chat panel's settings button).
	settings_panel = memnew(AISettingsPanel);
	settings_panel->set_visible(false);
	settings_panel->connect("config_changed", callable_mp(this, &AIAgentPlugin::_on_config_changed));
	chat_panel->set_settings_panel(settings_panel);

	// Status bar button.
	status_button = memnew(Button);
	status_button->set_text("");
	status_button->set_tooltip_text("Toggle AI Agent Panel (Ctrl+Shift+A)");
	status_button->set_flat(true);
	status_button->set_focus_mode(Control::FOCUS_NONE);
	status_button->set_custom_minimum_size(Size2(30 * EDSCALE, 30 * EDSCALE));
	status_button->set_icon_alignment(HORIZONTAL_ALIGNMENT_CENTER);
	status_button->set_vertical_icon_alignment(VERTICAL_ALIGNMENT_CENTER);
	status_button->connect("pressed", callable_mp(this, &AIAgentPlugin::_toggle_ai_panel));
	add_control_to_container(EditorPlugin::CONTAINER_TOOLBAR, status_button);
	status_button->set_shortcut(shortcut);

	_refresh_ui_icons();
	_update_status_indicator(false);
	if (settings_panel) {
		_on_config_changed(settings_panel->get_config());
	}
}

AIAgentPlugin::~AIAgentPlugin() {
	// Panels are freed by the editor when removed.
}

void AIAgentPlugin::_notification(int p_what) {
	if (ai_agent_plugin_singleton != this) {
		return;
	}

	if (p_what == NOTIFICATION_ENTER_TREE) {
		_refresh_ui_icons();
	} else if (p_what == NOTIFICATION_EXIT_TREE) {
		if (chat_panel) {
			remove_control_from_docks(chat_panel);
			memdelete(chat_panel);
			chat_panel = nullptr;
		}
		if (status_button) {
			remove_control_from_container(EditorPlugin::CONTAINER_TOOLBAR, status_button);
			memdelete(status_button);
			status_button = nullptr;
		}
		settings_panel = nullptr;
		ai_agent_plugin_singleton = nullptr;
	}
}

void AIAgentPlugin::_make_visible(bool p_visible) {
	if (chat_panel) {
		EditorDock *dock = Object::cast_to<EditorDock>(chat_panel->get_parent());
		if (!dock) {
			return;
		}
		if (p_visible) {
			dock->make_visible();
		} else {
			dock->close();
		}
	}
}

void AIAgentPlugin::_on_config_changed(const Ref<AIAgentConfig> &p_config) {
	bool configured = false;
	if (p_config.is_valid()) {
		configured = p_config->is_configured();
	}
	_update_status_indicator(configured);
}

void AIAgentPlugin::_toggle_ai_panel() {
	if (chat_panel) {
		EditorDock *dock = Object::cast_to<EditorDock>(chat_panel->get_parent());
		if (!dock) {
			return;
		}
		if (dock->is_visible_in_tree()) {
			dock->close();
		} else {
			dock->make_visible();
		}
	}
}

void AIAgentPlugin::_refresh_ui_icons() {
	if (!status_button) {
		return;
	}

	const Ref<Texture2D> ai_icon = status_button->get_theme_icon(SNAME("AIAgentModeOrchestrate"), EditorStringName(EditorIcons));
	status_button->set_button_icon(ai_icon);
	if (chat_panel && ai_icon.is_valid()) {
		set_dock_tab_icon(chat_panel, ai_icon);
	}
}

void AIAgentPlugin::_update_status_indicator(bool p_connected) {
	if (!status_button) {
		return;
	}
	const Color strong = status_button->get_theme_color("font_color", EditorStringName(Editor));
	const Color muted = status_button->get_theme_color("font_placeholder_color", EditorStringName(Editor));
	const Color accent = status_button->get_theme_color("accent_color", EditorStringName(Editor));

	if (p_connected) {
		status_button->add_theme_color_override("icon_normal_color", accent.lerp(strong, 0.18f));
		status_button->add_theme_color_override("icon_hover_color", strong);
		status_button->add_theme_color_override("icon_pressed_color", strong);
		status_button->add_theme_color_override("icon_hover_pressed_color", strong);
		status_button->set_tooltip_text("AI Agent: Connected\nToggle AI Agent Panel (Ctrl+Shift+A)");
	} else {
		status_button->add_theme_color_override("icon_normal_color", muted.lerp(strong, 0.35f));
		status_button->add_theme_color_override("icon_hover_color", strong);
		status_button->add_theme_color_override("icon_pressed_color", strong);
		status_button->add_theme_color_override("icon_hover_pressed_color", strong);
		status_button->set_tooltip_text("AI Agent: Not configured\nToggle AI Agent Panel (Ctrl+Shift+A)");
	}
}

#endif // TOOLS_ENABLED
