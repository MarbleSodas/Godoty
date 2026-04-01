/**************************************************************************/
/*  ai_chat_panel.h                                                       */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#ifdef TOOLS_ENABLED

#include "core/templates/hash_map.h"
#include "modules/ai_agent/ai_agent_mode.h"
#include "modules/ai_agent/ai_agent_session.h"
#include "scene/gui/box_container.h"
#include "scene/gui/container.h"
#include "scene/gui/control.h"

class RichTextLabel;
class TextureRect;
class TextEdit;
class Button;
class Label;
class MenuButton;
class PanelContainer;
class ScrollContainer;
class HSeparator;
class PopupMenu;
class Tween;
class AISettingsPanel;
class AIStreamPreview;

class AIChatPanel : public VBoxContainer {
	GDCLASS(AIChatPanel, VBoxContainer);

	struct TimelineEntry {
		enum Kind {
			KIND_USER,
			KIND_ASSISTANT,
			KIND_ACTIVITY,
			KIND_TOOL_CARD,
			KIND_SYSTEM,
			KIND_ERROR,
		};

		Kind kind = KIND_SYSTEM;
		String role;
		String title;
		String content;
		String secondary_text;
		String thinking_content;
		String footer_left;
		String footer_right;
		String tool_name;
		String tool_call_id;
		Dictionary arguments;
		bool thinking_phase_finished = false;
		bool is_pending = false;
		uint64_t started_msec = 0;
		uint64_t thinking_started_msec = 0;
		uint64_t accumulated_thinking_msec = 0;
		double thinking_duration_seconds = -1.0;
		double duration_seconds = -1.0;
		uint64_t first_visible_chunk_msec = 0;
		uint64_t last_stream_flush_msec = 0;
		bool stream_dirty = false;
		bool stream_should_autoscroll = false;
		String pending_visible_stream_delta;

		Control *root = nullptr;
		Control *body = nullptr;
		PanelContainer *panel = nullptr;
		PanelContainer *content_panel = nullptr;
		Label *title_label = nullptr;
		Label *secondary_label = nullptr;
		Label *thinking_log_label = nullptr;
		AIStreamPreview *stream_preview = nullptr;
		RichTextLabel *content_label = nullptr;
		RichTextLabel *details_label = nullptr;
		RichTextLabel *output_label = nullptr;
		HBoxContainer *inline_action_row = nullptr;
		Button *inline_plan_button = nullptr;
		HBoxContainer *footer_row = nullptr;
		Label *footer_left_label = nullptr;
		Label *footer_right_label = nullptr;
		bool can_execute_plan = false;
		Ref<Tween> insert_tween;
		Ref<Tween> remove_tween;
	};

	ScrollContainer *transcript_scroll = nullptr;
	Control *transcript_overlay = nullptr;
	VBoxContainer *timeline_list = nullptr;
	Button *scroll_to_latest_button = nullptr;
	Control *empty_state_wrap = nullptr;
	PanelContainer *empty_state_card = nullptr;
	TextureRect *empty_logo = nullptr;
	TextEdit *input_field = nullptr;
	MenuButton *mode_button = nullptr;
	MenuButton *model_button = nullptr;
	Button *send_button = nullptr;
	Button *chat_tab = nullptr;
	Button *settings_tab = nullptr;
	Button *cancel_button = nullptr;
	Button *approval_allow_button = nullptr;
	Button *approval_deny_button = nullptr;
	Button *approval_policy_ask_button = nullptr;
	Button *approval_policy_allow_button = nullptr;
	Control *composer_action_slot = nullptr;
	HBoxContainer *send_button_slot = nullptr;
	HBoxContainer *cancel_button_slot = nullptr;
	HBoxContainer *tab_bar = nullptr;
	PanelContainer *tab_shell = nullptr;
	VBoxContainer *chat_container = nullptr;
	PanelContainer *approval_card = nullptr;
	Label *approval_title_label = nullptr;
	RichTextLabel *approval_details_label = nullptr;
	PanelContainer *composer_card = nullptr;
	VBoxContainer *settings_container = nullptr;
	ScrollContainer *settings_scroll = nullptr;

	Ref<AIAgentSession> session;
	AISettingsPanel *settings_panel = nullptr;
	Vector<TimelineEntry> transcript;
	HashMap<String, int> tool_entry_indices;
	int active_assistant_entry = -1;
	uint64_t pending_assistant_started_msec = 0;
	int current_tab = 0;
	int input_min_lines = 1;
	int input_max_lines = 6;
	float input_line_height = 0.0f;
	bool action_slot_busy = false;
	bool transcript_autoscroll_enabled = true;
	bool transcript_scroll_updating = false;
	bool refreshing_model_menu = false;
	int latest_executable_plan_entry = -1;
	uint64_t last_runtime_state_refresh_msec = 0;
	String pending_approval_tool_call_id;
	String pending_approval_tool_name;
	Dictionary pending_approval_arguments;
	Ref<Tween> composer_action_tween;

