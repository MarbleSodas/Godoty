/**************************************************************************/
/*  ai_chat_panel.h                                                       */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#ifdef TOOLS_ENABLED

#include "modules/ai_agent/ai_agent_session.h"
#include "scene/gui/control.h"
#include "scene/gui/container.h"
#include "scene/gui/box_container.h"

class RichTextLabel;
class TextEdit;
class Button;
class ConfirmationDialog;
class AISettingsPanel;

class AIChatPanel : public VBoxContainer {
	GDCLASS(AIChatPanel, VBoxContainer);

	struct ChatEntry {
		String role;
		String content;
		Color color;
	};

	RichTextLabel *message_display = nullptr;
	TextEdit *input_field = nullptr;
	Button *send_button = nullptr;
	Button *clear_button = nullptr;
	Button *settings_button = nullptr;
	Button *cancel_button = nullptr;
	ConfirmationDialog *approval_dialog = nullptr;

	Ref<AIAgentSession> session;
	AISettingsPanel *settings_panel = nullptr;
	Vector<ChatEntry> transcript;
	int active_assistant_entry = -1;
	String pending_approval_tool_call_id;
	String pending_approval_tool_name;
	Dictionary pending_approval_arguments;

	void _send_message();
	void _clear_chat();
	void _toggle_settings();
	void _cancel_request();
	void _approve_pending_tool_call();
	void _deny_pending_tool_call();

	// Signal handlers.
	void _on_message_received(const Ref<AIMessage> &p_message);
	void _on_stream_chunk(const String &p_chunk);
	void _on_tool_call_requested(const String &p_tool_name, const Dictionary &p_args, const String &p_tool_call_id);
	void _on_tool_call_completed(const String &p_tool_name, const Variant &p_result);
	void _on_approval_required(const String &p_tool_name, const Dictionary &p_args, const String &p_tool_call_id);
	void _on_error_occurred(const String &p_error);
	void _on_session_state_changed(int p_state);
	void _on_config_changed(const Ref<AIAgentConfig> &p_config);

	String _escape_bbcode(const String &p_text) const;
	void _render_transcript();
	void _append_message(const String &p_role, const String &p_content, const Color &p_color, bool p_merge_with_active = false);
	void _input_gui_input(const Ref<InputEvent> &p_event);

protected:
	static void _bind_methods();
	void _notification(int p_what);

public:
	void set_settings_panel(AISettingsPanel *p_panel);
	void initialize_session();

	AIChatPanel();
};

#endif // TOOLS_ENABLED
