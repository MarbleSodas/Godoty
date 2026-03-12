/**************************************************************************/
/*  ai_chat_panel.cpp                                                     */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#ifdef TOOLS_ENABLED

#include "ai_chat_panel.h"
#include "ai_settings_panel.h"

#include "core/io/json.h"
#include "modules/ai_agent/ai_agent_config.h"
#include "modules/ai_agent/ai_message.h"
#include "modules/ai_agent/context/ai_context_manager.h"

#include "editor/editor_interface.h"
#include "scene/gui/button.h"
#include "scene/gui/label.h"
#include "scene/gui/rich_text_label.h"
#include "scene/gui/separator.h"
#include "scene/gui/text_edit.h"
#include "scene/gui/dialogs.h"

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
	_render_transcript();

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

	approval_dialog = memnew(ConfirmationDialog);
	approval_dialog->set_title("Approve AI Tool Call");
	approval_dialog->get_ok_button()->set_text("Approve");
	approval_dialog->get_cancel_button()->set_text("Deny");
	approval_dialog->connect("confirmed", callable_mp(this, &AIChatPanel::_approve_pending_tool_call));
	approval_dialog->connect("canceled", callable_mp(this, &AIChatPanel::_deny_pending_tool_call));
	add_child(approval_dialog);
}

void AIChatPanel::_notification(int p_what) {
	if (p_what == NOTIFICATION_ENTER_TREE) {
		initialize_session();
	}
}

void AIChatPanel::set_settings_panel(AISettingsPanel *p_panel) {
	settings_panel = p_panel;
	if (settings_panel) {
		settings_panel->connect("config_changed", callable_mp(this, &AIChatPanel::_on_config_changed));
	}
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
	session->connect("tool_call_completed", callable_mp(this, &AIChatPanel::_on_tool_call_completed));
	session->connect("approval_required", callable_mp(this, &AIChatPanel::_on_approval_required));
	session->connect("error_occurred", callable_mp(this, &AIChatPanel::_on_error_occurred));
	session->connect("state_changed", callable_mp(this, &AIChatPanel::_on_session_state_changed));

	// Pass the initial configuration if available.
	if (settings_panel) {
		session->set_config(settings_panel->get_config());
	}
}

void AIChatPanel::_on_config_changed(const Ref<AIAgentConfig> &p_config) {
	if (session.is_valid()) {
		session->set_config(p_config);
	}
}

void AIChatPanel::_send_message() {
	String text = input_field->get_text().strip_edges();
	if (text.is_empty()) {
		return;
	}

	// Validate API key before attempting to send.
	if (session.is_valid() && session->get_config().is_valid()) {
		Ref<AIAgentConfig> cfg = session->get_config();
		if (cfg->get_api_key().is_empty() && cfg->get_provider_type() != AIAgentConfig::PROVIDER_LOCAL) {
			_append_message("System", "Please configure your API key in Settings before sending messages.", Color(1.0, 0.6, 0.2));
			return;
		}
	} else {
		_append_message("System", "AI session not configured. Open Settings and save your configuration.", Color(1.0, 0.6, 0.2));
		return;
	}

	// Display user message.
	_append_message("You", text, Color(0.4, 0.8, 1.0));

	// Clear input.
	input_field->set_text("");

	// Collect editor context and send with context.
	if (session.is_valid()) {
		AIContextManager *ctx_mgr = AIContextManager::get_singleton();
		if (ctx_mgr) {
			Dictionary context = ctx_mgr->collect_context_budgeted(
					AIContextManager::CONTEXT_SCENE | AIContextManager::CONTEXT_SCRIPTS | AIContextManager::CONTEXT_EDITOR_STATE,
					4000);
			session->send_message_with_context(text, context);
		} else {
			session->send_message(text);
		}
	}
}