	void _send_message();
	void _clear_chat();
	void _cancel_request();
	void _set_approval_policy(AIAgentConfig::ApprovalPolicy p_policy);
	void _approve_pending_tool_call();
	void _deny_pending_tool_call();
	void _on_execute_plan_pressed(int p_entry_index);
	void _set_mode(int p_mode);
	void _on_mode_menu_id_pressed(int p_id);
	void _on_model_menu_id_pressed(int p_id);
	void _on_mode_menu_about_to_popup();
	void _on_model_menu_about_to_popup();
	void _on_tab_selected(int p_tab);
	void _on_input_text_changed();
	void _refresh_theme_dependent_state();
	void _refresh_model_menu();

	// Signal handlers.
	void _on_message_received(const Ref<AIMessage> &p_message);
	void _on_stream_chunk(const Ref<AIMessage> &p_chunk);
	void _on_tool_call_requested(const String &p_tool_name, const Dictionary &p_args, const String &p_tool_call_id);
	void _on_tool_call_completed(const String &p_tool_name, const Variant &p_result, const String &p_tool_call_id);
	void _on_approval_required(const String &p_tool_name, const Dictionary &p_args, const String &p_tool_call_id);
	void _on_error_occurred(const String &p_error);
	void _on_session_state_changed(int p_state);
	void _on_config_changed(const Ref<AIAgentConfig> &p_config);
	void _on_thinking_state_changed(bool p_active);
	void _on_transcript_scroll_value_changed(double p_value);
	void _on_scroll_to_latest_pressed();

	String _escape_bbcode(const String &p_text) const;
	void _apply_theme();
	void _refresh_header_state();
	void _refresh_approval_section();
	void _render_transcript();
	void _rebuild_timeline();
	void _refresh_empty_state();
	void _create_entry_ui(int p_index, bool p_animate_in);
	void _animate_entry_in(int p_index);
	void _animate_entry_out(Control *p_wrapper, Control *p_body);
	void _set_control_height(float p_height, Control *p_control);
	void _clear_control_height(Control *p_control);
	void _set_control_opacity(float p_opacity, Control *p_control);
	void _start_entry_thinking(TimelineEntry &r_entry, uint64_t p_now);
	void _stop_entry_thinking(TimelineEntry &r_entry, uint64_t p_now);
	void _finalize_entry_thinking(TimelineEntry &r_entry, uint64_t p_now);
	double _get_entry_thinking_seconds(const TimelineEntry &p_entry, uint64_t p_now) const;
	void _update_action_slot_state(bool p_busy, bool p_animate);
	void _update_entry_visuals(int p_index);
	void _flush_active_stream_updates(bool p_force = false);
	void _flush_entry_stream_updates(int p_index, bool p_force = false);
	void _refresh_active_runtime_state();
	void _reset_entry_stream_preview(int p_index);
	void _finalize_entry_stream_display(int p_index);
	void _append_stream_preview_text(int p_index, const String &p_text);
	void _clear_executable_plan_entry();
	void _set_executable_plan_entry(int p_entry_index);
	void _apply_popup_theme(PopupMenu *p_popup);
	void _animate_popup_menu_open(PopupMenu *p_popup, Point2i p_target_position);
	bool _is_near_transcript_bottom() const;
	bool _should_autoscroll() const;
	void _maybe_autoscroll(Control *p_focus_control = nullptr);
	void _scroll_transcript_to_bottom();
	void _set_transcript_autoscroll_enabled(bool p_enabled, bool p_scroll_now = false);
	void _refresh_scroll_to_latest_button();
	void _remove_entry(int p_index);
	int _add_user_entry(const String &p_text);
	int _ensure_assistant_entry(bool p_streaming = true);
	int _add_activity_entry(TimelineEntry::Kind p_kind, const String &p_title, const String &p_secondary = "", const String &p_tool_name = "", const String &p_tool_call_id = "");
	int _add_tool_card_entry(const String &p_tool_name, const Dictionary &p_args, const String &p_tool_call_id);
	void _finalize_active_assistant_entry(const Ref<AIMessage> &p_message);
	String _humanize_tool_name(const String &p_tool_name) const;
	String _format_tool_arguments(const Dictionary &p_args) const;
	String _format_tool_result(const Variant &p_result) const;
	String _summarize_tool_result(const Variant &p_result) const;
	String _primary_tool_target(const Dictionary &p_args) const;
	String _tool_activity_title(const String &p_tool_name, const Dictionary &p_args) const;
	bool _tool_prefers_activity_row(const String &p_tool_name) const;
	void _input_gui_input(const Ref<InputEvent> &p_event);
	void _position_menu_popup_above(MenuButton *p_button);
	void _update_tab_visibility();
	void _update_input_height();
	void _restore_transcript_from_session_history();

protected:
	static void _bind_methods();
	void _notification(int p_what);

public:
	void set_settings_panel(AISettingsPanel *p_panel);
	void initialize_session();

	AIChatPanel();
};

#endif // TOOLS_ENABLED
