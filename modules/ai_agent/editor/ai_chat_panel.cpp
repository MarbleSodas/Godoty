/**************************************************************************/
/*  ai_chat_panel.cpp                                                     */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#ifdef TOOLS_ENABLED

#include "ai_chat_panel.h"
#include "ai_settings_panel.h"

#include "modules/ai_agent/ai_agent_config.h"
#include "modules/ai_agent/ai_message.h"

#include "editor/editor_interface.h"
#include "scene/gui/button.h"
#include "scene/gui/rich_text_label.h"
#include "scene/gui/separator.h"
#include "scene/gui/text_edit.h"

void AIChatPanel::_bind_methods() {
	// Internal signals and methods.
}

AIChatPanel::AIChatPanel() {
	set_name("AIChat");

	// --- Top toolbar ---
	HBoxContainer *toolbar = memnew(HBoxContainer);
	add_child(toolbar);

	Label *title = memnew(Label);
	title->set_text("AI Agent");
	title->set_horizontal_alignment(HORIZONTAL_ALIGNMENT_LEFT);
	toolbar->add_child(title);

	toolbar->add_spacer();

	settings_button = memnew(Button);
	settings_button->set_text("Settings");
	settings_button->set_flat(true);
	settings_button->set_tooltip_text("Configure AI provider settings");
	settings_button->connect("pressed", callable_mp(this, &AIChatPanel::_toggle_settings));
	toolbar->add_child(settings_button);

	clear_button = memnew(Button);
	clear_button->set_text("Clear");
	clear_button->set_flat(true);
	clear_button->set_tooltip_text("Clear conversation history");
	clear_button->connect("pressed", callable_mp(this, &AIChatPanel::_clear_chat));
	toolbar->add_child(clear_button);

	add_child(memnew(HSeparator));

	// --- Message display area ---
	message_display = memnew(RichTextLabel);
	message_display->set_v_size_flags(SIZE_EXPAND_FILL);
	message_display->set_selection_enabled(true);
	message_display->set_scroll_follow(true);
	message_display->set_use_bbcode(true);
	message_display->set_fit_content(false);
	add_child(message_display);

	// Welcome message.
	message_display->append_text("[color=#888888][i]Welcome to the Godoty AI Agent.[/i][/color]\n");
	message_display->append_text("[color=#888888][i]Configure your API key in Settings, then start chatting.[/i][/color]\n\n");

	// --- Input area ---
	HBoxContainer *input_bar = memnew(HBoxContainer);
	add_child(input_bar);

	input_field = memnew(TextEdit);
	input_field->set_h_size_flags(SIZE_EXPAND_FILL);
	input_field->set_custom_minimum_size(Size2(0, 60));
	input_field->set_placeholder("Ask the AI agent anything...");
	input_field->set_line_wrapping_mode(TextEdit::LineWrappingMode::LINE_WRAPPING_BOUNDARY);
	input_field->connect("gui_input", callable_mp(this, &AIChatPanel::_input_gui_input));
	input_bar->add_child(input_field);

	VBoxContainer *button_box = memnew(VBoxContainer);
	input_bar->add_child(button_box);

	send_button = memnew(Button);
	send_button->set_text("Send");
	send_button->set_tooltip_text("Send message (Ctrl+Enter)");
	send_button->connect("pressed", callable_mp(this, &AIChatPanel::_send_message));
	button_box->add_child(send_button);

	cancel_button = memnew(Button);
	cancel_button->set_text("Cancel");
	cancel_button->set_tooltip_text("Cancel current request");
	cancel_button->set_visible(false);
	cancel_button->connect("pressed", callable_mp(this, &AIChatPanel::_cancel_request));
	button_box->add_child(cancel_button);
}

void AIChatPanel::_notification(int p_what) {
	if (p_what == NOTIFICATION_ENTER_TREE) {
		initialize_session();
	}
}