void AIChatPanel::_clear_chat() {
	transcript.clear();
	active_assistant_entry = -1;
	_render_transcript();
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

void AIChatPanel::_approve_pending_tool_call() {
	if (session.is_valid() && !pending_approval_tool_call_id.is_empty()) {
		session->approve_tool_call(pending_approval_tool_call_id);
	}
	pending_approval_tool_call_id = "";
	pending_approval_tool_name = "";
	pending_approval_arguments.clear();
}

void AIChatPanel::_deny_pending_tool_call() {
	if (session.is_valid() && !pending_approval_tool_call_id.is_empty()) {
		session->deny_tool_call(pending_approval_tool_call_id, "User denied the tool call from the chat panel.");
	}
	pending_approval_tool_call_id = "";
	pending_approval_tool_name = "";
	pending_approval_arguments.clear();
}

void AIChatPanel::_on_message_received(const Ref<AIMessage> &p_message) {
	if (p_message.is_null()) {
		return;
	}

	if (p_message->get_content().is_empty() && p_message->has_tool_calls()) {
		if (active_assistant_entry != -1 && transcript[active_assistant_entry].content.is_empty()) {
			transcript.remove_at(active_assistant_entry);
			active_assistant_entry = -1;
			_render_transcript();
		}
		return;
	}

	if (active_assistant_entry != -1) {
		transcript.write[active_assistant_entry].content = p_message->get_content();
		_render_transcript();
		active_assistant_entry = -1;
	} else {
		_append_message("AI", p_message->get_content(), Color(0.6, 1.0, 0.6));
	}
}

void AIChatPanel::_on_stream_chunk(const String &p_chunk) {
	if (!p_chunk.is_empty()) {
		if (active_assistant_entry == -1) {
			_append_message("AI", p_chunk, Color(0.6, 1.0, 0.6));
			active_assistant_entry = transcript.size() - 1;
		} else {
			transcript.write[active_assistant_entry].content += p_chunk;
			_render_transcript();
		}
	}
}

void AIChatPanel::_on_tool_call_requested(const String &p_tool_name, const Dictionary &p_args, const String &p_tool_call_id) {
	String args_str;
	Array keys = p_args.keys();
	for (int i = 0; i < keys.size(); i++) {
		if (i > 0) {
			args_str += ", ";
		}
		args_str += String(keys[i]) + "=" + String(p_args[keys[i]]);
	}

	String content = p_tool_name + "(" + args_str + ")";
	if (!p_tool_call_id.is_empty()) {
		content += " [" + p_tool_call_id + "]";
	}
	_append_message("Tool", content, Color(1.0, 0.67, 0.0));
}

void AIChatPanel::_on_tool_call_completed(const String &p_tool_name, const Variant &p_result) {
	String result_text = p_result.get_type() == Variant::STRING ? String(p_result) : JSON::stringify(p_result);
	_append_message("Tool Result", p_tool_name + ": " + result_text, Color(0.95, 0.85, 0.45));
}

void AIChatPanel::_on_approval_required(const String &p_tool_name, const Dictionary &p_args, const String &p_tool_call_id) {
	pending_approval_tool_call_id = p_tool_call_id;
	pending_approval_tool_name = p_tool_name;
	pending_approval_arguments = p_args;
	_append_message("Approval", "Review required for tool call: " + p_tool_name, Color(1.0, 0.45, 0.25));

	String args_str = JSON::stringify(p_args, "  ");
	approval_dialog->set_text(vformat("Allow the AI to run '%s'?\n\nArguments:\n%s", p_tool_name, args_str));
	approval_dialog->popup_centered_clamped(Size2(520, 280));
}

void AIChatPanel::_on_error_occurred(const String &p_error) {
	if (active_assistant_entry != -1 && transcript[active_assistant_entry].content.is_empty()) {
		transcript.remove_at(active_assistant_entry);
		active_assistant_entry = -1;
	}
	_append_message("Error", p_error, Color(1.0, 0.27, 0.27));
}

void AIChatPanel::_on_session_state_changed(int p_state) {
	bool is_busy = (p_state != AIAgentSession::STATE_IDLE && p_state != AIAgentSession::STATE_ERROR);
	send_button->set_disabled(is_busy);
	cancel_button->set_visible(is_busy);

	if (p_state == AIAgentSession::STATE_WAITING_FOR_RESPONSE) {
		send_button->set_text("...");
		if (active_assistant_entry == -1) {
			_append_message("AI", "", Color(0.6, 1.0, 0.6));
			active_assistant_entry = transcript.size() - 1;
		}
	} else if (!is_busy) {
		send_button->set_text("Send");
		if (active_assistant_entry != -1 && transcript[active_assistant_entry].content.is_empty()) {
			transcript.remove_at(active_assistant_entry);
		}
		active_assistant_entry = -1;
		_render_transcript();
	}
}

String AIChatPanel::_escape_bbcode(const String &p_text) const {
	String escaped = p_text;
	escaped = escaped.replace("[", "[lb]");
	escaped = escaped.replace("]", "[rb]");
	return escaped;
}

void AIChatPanel::_render_transcript() {
	message_display->clear();
	if (transcript.is_empty()) {
		message_display->append_text("[color=#888888][i]Welcome to the Godoty AI Agent.[/i][/color]\n");
		message_display->append_text("[color=#888888][i]Configure your API key in Settings, then start chatting.[/i][/color]\n\n");
		return;
	}

	for (int i = 0; i < transcript.size(); i++) {
		const ChatEntry &entry = transcript[i];
		String hex = entry.color.to_html(false);
		message_display->append_text("[color=#" + hex + "][b]" + _escape_bbcode(entry.role) + ":[/b][/color] ");
		message_display->append_text(_escape_bbcode(entry.content) + "\n\n");
	}
}

void AIChatPanel::_append_message(const String &p_role, const String &p_content, const Color &p_color, bool p_merge_with_active) {
	if (p_merge_with_active && active_assistant_entry != -1) {
		transcript.write[active_assistant_entry].content += p_content;
	} else {
		ChatEntry entry;
		entry.role = p_role;
		entry.content = p_content;
		entry.color = p_color;
		transcript.push_back(entry);
	}
	_render_transcript();
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