void AIChatPanel::set_settings_panel(AISettingsPanel *p_panel) {
	settings_panel = p_panel;
}

void AIChatPanel::initialize_session() {
	if (session.is_valid()) {
		return;
	}

	session.instantiate();

	// Connect session signals.
	session->connect("message_received", callable_mp(this, &AIChatPanel::_on_message_received));
	session->connect("stream_chunk", callable_mp(this, &AIChatPanel::_on_stream_chunk));
	session->connect("tool_call_requested", callable_mp(this, &AIChatPanel::_on_tool_call_requested));
	session->connect("error_occurred", callable_mp(this, &AIChatPanel::_on_error_occurred));
	session->connect("state_changed", callable_mp(this, &AIChatPanel::_on_session_state_changed));
}

void AIChatPanel::_send_message() {
	String text = input_field->get_text().strip_edges();
	if (text.is_empty()) {
		return;
	}

	// Display user message.
	_append_message("You", text, Color(0.4, 0.8, 1.0));

	// Clear input.
	input_field->set_text("");

	// Send to session.
	if (session.is_valid()) {
		session->send_user_message(text);
	}
}

void AIChatPanel::_clear_chat() {
	message_display->clear();
	message_display->append_text("[color=#888888][i]Conversation cleared.[/i][/color]\n\n");
	if (session.is_valid()) {
		session->clear_history();
	}
}

void AIChatPanel::_toggle_settings() {
	if (settings_panel) {
		settings_panel->set_visible(!settings_panel->is_visible());
	}
}

void AIChatPanel::_cancel_request() {
	if (session.is_valid()) {
		session->cancel();
	}
}

void AIChatPanel::_on_message_received(const Ref<AIMessage> &p_message) {
	if (p_message.is_valid()) {
		_append_message("AI", p_message->get_content(), Color(0.6, 1.0, 0.6));
	}
}

void AIChatPanel::_on_stream_chunk(const String &p_chunk) {
	// Append streaming text directly (no formatting wrapper for chunks).
	message_display->append_text(p_chunk);
}

void AIChatPanel::_on_tool_call_requested(const String &p_tool_name, const Dictionary &p_args) {
	String args_str;
	Array keys = p_args.keys();
	for (int i = 0; i < keys.size(); i++) {
		if (i > 0) {
			args_str += ", ";
		}
		args_str += String(keys[i]) + "=" + String(p_args[keys[i]]);
	}

	message_display->append_text("[color=#FFAA00][b]🔧 Tool Call:[/b] " + p_tool_name + "(" + args_str + ")[/color]\n");
}

void AIChatPanel::_on_error_occurred(const String &p_error) {
	message_display->append_text("[color=#FF4444][b]Error:[/b] " + p_error + "[/color]\n\n");
}

void AIChatPanel::_on_session_state_changed(int p_state) {
	bool is_busy = (p_state != AIAgentSession::STATE_IDLE && p_state != AIAgentSession::STATE_ERROR);
	send_button->set_disabled(is_busy);
	cancel_button->set_visible(is_busy);

	if (is_busy) {
		send_button->set_text("...");
	} else {
		send_button->set_text("Send");
	}
}

void AIChatPanel::_append_message(const String &p_role, const String &p_content, const Color &p_color) {
	String hex = p_color.to_html(false);
	message_display->append_text("[color=#" + hex + "][b]" + p_role + ":[/b][/color] ");
	message_display->append_text(p_content + "\n\n");
}

void AIChatPanel::_input_gui_input(const Ref<InputEvent> &p_event) {
	Ref<InputEventKey> key = p_event;
	if (key.is_valid() && key->is_pressed() && !key->is_echo()) {
		// Ctrl+Enter to send.
		if (key->get_keycode() == Key::ENTER && key->is_ctrl_pressed()) {
			_send_message();
			input_field->accept_event();
		}
	}
}

#endif // TOOLS_ENABLED
