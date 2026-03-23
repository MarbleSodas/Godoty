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
#include "core/math/math_funcs.h"
#include "core/os/os.h"
#include "modules/ai_agent/ai_agent_config.h"
#include "modules/ai_agent/ai_message.h"

#include "editor/editor_string_names.h"
#include "editor/settings/editor_settings.h"
#include "editor/themes/editor_scale.h"
#include "scene/animation/tween.h"
#include "scene/gui/button.h"
#include "scene/gui/center_container.h"
#include "scene/gui/dialogs.h"
#include "scene/gui/label.h"
#include "scene/gui/margin_container.h"
#include "scene/gui/menu_button.h"
#include "scene/gui/panel_container.h"
#include "scene/gui/popup_menu.h"
#include "scene/gui/rich_text_label.h"
#include "scene/gui/scroll_bar.h"
#include "scene/gui/scroll_container.h"
#include "scene/gui/separator.h"
#include "scene/gui/text_edit.h"
#include "scene/resources/style_box_flat.h"
#include "scene/resources/style_box_line.h"
#include "scene/resources/text_paragraph.h"
#include "servers/text/text_server.h"

class AIStreamPreview : public Control {
	GDCLASS(AIStreamPreview, Control);

	Ref<TextParagraph> paragraph;
	String preview_text;
	Ref<Font> preview_font;
	int preview_font_size = 0;
	float preview_line_spacing = 0.0f;
	Color preview_color = Color(1, 1, 1, 1);
	float preview_width = -1.0f;
	int animated_start = -1;
	uint64_t animated_started_msec = 0;

	static constexpr double REVEAL_DURATION = 0.16;
	static constexpr float REVEAL_OFFSET_Y = 4.0f;

	void _ensure_paragraph() {
		if (paragraph.is_null()) {
			paragraph.instantiate();
			paragraph->set_alignment(HORIZONTAL_ALIGNMENT_LEFT);
			paragraph->set_direction(TextServer::DIRECTION_AUTO);
			paragraph->set_orientation(TextServer::ORIENTATION_HORIZONTAL);
			paragraph->set_break_flags(TextServer::BREAK_WORD_BOUND | TextServer::BREAK_MANDATORY);
		}
	}

	void _rebuild_paragraph() {
		_ensure_paragraph();
		paragraph->clear();
		paragraph->set_width(preview_width);
		paragraph->set_line_spacing(preview_line_spacing);
		if (preview_font.is_valid() && !preview_text.is_empty()) {
			paragraph->add_string(preview_text, preview_font, preview_font_size);
		}
		update_minimum_size();
		queue_redraw();
	}

	double _get_reveal_progress() const {
		if (animated_start < 0 || animated_start >= preview_text.length() || animated_started_msec == 0) {
			return 1.0;
		}
		const uint64_t now = OS::get_singleton()->get_ticks_msec();
		const double elapsed = (double)(now - animated_started_msec) / 1000.0;
		return CLAMP(elapsed / REVEAL_DURATION, 0.0, 1.0);
	}

	void _stop_reveal_if_complete() {
		if (_get_reveal_progress() < 1.0) {
			return;
		}
		animated_start = -1;
		animated_started_msec = 0;
		set_process_internal(false);
	}

protected:
	static void _bind_methods() {}

	void _notification(int p_what) {
		switch (p_what) {
			case NOTIFICATION_DRAW: {
				if (paragraph.is_null() || preview_font.is_null() || preview_text.is_empty()) {
					return;
				}

				const RID canvas = get_canvas_item();
				const int line_count = paragraph->get_line_count();
				const double progress = _get_reveal_progress();
				const double eased = 1.0 - Math::pow(1.0 - progress, 3.0);
				const float animated_alpha = (float)eased;
				const float animated_offset = (float)Math::round((1.0 - eased) * REVEAL_OFFSET_Y * EDSCALE);
				float line_offset_y = 0.0f;

				for (int line = 0; line < line_count; line++) {
					const float ascent = paragraph->get_line_ascent(line);
					const float descent = paragraph->get_line_descent(line);
					const float baseline_y = line_offset_y + ascent;
					const RID line_rid = paragraph->get_line_rid(line);
					const Vector2i line_range = paragraph->get_line_range(line);
					const Vector2 base_pos(0.0f, baseline_y);

					if (animated_start < 0 || animated_start <= line_range.x) {
						Color draw_color = preview_color;
						if (animated_start >= 0) {
							draw_color.a *= animated_alpha;
						}
						const Vector2 draw_pos = animated_start < 0 ? base_pos : base_pos + Vector2(0.0f, animated_offset);
						TS->shaped_text_draw(line_rid, canvas, draw_pos, -1.0, -1.0, draw_color);
					} else if (animated_start >= line_range.y) {
						TS->shaped_text_draw(line_rid, canvas, base_pos, -1.0, -1.0, preview_color);
					} else {
						const CaretInfo caret = TS->shaped_text_get_carets(line_rid, animated_start);
						const double split_x = MAX(0.0, (double)caret.l_caret.position.x);
						TS->shaped_text_draw(line_rid, canvas, base_pos, -1.0, split_x, preview_color);
						Color animated_color = preview_color;
						animated_color.a *= animated_alpha;
						TS->shaped_text_draw(line_rid, canvas, base_pos + Vector2(0.0f, animated_offset), split_x, -1.0, animated_color);
					}

					line_offset_y += ascent + descent;
					if (line < line_count - 1) {
						line_offset_y += preview_line_spacing;
					}
				}
			} break;

			case NOTIFICATION_RESIZED: {
				const float next_width = MAX(1.0f, get_size().x);
				if (!Math::is_equal_approx(next_width, preview_width)) {
					preview_width = next_width;
					_rebuild_paragraph();
				}
			} break;

			case NOTIFICATION_INTERNAL_PROCESS: {
				if (animated_start < 0) {
					set_process_internal(false);
					return;
				}
				queue_redraw();
				_stop_reveal_if_complete();
			} break;
		}
	}

public:
	void configure(const Ref<Font> &p_font, int p_font_size, float p_line_spacing, const Color &p_color) {
		const bool font_changed = preview_font != p_font;
		const bool size_changed = preview_font_size != p_font_size;
		const bool spacing_changed = !Math::is_equal_approx(preview_line_spacing, p_line_spacing);
		const bool color_changed = preview_color != p_color;
		preview_font = p_font;
		preview_font_size = p_font_size;
		preview_line_spacing = p_line_spacing;
		preview_color = p_color;
		if (font_changed || size_changed || spacing_changed) {
			_rebuild_paragraph();
		} else if (color_changed) {
			queue_redraw();
		}
	}

	void append_preview_text(const String &p_text) {
		if (p_text.is_empty()) {
			return;
		}

		const int previous_length = preview_text.length();
		preview_text += p_text;
		animated_start = previous_length;
		animated_started_msec = OS::get_singleton()->get_ticks_msec();

		_ensure_paragraph();
		paragraph->set_width(preview_width);
		paragraph->set_line_spacing(preview_line_spacing);
		if (preview_font.is_valid()) {
			paragraph->add_string(p_text, preview_font, preview_font_size);
		} else {
			_rebuild_paragraph();
		}
		update_minimum_size();
		queue_redraw();
		set_process_internal(true);
	}

	void clear_preview() {
		preview_text = "";
		animated_start = -1;
		animated_started_msec = 0;
		set_process_internal(false);
		_rebuild_paragraph();
	}

	bool has_content() const {
		return !preview_text.is_empty();
	}

	Size2 get_minimum_size() const override {
		if (paragraph.is_null() || preview_text.is_empty()) {
			return Size2();
		}
		return paragraph->get_size();
	}

	AIStreamPreview() {
		set_mouse_filter(MOUSE_FILTER_IGNORE);
		set_h_size_flags(SIZE_EXPAND_FILL);
	}
};

namespace {

static const char *AI_SETTING_APPROVAL_POLICY = "_ai_agent/approval_policy";

constexpr double ENTRY_REVEAL_DURATION = 0.18;
constexpr double ENTRY_FADE_DURATION = 0.14;
constexpr uint64_t STREAM_WARMUP_MSEC = 90;
constexpr uint64_t STREAM_FLUSH_INTERVAL_MSEC = 33;
constexpr uint64_t RUNTIME_REFRESH_INTERVAL_MSEC = 90;
constexpr double STREAM_TARGET_CHARACTERS_PER_SECOND = 90.0;
constexpr int STREAM_MIN_CHARACTERS_PER_FLUSH = 6;
constexpr int STREAM_MAX_CHARACTERS_PER_FLUSH = 24;
constexpr uint64_t STREAM_CATCH_UP_WINDOW_MSEC = 250;
constexpr int POPUP_REVEAL_OFFSET_Y = 6;

Ref<Texture2D> _get_ai_editor_icon(Control *p_control, const String &p_icon_name) {
	if (!p_control || p_icon_name.is_empty()) {
		return Ref<Texture2D>();
	}
	return p_control->get_theme_icon(p_icon_name, EditorStringName(EditorIcons));
}

String _seconds_label(double p_seconds) {
	if (p_seconds < 0.05) {
		return "<1s";
	}
	return vformat("%ds", MAX(1, (int)Math::round(p_seconds)));
}

bool _is_stream_boundary(const String &p_character) {
	return p_character == "\n" ||
			p_character == " " ||
			p_character == "\t" ||
			p_character == "." ||
			p_character == "," ||
			p_character == "!" ||
			p_character == "?" ||
			p_character == ":" ||
			p_character == ";" ||
			p_character == ")" ||
			p_character == "]" ||
			p_character == "}";
}

String _take_stream_slice(String &r_buffer, int p_preferred_count) {
	if (r_buffer.is_empty()) {
		return "";
	}

	const int length = r_buffer.length();
	const int preferred = CLAMP(p_preferred_count, STREAM_MIN_CHARACTERS_PER_FLUSH, MAX(STREAM_MIN_CHARACTERS_PER_FLUSH, length));
	int slice_end = MIN(length, preferred);
	if (length <= STREAM_MIN_CHARACTERS_PER_FLUSH) {
		slice_end = length;
	} else {
		const int min_break = MIN(length, STREAM_MIN_CHARACTERS_PER_FLUSH);
		for (int i = slice_end - 1; i >= min_break - 1; i--) {
			if (_is_stream_boundary(r_buffer.substr(i, 1))) {
				slice_end = i + 1;
				break;
			}
		}
	}

	String slice = r_buffer.substr(0, slice_end);
	r_buffer = r_buffer.substr(slice_end);
	return slice;
}

} // namespace

void AIChatPanel::_bind_methods() {
}

AIChatPanel::AIChatPanel() {
	set_name("AIChat");
	set_h_size_flags(SIZE_EXPAND_FILL);
	set_v_size_flags(SIZE_EXPAND_FILL);
	set_clip_contents(true);
	set_process(true);
	add_theme_constant_override("separation", 10 * EDSCALE);

	tab_bar = memnew(HBoxContainer);
	tab_bar->set_h_size_flags(SIZE_EXPAND_FILL);
	tab_bar->add_theme_constant_override("separation", 4 * EDSCALE);
	add_child(tab_bar);

	tab_shell = memnew(PanelContainer);
	tab_bar->add_child(tab_shell);

	HBoxContainer *tabs = memnew(HBoxContainer);
	tabs->add_theme_constant_override("separation", 0);
	tab_shell->add_child(tabs);

	chat_tab = memnew(Button);
	chat_tab->set_text("Chat");
	chat_tab->set_toggle_mode(true);
	chat_tab->set_pressed(true);
	chat_tab->set_tooltip_text("Show the AI chat");
	chat_tab->connect("pressed", callable_mp(this, &AIChatPanel::_on_tab_selected).bind(0));
	tabs->add_child(chat_tab);

	settings_tab = memnew(Button);
	settings_tab->set_text("Settings");
	settings_tab->set_toggle_mode(true);
	settings_tab->set_tooltip_text("Configure the AI provider");
	settings_tab->connect("pressed", callable_mp(this, &AIChatPanel::_on_tab_selected).bind(1));
	tabs->add_child(settings_tab);

	tab_bar->add_spacer();

	chat_container = memnew(VBoxContainer);
	chat_container->set_h_size_flags(SIZE_EXPAND_FILL);
	chat_container->set_v_size_flags(SIZE_EXPAND_FILL);
	chat_container->add_theme_constant_override("separation", 10 * EDSCALE);
	add_child(chat_container);

	MarginContainer *transcript_margin = memnew(MarginContainer);
	transcript_margin->set_h_size_flags(SIZE_EXPAND_FILL);
	transcript_margin->set_v_size_flags(SIZE_EXPAND_FILL);
	transcript_margin->add_theme_constant_override("margin_left", 12 * EDSCALE);
	transcript_margin->add_theme_constant_override("margin_top", 6 * EDSCALE);
	transcript_margin->add_theme_constant_override("margin_right", 12 * EDSCALE);
	transcript_margin->add_theme_constant_override("margin_bottom", 6 * EDSCALE);
	chat_container->add_child(transcript_margin);

	Control *transcript_surface = memnew(Control);
	transcript_surface->set_h_size_flags(SIZE_EXPAND_FILL);
	transcript_surface->set_v_size_flags(SIZE_EXPAND_FILL);
	transcript_surface->set_clip_contents(false);
	transcript_margin->add_child(transcript_surface);

	transcript_scroll = memnew(ScrollContainer);
	transcript_scroll->set_anchors_and_offsets_preset(Control::PRESET_FULL_RECT);
	transcript_scroll->set_horizontal_scroll_mode(ScrollContainer::SCROLL_MODE_DISABLED);
	transcript_surface->add_child(transcript_scroll);

	timeline_list = memnew(VBoxContainer);
	timeline_list->set_h_size_flags(SIZE_EXPAND_FILL);
	timeline_list->set_v_size_flags(SIZE_EXPAND_FILL);
	timeline_list->add_theme_constant_override("separation", 8 * EDSCALE);
	transcript_scroll->add_child(timeline_list);

	transcript_overlay = memnew(Control);
	transcript_overlay->set_anchors_and_offsets_preset(Control::PRESET_FULL_RECT);
	transcript_overlay->set_mouse_filter(Control::MOUSE_FILTER_IGNORE);
	transcript_surface->add_child(transcript_overlay);

	if (transcript_scroll->get_v_scroll_bar()) {
		transcript_scroll->get_v_scroll_bar()->connect("value_changed", callable_mp(this, &AIChatPanel::_on_transcript_scroll_value_changed));
	}

	scroll_to_latest_button = memnew(Button);
	scroll_to_latest_button->set_text("Latest");
	scroll_to_latest_button->set_visible(false);
	scroll_to_latest_button->set_mouse_filter(Control::MOUSE_FILTER_STOP);
	scroll_to_latest_button->set_tooltip_text("Jump to the bottom of the transcript and resume auto-scroll.");
	scroll_to_latest_button->set_anchors_and_offsets_preset(Control::PRESET_BOTTOM_RIGHT);
	scroll_to_latest_button->set_anchor(SIDE_LEFT, 1.0);
	scroll_to_latest_button->set_anchor(SIDE_TOP, 1.0);
	scroll_to_latest_button->set_anchor(SIDE_RIGHT, 1.0);
	scroll_to_latest_button->set_anchor(SIDE_BOTTOM, 1.0);
	scroll_to_latest_button->set_offset(SIDE_LEFT, -(92 * EDSCALE));
	scroll_to_latest_button->set_offset(SIDE_TOP, -(40 * EDSCALE));
	scroll_to_latest_button->set_offset(SIDE_RIGHT, -(8 * EDSCALE));
	scroll_to_latest_button->set_offset(SIDE_BOTTOM, -(8 * EDSCALE));
	scroll_to_latest_button->connect("pressed", callable_mp(this, &AIChatPanel::_on_scroll_to_latest_pressed));
	transcript_overlay->add_child(scroll_to_latest_button);

	empty_state_wrap = memnew(CenterContainer);
	empty_state_wrap->set_h_size_flags(SIZE_EXPAND_FILL);
	empty_state_wrap->set_v_size_flags(SIZE_EXPAND_FILL);
	timeline_list->add_child(empty_state_wrap);

	empty_state_card = memnew(PanelContainer);
	empty_state_card->set_h_size_flags(SIZE_SHRINK_CENTER);
	empty_state_card->set_custom_minimum_size(Size2(340 * EDSCALE, 0));
	empty_state_wrap->add_child(empty_state_card);

	MarginContainer *empty_state_margin = memnew(MarginContainer);
	empty_state_margin->add_theme_constant_override("margin_left", 18 * EDSCALE);
	empty_state_margin->add_theme_constant_override("margin_top", 16 * EDSCALE);
	empty_state_margin->add_theme_constant_override("margin_right", 18 * EDSCALE);
	empty_state_margin->add_theme_constant_override("margin_bottom", 16 * EDSCALE);
	empty_state_card->add_child(empty_state_margin);

	empty_state = memnew(RichTextLabel);
	empty_state->set_h_size_flags(SIZE_EXPAND_FILL);
	empty_state->set_custom_minimum_size(Size2(340 * EDSCALE, 56 * EDSCALE));
	empty_state->set_fit_content(true);
	empty_state->set_scroll_active(false);
	empty_state->set_selection_enabled(false);
	empty_state->set_horizontal_alignment(HORIZONTAL_ALIGNMENT_CENTER);
	empty_state->set_autowrap_mode(TextServer::AUTOWRAP_WORD_SMART);
	empty_state->set_use_bbcode(true);
	empty_state_margin->add_child(empty_state);

	approval_card = memnew(PanelContainer);
	approval_card->set_h_size_flags(SIZE_EXPAND_FILL);
	approval_card->set_visible(false);
	chat_container->add_child(approval_card);

	MarginContainer *approval_margin = memnew(MarginContainer);
	approval_margin->add_theme_constant_override("margin_left", 14 * EDSCALE);
	approval_margin->add_theme_constant_override("margin_top", 12 * EDSCALE);
	approval_margin->add_theme_constant_override("margin_right", 14 * EDSCALE);
	approval_margin->add_theme_constant_override("margin_bottom", 12 * EDSCALE);
	approval_card->add_child(approval_margin);

	VBoxContainer *approval_content = memnew(VBoxContainer);
	approval_content->add_theme_constant_override("separation", 8 * EDSCALE);
	approval_margin->add_child(approval_content);

	approval_title_label = memnew(Label);
	approval_title_label->set_text("Approval required");
	approval_content->add_child(approval_title_label);

	approval_details_label = memnew(RichTextLabel);
	approval_details_label->set_h_size_flags(SIZE_EXPAND_FILL);
	approval_details_label->set_fit_content(true);
	approval_details_label->set_scroll_active(false);
	approval_details_label->set_selection_enabled(true);
	approval_details_label->set_use_bbcode(true);
	approval_details_label->set_autowrap_mode(TextServer::AUTOWRAP_WORD_SMART);
	approval_content->add_child(approval_details_label);

	HBoxContainer *approval_policy_row = memnew(HBoxContainer);
	approval_policy_row->set_h_size_flags(SIZE_EXPAND_FILL);
	approval_policy_row->add_theme_constant_override("separation", 6 * EDSCALE);
	approval_content->add_child(approval_policy_row);

	Label *approval_policy_label = memnew(Label);
	approval_policy_label->set_text("Approvals");
	approval_policy_row->add_child(approval_policy_label);

	approval_policy_row->add_spacer();

	approval_policy_ask_button = memnew(Button);
	approval_policy_ask_button->set_text("Ask");
	approval_policy_ask_button->set_toggle_mode(true);
	approval_policy_ask_button->connect("pressed", callable_mp(this, &AIChatPanel::_set_approval_policy).bind(AIAgentConfig::APPROVAL_ASK));
	approval_policy_row->add_child(approval_policy_ask_button);

	approval_policy_allow_button = memnew(Button);
	approval_policy_allow_button->set_text("Always Allow");
	approval_policy_allow_button->set_toggle_mode(true);
	approval_policy_allow_button->connect("pressed", callable_mp(this, &AIChatPanel::_set_approval_policy).bind(AIAgentConfig::APPROVAL_ALWAYS_ALLOW));
	approval_policy_row->add_child(approval_policy_allow_button);

	HBoxContainer *approval_action_row = memnew(HBoxContainer);
	approval_action_row->set_h_size_flags(SIZE_EXPAND_FILL);
	approval_action_row->add_theme_constant_override("separation", 8 * EDSCALE);
	approval_content->add_child(approval_action_row);

	approval_action_row->add_spacer();

	approval_deny_button = memnew(Button);
	approval_deny_button->set_text("Deny");
	approval_deny_button->connect("pressed", callable_mp(this, &AIChatPanel::_deny_pending_tool_call));
	approval_action_row->add_child(approval_deny_button);

	approval_allow_button = memnew(Button);
	approval_allow_button->set_text("Allow");
	approval_allow_button->connect("pressed", callable_mp(this, &AIChatPanel::_approve_pending_tool_call));
	approval_action_row->add_child(approval_allow_button);

	composer_card = memnew(PanelContainer);
	composer_card->set_h_size_flags(SIZE_EXPAND_FILL);
	chat_container->add_child(composer_card);

	MarginContainer *composer_margin = memnew(MarginContainer);
	composer_margin->add_theme_constant_override("margin_left", 12 * EDSCALE);
	composer_margin->add_theme_constant_override("margin_top", 10 * EDSCALE);
	composer_margin->add_theme_constant_override("margin_right", 12 * EDSCALE);
	composer_margin->add_theme_constant_override("margin_bottom", 10 * EDSCALE);
	composer_card->add_child(composer_margin);

	VBoxContainer *composer_content = memnew(VBoxContainer);
	composer_content->add_theme_constant_override("separation", 8 * EDSCALE);
	composer_margin->add_child(composer_content);

	input_field = memnew(TextEdit);
	input_field->set_h_size_flags(SIZE_EXPAND_FILL);
	input_field->set_custom_minimum_size(Size2(0, 40 * EDSCALE));
	input_field->set_placeholder("Ask AI...");
	input_field->set_tooltip_text("");
	input_field->set_line_wrapping_mode(TextEdit::LineWrappingMode::LINE_WRAPPING_BOUNDARY);
	input_field->set_highlight_current_line(false);
	input_field->set_draw_minimap(false);
	input_field->connect("gui_input", callable_mp(this, &AIChatPanel::_input_gui_input));
	input_field->connect("text_changed", callable_mp(this, &AIChatPanel::_on_input_text_changed));
	composer_content->add_child(input_field);

	HBoxContainer *footer_row = memnew(HBoxContainer);
	footer_row->set_h_size_flags(SIZE_EXPAND_FILL);
	footer_row->add_theme_constant_override("separation", 8 * EDSCALE);
	composer_content->add_child(footer_row);

	HBoxContainer *selector_row = memnew(HBoxContainer);
	selector_row->set_h_size_flags(SIZE_SHRINK_BEGIN);
	selector_row->add_theme_constant_override("separation", (int)Math::round(6.0f * EDSCALE));
	footer_row->add_child(selector_row);

	mode_button = memnew(MenuButton);
	mode_button->set_theme_type_variation("FlatMenuButton");
	mode_button->set_text("Ask");
	mode_button->set_expand_icon(false);
	mode_button->set_clip_text(true);
	mode_button->set_text_alignment(HORIZONTAL_ALIGNMENT_LEFT);
	mode_button->set_icon_alignment(HORIZONTAL_ALIGNMENT_LEFT);
	mode_button->set_text_overrun_behavior(TextServer::OVERRUN_TRIM_ELLIPSIS);
	mode_button->set_switch_on_hover(false);
	mode_button->set_tooltip_text("Select mode");
	mode_button->get_popup()->connect("id_pressed", callable_mp(this, &AIChatPanel::_on_mode_menu_id_pressed));
	mode_button->get_popup()->connect("about_to_popup", callable_mp(this, &AIChatPanel::_on_mode_menu_about_to_popup));
	selector_row->add_child(mode_button);

	model_button = memnew(MenuButton);
	model_button->set_theme_type_variation("FlatMenuButton");
	model_button->set_text("Model");
	model_button->set_expand_icon(false);
	model_button->set_clip_text(true);
	model_button->set_text_alignment(HORIZONTAL_ALIGNMENT_LEFT);
	model_button->set_icon_alignment(HORIZONTAL_ALIGNMENT_LEFT);
	model_button->set_text_overrun_behavior(TextServer::OVERRUN_TRIM_ELLIPSIS);
	model_button->set_switch_on_hover(false);
	model_button->set_tooltip_text("Select model");
	model_button->get_popup()->connect("id_pressed", callable_mp(this, &AIChatPanel::_on_model_menu_id_pressed));
	model_button->get_popup()->connect("about_to_popup", callable_mp(this, &AIChatPanel::_on_model_menu_about_to_popup));
	selector_row->add_child(model_button);

	footer_row->add_spacer();

	composer_action_slot = memnew(Control);
	composer_action_slot->set_custom_minimum_size(Size2(36 * EDSCALE, 36 * EDSCALE));
	composer_action_slot->set_h_size_flags(SIZE_SHRINK_END);
	composer_action_slot->set_v_size_flags(SIZE_SHRINK_CENTER);
	footer_row->add_child(composer_action_slot);

	send_button_slot = memnew(HBoxContainer);
	send_button_slot->set_anchors_and_offsets_preset(Control::PRESET_FULL_RECT);
	send_button_slot->add_theme_constant_override("separation", 0);
	composer_action_slot->add_child(send_button_slot);
	send_button_slot->add_spacer();

	send_button = memnew(Button);
	send_button->set_text("");
	send_button->set_custom_minimum_size(Size2(36 * EDSCALE, 36 * EDSCALE));
	send_button->set_text_alignment(HORIZONTAL_ALIGNMENT_CENTER);
	send_button->set_icon_alignment(HORIZONTAL_ALIGNMENT_CENTER);
	send_button->set_vertical_icon_alignment(VERTICAL_ALIGNMENT_CENTER);
	send_button->set_tooltip_text("Send message. Press Enter to send, or Shift+Enter for a new line.");
	send_button->connect("pressed", callable_mp(this, &AIChatPanel::_send_message));
	send_button_slot->add_child(send_button);

	cancel_button_slot = memnew(HBoxContainer);
	cancel_button_slot->set_anchors_and_offsets_preset(Control::PRESET_FULL_RECT);
	cancel_button_slot->add_theme_constant_override("separation", 0);
	composer_action_slot->add_child(cancel_button_slot);
	cancel_button_slot->add_spacer();

	cancel_button = memnew(Button);
	cancel_button->set_text("");
	cancel_button->set_text_alignment(HORIZONTAL_ALIGNMENT_CENTER);
	cancel_button->set_icon_alignment(HORIZONTAL_ALIGNMENT_CENTER);
	cancel_button->set_vertical_icon_alignment(VERTICAL_ALIGNMENT_CENTER);
	cancel_button->set_tooltip_text("Stop current request");
	cancel_button->connect("pressed", callable_mp(this, &AIChatPanel::_cancel_request));
	cancel_button_slot->add_child(cancel_button);

	settings_container = memnew(VBoxContainer);
	settings_container->set_h_size_flags(SIZE_EXPAND_FILL);
	settings_container->set_v_size_flags(SIZE_EXPAND_FILL);
	settings_container->set_visible(false);
	add_child(settings_container);

	settings_scroll = memnew(ScrollContainer);
	settings_scroll->set_h_size_flags(SIZE_EXPAND_FILL);
	settings_scroll->set_v_size_flags(SIZE_EXPAND_FILL);
	settings_scroll->set_horizontal_scroll_mode(ScrollContainer::SCROLL_MODE_DISABLED);
	settings_container->add_child(settings_scroll);
}

void AIChatPanel::_notification(int p_what) {
	if (p_what == NOTIFICATION_POSTINITIALIZE) {
		_refresh_theme_dependent_state();
		_update_tab_visibility();
	} else if (p_what == NOTIFICATION_ENTER_TREE) {
		initialize_session();
	} else if (p_what == NOTIFICATION_THEME_CHANGED) {
		_refresh_theme_dependent_state();
	} else if (p_what == NOTIFICATION_RESIZED) {
		_update_input_height();
	} else if (p_what == NOTIFICATION_PROCESS) {
		_flush_active_stream_updates(false);
		_refresh_active_runtime_state();
		if (current_tab == 0 && transcript_autoscroll_enabled && !transcript.is_empty()) {
			_scroll_transcript_to_bottom();
		}
	}
}

void AIChatPanel::_refresh_theme_dependent_state() {
	if (send_button) {
		send_button->set_button_icon(get_theme_icon(SNAME("ArrowUp"), EditorStringName(EditorIcons)));
	}
	if (cancel_button) {
		cancel_button->set_button_icon(get_theme_icon(SNAME("Stop"), EditorStringName(EditorIcons)));
	}

	_apply_theme();
	_update_input_height();
	for (int i = 0; i < transcript.size(); i++) {
		_update_entry_visuals(i);
	}
	_refresh_empty_state();
	_refresh_header_state();
	_update_action_slot_state(action_slot_busy, false);
	_refresh_scroll_to_latest_button();
}

void AIChatPanel::set_settings_panel(AISettingsPanel *p_panel) {
	settings_panel = p_panel;
	if (settings_panel) {
		Callable config_changed = callable_mp(this, &AIChatPanel::_on_config_changed);
		if (!settings_panel->is_connected("config_changed", config_changed)) {
			settings_panel->connect("config_changed", config_changed);
		}
		Callable suggestions_changed = callable_mp(this, &AIChatPanel::_refresh_model_menu);
		if (!settings_panel->is_connected("model_suggestions_changed", suggestions_changed)) {
			settings_panel->connect("model_suggestions_changed", suggestions_changed);
		}
		if (settings_panel->get_parent() != settings_scroll) {
			if (settings_panel->get_parent()) {
				settings_panel->get_parent()->remove_child(settings_panel);
			}
			settings_scroll->add_child(settings_panel);
		}
		settings_panel->set_visible(true);
	}
	_refresh_header_state();
	_refresh_empty_state();
	_refresh_approval_section();
	_update_tab_visibility();
}

void AIChatPanel::_on_tab_selected(int p_tab) {
	current_tab = p_tab;
	_update_tab_visibility();
}

void AIChatPanel::_update_tab_visibility() {
	const bool is_chat = current_tab == 0;
	const bool is_settings = current_tab == 1;

	if (chat_tab) {
		chat_tab->set_pressed(is_chat);
	}
	if (settings_tab) {
		settings_tab->set_pressed(is_settings);
	}
	if (chat_container) {
		chat_container->set_visible(is_chat);
	}
	if (settings_container) {
		settings_container->set_visible(is_settings && settings_panel != nullptr);
	}
	_refresh_scroll_to_latest_button();
	_apply_theme();
	if (is_chat && input_field && is_inside_tree()) {
		input_field->grab_focus();
	}
}

void AIChatPanel::_on_input_text_changed() {
	_update_input_height();
}

void AIChatPanel::_update_input_height() {
	if (!input_field) {
		return;
	}

	input_line_height = MAX(1.0f, (float)input_field->get_line_height());

	const int visible_lines = CLAMP(MAX(1, input_field->get_total_visible_line_count()), input_min_lines, input_max_lines);
	const int vertical_padding = (int)Math::round(12.0f * EDSCALE);
	const int desired_height = (int)Math::round((visible_lines * input_line_height) + vertical_padding);
	input_field->set_custom_minimum_size(Size2(0, desired_height));
}

void AIChatPanel::_apply_theme() {
	const Color accent = get_theme_color("accent_color", EditorStringName(Editor));
	const Color strong = get_theme_color("font_color", EditorStringName(Editor));
	const Color muted = get_theme_color("font_placeholder_color", EditorStringName(Editor));
	const Color background = get_theme_color("dark_color_1", EditorStringName(Editor));
	const Color surface = get_theme_color("dark_color_2", EditorStringName(Editor));
	const Color shell_fill = background.lerp(surface, 0.42f);
	const Color shell_border = strong.lerp(surface, 0.92f);
	const Color shell_hover = surface.lerp(accent, 0.05f);
	const Color shell_active = surface.lerp(accent, 0.11f);
	const Color chip_fill = background.lerp(surface, 0.28f);
	const Color chip_border = strong.lerp(surface, 0.91f);
	const Color chip_hover = background.lerp(surface, 0.35f);
	const Color chip_active = background.lerp(surface, 0.42f);
	const Color chip_active_border = accent.lerp(surface, 0.45f);
	const Color approval_fill = background.lerp(surface, 0.28f);
	const Color approval_border = accent.lerp(surface, 0.5f);
	const Color composer_fill = background.lerp(surface, 0.24f);
	const Color composer_border = strong.lerp(surface, 0.92f);
	const Color send_fill = background.lerp(accent, 0.16f);
	const Color send_hover = background.lerp(accent, 0.23f);
	const int thin_border = 1;
	const int medium_radius = (int)Math::round(9.0f * EDSCALE);
	const int large_radius = (int)Math::round(12.0f * EDSCALE);
	const int chip_padding_h = (int)Math::round(10.0f * EDSCALE);
	const int chip_padding_v = (int)Math::round(5.0f * EDSCALE);

	auto make_surface_style = [&](const Color &p_fill, const Color &p_border, int p_radius, int p_padding_h = 0, int p_padding_v = 0) {
		Ref<StyleBoxFlat> style;
		style.instantiate();
		style->set_bg_color(p_fill);
		style->set_border_color(p_border);
		style->set_border_width_all(thin_border);
		style->set_corner_radius_all(p_radius);
		style->set_content_margin(SIDE_LEFT, p_padding_h);
		style->set_content_margin(SIDE_TOP, p_padding_v);
		style->set_content_margin(SIDE_RIGHT, p_padding_h);
		style->set_content_margin(SIDE_BOTTOM, p_padding_v);
		return style;
	};

	if (tab_shell) {
		tab_shell->add_theme_style_override("panel", make_surface_style(shell_fill, shell_border, medium_radius, 3 * EDSCALE, 3 * EDSCALE));
	}

	if (chat_tab) {
		chat_tab->set_custom_minimum_size(Size2(0, 32 * EDSCALE));
		chat_tab->add_theme_style_override("normal", make_surface_style(Color(0, 0, 0, 0), Color(0, 0, 0, 0), medium_radius, chip_padding_h, chip_padding_v));
		chat_tab->add_theme_style_override("hover", make_surface_style(shell_hover, Color(0, 0, 0, 0), medium_radius, chip_padding_h, chip_padding_v));
		chat_tab->add_theme_style_override("pressed", make_surface_style(shell_active, chip_active_border, medium_radius, chip_padding_h, chip_padding_v));
		chat_tab->add_theme_style_override("hover_pressed", make_surface_style(shell_active, chip_active_border, medium_radius, chip_padding_h, chip_padding_v));
		chat_tab->add_theme_color_override("font_color", current_tab == 0 ? strong : muted);
		chat_tab->add_theme_color_override("font_hover_color", strong);
		chat_tab->add_theme_color_override("font_pressed_color", strong);
		chat_tab->add_theme_color_override("font_hover_pressed_color", strong);
	}
	if (settings_tab) {
		settings_tab->set_custom_minimum_size(Size2(0, 32 * EDSCALE));
		settings_tab->add_theme_style_override("normal", make_surface_style(Color(0, 0, 0, 0), Color(0, 0, 0, 0), medium_radius, chip_padding_h, chip_padding_v));
		settings_tab->add_theme_style_override("hover", make_surface_style(shell_hover, Color(0, 0, 0, 0), medium_radius, chip_padding_h, chip_padding_v));
		settings_tab->add_theme_style_override("pressed", make_surface_style(shell_active, chip_active_border, medium_radius, chip_padding_h, chip_padding_v));
		settings_tab->add_theme_style_override("hover_pressed", make_surface_style(shell_active, chip_active_border, medium_radius, chip_padding_h, chip_padding_v));
		settings_tab->add_theme_color_override("font_color", current_tab == 1 ? strong : muted);
		settings_tab->add_theme_color_override("font_hover_color", strong);
		settings_tab->add_theme_color_override("font_pressed_color", strong);
		settings_tab->add_theme_color_override("font_hover_pressed_color", strong);
	}

	if (composer_card) {
		composer_card->add_theme_style_override("panel", make_surface_style(composer_fill, composer_border, large_radius));
	}
	if (approval_card) {
		approval_card->add_theme_style_override("panel", make_surface_style(approval_fill, approval_border, large_radius));
	}
	if (empty_state_card) {
		empty_state_card->add_theme_style_override("panel", make_surface_style(background.lerp(surface, 0.18f), strong.lerp(surface, 0.92f), large_radius));
	}

	auto apply_chip_button_theme = [&](Button *p_button) {
		if (!p_button) {
			return;
		}
		p_button->set_custom_minimum_size(Size2(0, 30 * EDSCALE));
		p_button->add_theme_constant_override("h_separation", (int)Math::round(7.0f * EDSCALE));
		p_button->add_theme_constant_override("icon_max_width", (int)Math::round(12.0f * EDSCALE));
		p_button->add_theme_style_override("normal", make_surface_style(chip_fill, chip_border, medium_radius, chip_padding_h + (int)Math::round(1.0f * EDSCALE), chip_padding_v));
		p_button->add_theme_style_override("hover", make_surface_style(chip_hover, chip_active_border, medium_radius, chip_padding_h + (int)Math::round(1.0f * EDSCALE), chip_padding_v));
		p_button->add_theme_style_override("pressed", make_surface_style(chip_active, chip_active_border, medium_radius, chip_padding_h + (int)Math::round(1.0f * EDSCALE), chip_padding_v));
		p_button->add_theme_style_override("hover_pressed", make_surface_style(chip_active, chip_active_border, medium_radius, chip_padding_h + (int)Math::round(1.0f * EDSCALE), chip_padding_v));
		p_button->add_theme_color_override("font_color", strong);
		p_button->add_theme_color_override("font_hover_color", strong);
		p_button->add_theme_color_override("font_pressed_color", strong);
		p_button->add_theme_color_override("font_hover_pressed_color", strong);
		p_button->add_theme_color_override("icon_normal_color", muted.lerp(strong, 0.7f));
		p_button->add_theme_color_override("icon_hover_color", strong);
		p_button->add_theme_color_override("icon_pressed_color", strong);
		p_button->add_theme_color_override("icon_hover_pressed_color", strong);
	};

	apply_chip_button_theme(mode_button);
	apply_chip_button_theme(model_button);
	apply_chip_button_theme(approval_policy_ask_button);
	apply_chip_button_theme(approval_policy_allow_button);
	apply_chip_button_theme(scroll_to_latest_button);
	for (int i = 0; i < transcript.size(); i++) {
		if (transcript[i].inline_plan_button) {
			apply_chip_button_theme(transcript[i].inline_plan_button);
			transcript.write[i].inline_plan_button->set_text("Execute Plan");
			transcript.write[i].inline_plan_button->set_button_icon(get_theme_icon(SNAME("Play"), EditorStringName(EditorIcons)));
		}
	}
	if (mode_button) {
		mode_button->set_custom_minimum_size(Size2((int)Math::round(84.0f * EDSCALE), 30 * EDSCALE));
	}
	if (model_button) {
		model_button->set_custom_minimum_size(Size2((int)Math::round(144.0f * EDSCALE), 30 * EDSCALE));
	}
	if (mode_button) {
		_apply_popup_theme(mode_button->get_popup());
	}
	if (model_button) {
		_apply_popup_theme(model_button->get_popup());
	}

	if (send_button) {
		send_button->set_custom_minimum_size(Size2(36 * EDSCALE, 36 * EDSCALE));
		send_button->add_theme_style_override("normal", make_surface_style(send_fill, Color(0, 0, 0, 0), medium_radius, 0, 0));
		send_button->add_theme_style_override("hover", make_surface_style(send_hover, Color(0, 0, 0, 0), medium_radius, 0, 0));
		send_button->add_theme_style_override("pressed", make_surface_style(chip_active, Color(0, 0, 0, 0), medium_radius, 0, 0));
		send_button->add_theme_style_override("hover_pressed", make_surface_style(chip_active, Color(0, 0, 0, 0), medium_radius, 0, 0));
		send_button->add_theme_color_override("icon_normal_color", strong);
		send_button->add_theme_color_override("icon_hover_color", strong);
		send_button->add_theme_color_override("icon_pressed_color", strong);
		send_button->add_theme_color_override("icon_hover_pressed_color", strong);
	}
	if (cancel_button) {
		const Color danger = get_theme_color("error_color", EditorStringName(Editor));
		cancel_button->set_custom_minimum_size(Size2(36 * EDSCALE, 36 * EDSCALE));
		cancel_button->add_theme_style_override("normal", make_surface_style(chip_fill, Color(0, 0, 0, 0), medium_radius, 0, 0));
		cancel_button->add_theme_style_override("hover", make_surface_style(chip_hover, Color(0, 0, 0, 0), medium_radius, 0, 0));
		cancel_button->add_theme_style_override("pressed", make_surface_style(chip_active, Color(0, 0, 0, 0), medium_radius, 0, 0));
		cancel_button->add_theme_style_override("hover_pressed", make_surface_style(chip_active, Color(0, 0, 0, 0), medium_radius, 0, 0));
		cancel_button->add_theme_color_override("font_color", danger);
		cancel_button->add_theme_color_override("font_hover_color", danger);
		cancel_button->add_theme_color_override("font_pressed_color", danger);
		cancel_button->add_theme_color_override("font_hover_pressed_color", danger);
		cancel_button->add_theme_color_override("icon_normal_color", danger);
		cancel_button->add_theme_color_override("icon_hover_color", danger);
		cancel_button->add_theme_color_override("icon_pressed_color", danger);
		cancel_button->add_theme_color_override("icon_hover_pressed_color", danger);
	}
	if (approval_allow_button) {
		approval_allow_button->set_custom_minimum_size(Size2(0, 30 * EDSCALE));
		approval_allow_button->add_theme_style_override("normal", make_surface_style(send_fill, Color(0, 0, 0, 0), medium_radius, chip_padding_h, chip_padding_v));
		approval_allow_button->add_theme_style_override("hover", make_surface_style(send_hover, Color(0, 0, 0, 0), medium_radius, chip_padding_h, chip_padding_v));
		approval_allow_button->add_theme_style_override("pressed", make_surface_style(chip_active, Color(0, 0, 0, 0), medium_radius, chip_padding_h, chip_padding_v));
		approval_allow_button->add_theme_style_override("hover_pressed", make_surface_style(chip_active, Color(0, 0, 0, 0), medium_radius, chip_padding_h, chip_padding_v));
		approval_allow_button->add_theme_color_override("font_color", strong);
		approval_allow_button->add_theme_color_override("font_hover_color", strong);
		approval_allow_button->add_theme_color_override("font_pressed_color", strong);
		approval_allow_button->add_theme_color_override("font_hover_pressed_color", strong);
	}
	if (approval_deny_button) {
		const Color danger = get_theme_color("error_color", EditorStringName(Editor));
		approval_deny_button->set_custom_minimum_size(Size2(0, 30 * EDSCALE));
		approval_deny_button->add_theme_style_override("normal", make_surface_style(chip_fill, chip_border, medium_radius, chip_padding_h, chip_padding_v));
		approval_deny_button->add_theme_style_override("hover", make_surface_style(chip_hover, chip_active_border, medium_radius, chip_padding_h, chip_padding_v));
		approval_deny_button->add_theme_style_override("pressed", make_surface_style(chip_active, chip_active_border, medium_radius, chip_padding_h, chip_padding_v));
		approval_deny_button->add_theme_style_override("hover_pressed", make_surface_style(chip_active, chip_active_border, medium_radius, chip_padding_h, chip_padding_v));
		approval_deny_button->add_theme_color_override("font_color", danger);
		approval_deny_button->add_theme_color_override("font_hover_color", danger);
		approval_deny_button->add_theme_color_override("font_pressed_color", danger);
		approval_deny_button->add_theme_color_override("font_hover_pressed_color", danger);
	}
	if (approval_title_label) {
		approval_title_label->add_theme_color_override("font_color", strong);
	}
	if (approval_details_label) {
		approval_details_label->add_theme_color_override("default_color", muted.lerp(strong, 0.3f));
	}
	if (approval_policy_ask_button) {
		approval_policy_ask_button->set_pressed(session.is_valid() && session->get_config().is_valid() && session->get_config()->get_approval_policy() == AIAgentConfig::APPROVAL_ASK);
	}
	if (approval_policy_allow_button) {
		approval_policy_allow_button->set_pressed(session.is_valid() && session->get_config().is_valid() && session->get_config()->get_approval_policy() == AIAgentConfig::APPROVAL_ALWAYS_ALLOW);
	}
	if (composer_action_slot) {
		composer_action_slot->set_custom_minimum_size(Size2(36 * EDSCALE, 36 * EDSCALE));
	}
	if (scroll_to_latest_button) {
		scroll_to_latest_button->set_button_icon(get_theme_icon(SNAME("GuiTreeArrowDown"), EditorStringName(EditorIcons)));
		scroll_to_latest_button->set_custom_minimum_size(Size2((int)Math::round(84.0f * EDSCALE), 30 * EDSCALE));
		scroll_to_latest_button->add_theme_color_override("icon_normal_color", strong);
		scroll_to_latest_button->add_theme_color_override("icon_hover_color", strong);
		scroll_to_latest_button->add_theme_color_override("icon_pressed_color", strong);
		scroll_to_latest_button->add_theme_color_override("icon_hover_pressed_color", strong);
	}

	if (input_field) {
		Ref<StyleBoxFlat> input_normal = make_surface_style(background.lerp(surface, 0.12f), strong.lerp(surface, 0.93f), medium_radius);
		input_normal->set_content_margin(SIDE_LEFT, 9 * EDSCALE);
		input_normal->set_content_margin(SIDE_TOP, 6 * EDSCALE);
		input_normal->set_content_margin(SIDE_RIGHT, 9 * EDSCALE);
		input_normal->set_content_margin(SIDE_BOTTOM, 6 * EDSCALE);

		Ref<StyleBoxFlat> input_focus = make_surface_style(background.lerp(surface, 0.12f), strong.lerp(surface, 0.93f), medium_radius);
		input_focus->set_content_margin(SIDE_LEFT, 9 * EDSCALE);
		input_focus->set_content_margin(SIDE_TOP, 6 * EDSCALE);
		input_focus->set_content_margin(SIDE_RIGHT, 9 * EDSCALE);
		input_focus->set_content_margin(SIDE_BOTTOM, 6 * EDSCALE);

		input_field->add_theme_style_override("normal", input_normal);
		input_field->add_theme_style_override("read_only", input_normal);
		input_field->add_theme_style_override("focus", input_focus);
		input_field->add_theme_color_override("font_color", strong);
		input_field->add_theme_color_override("font_placeholder_color", muted);
		input_field->add_theme_color_override("font_readonly_color", muted);
		input_field->add_theme_color_override("caret_color", strong);
		input_field->add_theme_color_override("selection_color", accent.lerp(composer_fill, 0.5f));
	}
}

void AIChatPanel::initialize_session() {
	if (session.is_valid()) {
		return;
	}

	session.instantiate();
	session->connect("message_received", callable_mp(this, &AIChatPanel::_on_message_received));
	session->connect("stream_chunk", callable_mp(this, &AIChatPanel::_on_stream_chunk));
	session->connect("tool_call_requested", callable_mp(this, &AIChatPanel::_on_tool_call_requested));
	session->connect("tool_call_completed", callable_mp(this, &AIChatPanel::_on_tool_call_completed));
	session->connect("approval_required", callable_mp(this, &AIChatPanel::_on_approval_required));
	session->connect("error_occurred", callable_mp(this, &AIChatPanel::_on_error_occurred));
	session->connect("thinking_state_changed", callable_mp(this, &AIChatPanel::_on_thinking_state_changed));
	session->connect("state_changed", callable_mp(this, &AIChatPanel::_on_session_state_changed));

	if (settings_panel) {
		session->set_config(settings_panel->get_config());
	}
	const bool restored = session->restore_last_saved_session();
	if (!restored) {
		session->set_mode(AI_AGENT_MODE_ASK);
		_set_transcript_autoscroll_enabled(true);
	} else {
		_restore_transcript_from_session_history();
	}

	_refresh_header_state();
	_refresh_empty_state();
	_refresh_approval_section();
}

void AIChatPanel::_on_config_changed(const Ref<AIAgentConfig> &p_config) {
	if (session.is_valid()) {
		session->set_config(p_config);
	}
	_refresh_empty_state();
	_refresh_header_state();
	_refresh_approval_section();
	if (p_config.is_valid() && p_config->get_approval_policy() == AIAgentConfig::APPROVAL_ALWAYS_ALLOW && !pending_approval_tool_call_id.is_empty()) {
		_approve_pending_tool_call();
	}
}

void AIChatPanel::_on_thinking_state_changed(bool p_active) {
	if (active_assistant_entry < 0 || active_assistant_entry >= transcript.size()) {
		return;
	}

	TimelineEntry &entry = transcript.write[active_assistant_entry];
	if (entry.kind != TimelineEntry::KIND_ASSISTANT) {
		return;
	}

	const uint64_t now = OS::get_singleton()->get_ticks_msec();
	if (p_active) {
		_start_entry_thinking(entry, now);
		entry.thinking_phase_finished = false;
	} else {
		_stop_entry_thinking(entry, now);
		entry.thinking_phase_finished = !entry.thinking_content.is_empty();
	}
	_update_entry_visuals(active_assistant_entry);
}

void AIChatPanel::_set_mode(int p_mode) {
	if (session.is_valid()) {
		session->set_mode((AIAgentModeId)p_mode);
	}
	_refresh_header_state();
}

void AIChatPanel::_on_mode_menu_id_pressed(int p_id) {
	_set_mode(p_id);
}

void AIChatPanel::_on_model_menu_id_pressed(int p_id) {
	if (!model_button) {
		return;
	}

	PopupMenu *popup = model_button->get_popup();
	const int index = popup->get_item_index(p_id);
	if (index < 0) {
		return;
	}
	const Variant metadata = popup->get_item_metadata(index);
	if (metadata.get_type() != Variant::DICTIONARY) {
		return;
	}
	const Dictionary meta = metadata;
	if (!meta.has("provider_type") || !meta.has("model_name")) {
		return;
	}

	Ref<AIAgentConfig> cfg;
	if (settings_panel) {
		cfg = settings_panel->get_config();
	} else if (session.is_valid()) {
		cfg = session->get_config();
	}
	if (cfg.is_null()) {
		return;
	}

	cfg->set_provider_type((AIAgentConfig::ProviderType)(int)meta["provider_type"]);
	cfg->set_model_name((String)meta["model_name"]);
	cfg->apply_provider_defaults(cfg->get_model_name().is_empty(), false);

	if (settings_panel) {
		settings_panel->persist_config();
	} else if (session.is_valid()) {
		session->set_config(cfg);
	}

	_refresh_header_state();
}

void AIChatPanel::_on_mode_menu_about_to_popup() {
	if (!mode_button) {
		return;
	}
	PopupMenu *popup = mode_button->get_popup();
	if (!popup) {
		return;
	}

	_position_menu_popup_above(mode_button);
	_apply_popup_theme(popup);
	const Point2i target_position = popup->get_position();
	popup->set_position(target_position + Point2i(0, (int)Math::round(POPUP_REVEAL_OFFSET_Y * EDSCALE)));
	callable_mp(this, &AIChatPanel::_animate_popup_menu_open).call_deferred(popup, target_position);
}

void AIChatPanel::_on_model_menu_about_to_popup() {
	if (!model_button) {
		return;
	}
	PopupMenu *popup = model_button->get_popup();
	if (!popup) {
		return;
	}

	_position_menu_popup_above(model_button);
	_apply_popup_theme(popup);
	const Point2i target_position = popup->get_position();
	popup->set_position(target_position + Point2i(0, (int)Math::round(POPUP_REVEAL_OFFSET_Y * EDSCALE)));
	callable_mp(this, &AIChatPanel::_animate_popup_menu_open).call_deferred(popup, target_position);
}

void AIChatPanel::_position_menu_popup_above(MenuButton *p_button) {
	if (!p_button) {
		return;
	}

	PopupMenu *popup = p_button->get_popup();
	if (!popup || !get_window()) {
		return;
	}

	Rect2 button_rect = p_button->get_screen_rect();
	if (get_viewport()->is_embedding_subwindows() && popup->get_force_native()) {
		Transform2D xform = get_viewport()->get_popup_base_transform_native();
		button_rect = xform.xform(button_rect);
	}

	const Rect2i usable_rect = DisplayServer::get_singleton()->screen_get_usable_rect(get_window()->get_current_screen());
	const int popup_gap = MAX(4, (int)Math::round(4.0f * EDSCALE));
	const Size2 min_size = popup->get_contents_minimum_size();
	const int popup_width = MAX((int)Math::ceil(min_size.width), (int)Math::ceil(button_rect.size.x));
	const int popup_height = (int)Math::ceil(min_size.height);
	const int available_above = MAX(0, (int)button_rect.position.y - usable_rect.position.y - popup_gap);

	Size2i max_size = popup->get_max_size();
	max_size.width = 0;
	max_size.height = available_above;
	popup->set_max_size(max_size);

	Point2 popup_position = button_rect.position;
	popup_position.y = button_rect.position.y - MIN(popup_height, available_above) - popup_gap;
	popup_position.x = CLAMP((int)popup_position.x, usable_rect.position.x, usable_rect.get_end().x - popup_width);

	if (is_layout_rtl()) {
		popup_position.x = CLAMP((int)(button_rect.position.x + button_rect.size.x - popup_width), usable_rect.position.x, usable_rect.get_end().x - popup_width);
	}

	popup->set_position(popup_position);
}

void AIChatPanel::_apply_popup_theme(PopupMenu *p_popup) {
	if (!p_popup) {
		return;
	}

	const Color strong = get_theme_color("font_color", EditorStringName(Editor));
	const Color muted = get_theme_color("font_placeholder_color", EditorStringName(Editor));
	const Color background = get_theme_color("dark_color_1", EditorStringName(Editor));
	const Color surface = get_theme_color("dark_color_2", EditorStringName(Editor));
	const Color accent = get_theme_color("accent_color", EditorStringName(Editor));
	const int radius = (int)Math::round(14.0f * EDSCALE);
	const int item_radius = MAX((int)Math::round(8.0f * EDSCALE), radius - (int)Math::round(5.0f * EDSCALE));
	const int border_width = 1;
	const int popup_padding = (int)Math::round(8.0f * EDSCALE);
	const int item_padding_h = (int)Math::round(12.0f * EDSCALE);
	const int item_padding_v = (int)Math::round(7.0f * EDSCALE);

	Ref<StyleBoxFlat> panel_style;
	panel_style.instantiate();
	panel_style->set_bg_color(background.lerp(surface, 0.26f));
	panel_style->set_border_color(accent.lerp(strong.lerp(surface, 0.9f), 0.16f));
	panel_style->set_border_width_all(border_width);
	panel_style->set_corner_radius_all(radius);
	panel_style->set_content_margin_all(popup_padding);

	Ref<StyleBoxFlat> hover_style;
	hover_style.instantiate();
	hover_style->set_bg_color(background.lerp(surface, 0.48f).lerp(accent, 0.08f));
	hover_style->set_border_color(accent.lerp(surface, 0.38f));
	hover_style->set_border_width_all(border_width);
	hover_style->set_corner_radius_all(item_radius);
	hover_style->set_content_margin(SIDE_LEFT, item_padding_h);
	hover_style->set_content_margin(SIDE_TOP, item_padding_v);
	hover_style->set_content_margin(SIDE_RIGHT, item_padding_h);
	hover_style->set_content_margin(SIDE_BOTTOM, item_padding_v);

	Ref<StyleBoxLine> separator_style;
	separator_style.instantiate();
	separator_style->set_color(strong.lerp(surface, 0.84f));
	separator_style->set_thickness(MAX(1, (int)Math::round(1.0f * EDSCALE)));
	separator_style->set_grow_begin((int)Math::round(-4.0f * EDSCALE));
	separator_style->set_grow_end((int)Math::round(-4.0f * EDSCALE));

	p_popup->add_theme_style_override("panel", panel_style);
	p_popup->add_theme_style_override("hover", hover_style);
	p_popup->add_theme_style_override("separator", separator_style);
	p_popup->add_theme_style_override("labeled_separator_left", separator_style);
	p_popup->add_theme_style_override("labeled_separator_right", separator_style);
	p_popup->add_theme_color_override("font_color", strong);
	p_popup->add_theme_color_override("font_hover_color", strong);
	p_popup->add_theme_color_override("font_accelerator_color", muted);
	p_popup->add_theme_color_override("font_separator_color", muted.lerp(strong, 0.15f));
	p_popup->add_theme_color_override("font_disabled_color", muted);
	p_popup->add_theme_color_override("icon_normal_color", muted.lerp(strong, 0.7f));
	p_popup->add_theme_color_override("icon_hover_color", strong);
	p_popup->add_theme_constant_override("outline_size", 0);
	p_popup->add_theme_constant_override("v_separation", (int)Math::round(4.0f * EDSCALE));
	p_popup->add_theme_constant_override("h_separation", (int)Math::round(9.0f * EDSCALE));
	p_popup->add_theme_constant_override("item_start_padding", item_padding_h);
	p_popup->add_theme_constant_override("item_end_padding", item_padding_h);
}

void AIChatPanel::_animate_popup_menu_open(PopupMenu *p_popup, Point2i p_target_position) {
	if (!p_popup || !is_inside_tree()) {
		return;
	}

	Control *panel = nullptr;
	if (p_popup->get_child_count() > 0) {
		panel = Object::cast_to<Control>(p_popup->get_child(0));
	}
	if (!panel) {
		return;
	}

	_set_control_opacity(0.0f, panel);
	panel->set_position(Vector2(panel->get_position().x, (float)Math::round(4.0f * EDSCALE)));

	Ref<Tween> tween = p_popup->create_tween();
	tween->set_parallel(true);
	tween->set_trans(Tween::TRANS_CUBIC);
	tween->set_ease(Tween::EASE_OUT);
	tween->tween_property(p_popup, NodePath("position"), p_target_position, ENTRY_FADE_DURATION);
	Color panel_target_modulate = panel->get_self_modulate();
	panel_target_modulate.a = 1.0f;
	tween->tween_property(panel, NodePath("self_modulate"), panel_target_modulate, ENTRY_FADE_DURATION);
	tween->tween_property(panel, NodePath("position"), Vector2(panel->get_position().x, 0.0f), ENTRY_FADE_DURATION);
}

void AIChatPanel::_refresh_model_menu() {
	if (!model_button) {
		return;
	}
	if (refreshing_model_menu) {
		return;
	}

	refreshing_model_menu = true;

	PopupMenu *popup = model_button->get_popup();
	popup->clear();

	Ref<AIAgentConfig> cfg;
	if (settings_panel) {
		cfg = settings_panel->get_config();
	} else if (session.is_valid()) {
		cfg = session->get_config();
	}
	if (cfg.is_null()) {
		model_button->set_button_icon(Ref<Texture2D>());
		model_button->set_text("Model");
		model_button->set_tooltip_text("Select model");
		refreshing_model_menu = false;
		return;
	}

	const Vector<AIAgentConfig::ProviderType> saved_providers = cfg->get_saved_provider_types();
	for (int provider_index = 0; provider_index < saved_providers.size(); provider_index++) {
		const AIAgentConfig::ProviderType provider = saved_providers[provider_index];
		const AIProviderDescriptor descriptor = ai_agent_get_provider_descriptor(provider);
		if (settings_panel) {
			settings_panel->ensure_model_suggestions(provider, false);
		}
		popup->add_separator(descriptor.name);

		PackedStringArray models = settings_panel ? settings_panel->get_suggested_models(provider) : descriptor.recommended_models;
		const String saved_model = cfg->get_provider_model_name(provider);
		PackedStringArray unique_models;
		if (!saved_model.is_empty()) {
			unique_models.push_back(saved_model);
		}
		for (int i = 0; i < models.size(); i++) {
			if (!models[i].is_empty() && !unique_models.has(models[i])) {
				unique_models.push_back(models[i]);
			}
		}

		const Ref<Texture2D> provider_icon = _get_ai_editor_icon(this, descriptor.icon_name);
		for (int i = 0; i < unique_models.size(); i++) {
			const int item_id = popup->get_item_count();
			popup->add_icon_item(provider_icon, unique_models[i], item_id);
			const int item_index = popup->get_item_index(item_id);
			popup->set_item_icon_max_width(item_index, (int)Math::round(12.0f * EDSCALE));
			popup->set_item_tooltip(item_index, descriptor.description);
			Dictionary meta;
			meta["provider_type"] = (int)provider;
			meta["model_name"] = unique_models[i];
			popup->set_item_metadata(item_index, meta);
		}
	}

	const AIProviderDescriptor active_provider = ai_agent_get_provider_descriptor(cfg->get_provider_type());
	const AIAgentModeId current_mode = session.is_valid() ? session->get_mode() : AI_AGENT_MODE_ASK;
	const ResolvedAgentRunConfig resolved = ai_agent_resolve_run_config(cfg, current_mode, PackedStringArray());
	model_button->set_button_icon(_get_ai_editor_icon(this, active_provider.icon_name));
	model_button->set_text(resolved.model_name);
	String provider_hint = active_provider.description;
	if (cfg->has_mode_model_override((int)current_mode)) {
		model_button->set_tooltip_text(vformat("Provider: %s\nResolved model for %s mode: %s (override from Settings)\n\n%s",
				active_provider.name,
				ai_agent_mode_get_name(current_mode),
				resolved.model_name,
				provider_hint));
	} else {
		model_button->set_tooltip_text(vformat("Provider: %s\nResolved model for %s mode: %s\n\n%s",
				active_provider.name,
				ai_agent_mode_get_name(current_mode),
				resolved.model_name,
				provider_hint));
	}

	refreshing_model_menu = false;
}

void AIChatPanel::_send_message() {
	if (!input_field) {
		return;
	}

	String text = input_field->get_text().strip_edges();
	if (text.is_empty()) {
		return;
	}

	if (session.is_valid() && session->get_config().is_valid()) {
		Ref<AIAgentConfig> cfg = session->get_config();
		if (!cfg->is_configured()) {
			_add_activity_entry(TimelineEntry::KIND_SYSTEM, "Connect a provider before sending messages.");
			_on_tab_selected(1);
			return;
		}
	} else {
		_add_activity_entry(TimelineEntry::KIND_SYSTEM, "AI session not configured. Open Settings and save your provider first.");
		_on_tab_selected(1);
		return;
	}

	_clear_executable_plan_entry();
	_add_user_entry(text);

	input_field->set_text("");
	_update_input_height();
	input_field->grab_focus();

	if (session.is_valid()) {
		Dictionary ui_context;
		ui_context["surface"] = "editor_chat_panel";
		session->send_message_with_context(text, ui_context);
	}
}

void AIChatPanel::_clear_chat() {
	latest_executable_plan_entry = -1;
	transcript.clear();
	tool_entry_indices.clear();
	active_assistant_entry = -1;
	pending_assistant_started_msec = 0;
	last_runtime_state_refresh_msec = 0;
	_set_transcript_autoscroll_enabled(true);
	_render_transcript();
	if (session.is_valid()) {
		session->clear_history();
	}
	_refresh_header_state();
}

void AIChatPanel::_cancel_request() {
	if (session.is_valid()) {
		session->cancel();
	}
}

void AIChatPanel::_set_approval_policy(AIAgentConfig::ApprovalPolicy p_policy) {
	Ref<AIAgentConfig> cfg;
	if (settings_panel) {
		cfg = settings_panel->get_config();
	} else if (session.is_valid()) {
		cfg = session->get_config();
	}
	if (cfg.is_null()) {
		return;
	}

	cfg->set_approval_policy(p_policy);
	if (settings_panel) {
		settings_panel->persist_config();
	} else if (session.is_valid()) {
		if (EditorSettings *settings = EditorSettings::get_singleton()) {
			settings->set(AI_SETTING_APPROVAL_POLICY, (int)p_policy);
			EditorSettings::save();
		}
		session->set_config(cfg);
	}

	_refresh_approval_section();
	_refresh_header_state();

	if (p_policy == AIAgentConfig::APPROVAL_ALWAYS_ALLOW && !pending_approval_tool_call_id.is_empty()) {
		_approve_pending_tool_call();
	}
}

void AIChatPanel::_approve_pending_tool_call() {
	const String tool_call_id = pending_approval_tool_call_id;
	pending_approval_tool_call_id = "";
	pending_approval_tool_name = "";
	pending_approval_arguments.clear();
	_refresh_approval_section();
	if (session.is_valid() && !tool_call_id.is_empty()) {
		session->approve_tool_call(tool_call_id);
	}
}

void AIChatPanel::_deny_pending_tool_call() {
	const String tool_call_id = pending_approval_tool_call_id;
	pending_approval_tool_call_id = "";
	pending_approval_tool_name = "";
	pending_approval_arguments.clear();
	_refresh_approval_section();
	if (session.is_valid() && !tool_call_id.is_empty()) {
		session->deny_tool_call(tool_call_id, "User denied the tool call from the chat panel.");
	}
}

void AIChatPanel::_on_execute_plan_pressed(int p_entry_index) {
	if (!session.is_valid() || p_entry_index < 0 || p_entry_index >= transcript.size()) {
		return;
	}

	const TimelineEntry &entry = transcript[p_entry_index];
	if (entry.kind != TimelineEntry::KIND_ASSISTANT || !entry.can_execute_plan || entry.content.is_empty()) {
		return;
	}

	_clear_executable_plan_entry();

	// Switch to Edit mode.
	_set_mode((int)AI_AGENT_MODE_EDIT);

	// Build the execution prompt from the plan.
	String execution_prompt = "Execute the following plan step by step. Apply each change carefully.\n\n" + entry.content;

	// Send the plan as a user message.
	_add_user_entry("Execute plan");

	Dictionary ui_context;
	ui_context["surface"] = "editor_chat_panel";
	ui_context["origin"] = "plan_execute";
	session->send_message_with_context(execution_prompt, ui_context);
}

void AIChatPanel::_on_message_received(const Ref<AIMessage> &p_message) {
	if (p_message.is_null()) {
		return;
	}

	_finalize_active_assistant_entry(p_message);
}

void AIChatPanel::_on_stream_chunk(const Ref<AIMessage> &p_chunk) {
	if (p_chunk.is_null()) {
		return;
	}

	if (p_chunk->get_content().is_empty() && p_chunk->get_thinking_content().is_empty()) {
		return;
	}

	const bool should_follow = _should_autoscroll();
	const int entry_index = _ensure_assistant_entry(true);
	TimelineEntry &entry = transcript.write[entry_index];
	entry.content += p_chunk->get_content();
	entry.thinking_content += p_chunk->get_thinking_content();
	if (!p_chunk->get_content().is_empty()) {
		entry.pending_visible_stream_delta += p_chunk->get_content();
		entry.stream_dirty = true;
		if (entry.first_visible_chunk_msec == 0) {
			entry.first_visible_chunk_msec = OS::get_singleton()->get_ticks_msec();
		}
	}
	entry.stream_should_autoscroll = entry.stream_should_autoscroll || should_follow;
	if (!p_chunk->get_thinking_content().is_empty()) {
		entry.thinking_phase_finished = false;
	}
	_update_entry_visuals(entry_index);

	const uint64_t now = OS::get_singleton()->get_ticks_msec();
	if (!entry.pending_visible_stream_delta.is_empty() && (entry.last_stream_flush_msec == 0 || now - entry.last_stream_flush_msec >= STREAM_FLUSH_INTERVAL_MSEC)) {
		_flush_entry_stream_updates(entry_index, false);
	}
}

void AIChatPanel::_on_tool_call_requested(const String &p_tool_name, const Dictionary &p_args, const String &p_tool_call_id) {
	const bool should_follow = _should_autoscroll();
	int entry_index = -1;
	if (_tool_prefers_activity_row(p_tool_name)) {
		entry_index = _add_activity_entry(TimelineEntry::KIND_ACTIVITY, _tool_activity_title(p_tool_name, p_args), "", p_tool_name, p_tool_call_id);
	} else {
		entry_index = _add_tool_card_entry(p_tool_name, p_args, p_tool_call_id);
	}

	if (!p_tool_call_id.is_empty()) {
		tool_entry_indices[p_tool_call_id] = entry_index;
	}
	if (should_follow && entry_index >= 0 && entry_index < transcript.size()) {
		_maybe_autoscroll(transcript[entry_index].root);
	}
}

void AIChatPanel::_on_tool_call_completed(const String &p_tool_name, const Variant &p_result, const String &p_tool_call_id) {
	const String formatted_result = _format_tool_result(p_result);
	const String summary = _summarize_tool_result(p_result);
	const bool is_error = formatted_result.begins_with("Error:");

	if (!p_tool_call_id.is_empty() && tool_entry_indices.has(p_tool_call_id)) {
		const int entry_index = tool_entry_indices[p_tool_call_id];
		if (entry_index >= 0 && entry_index < transcript.size()) {
			TimelineEntry &entry = transcript.write[entry_index];
			if (entry.kind == TimelineEntry::KIND_TOOL_CARD) {
				entry.footer_left = formatted_result;
				entry.footer_right = is_error ? "Failed" : "Completed";
			} else {
				entry.secondary_text = summary;
				entry.footer_right = is_error ? "Failed" : "Completed";
			}
			_update_entry_visuals(entry_index);
			return;
		}
	}

	_add_activity_entry(is_error ? TimelineEntry::KIND_ERROR : TimelineEntry::KIND_ACTIVITY,
			vformat("%s finished", _humanize_tool_name(p_tool_name)), summary, p_tool_name, p_tool_call_id);
}

void AIChatPanel::_on_approval_required(const String &p_tool_name, const Dictionary &p_args, const String &p_tool_call_id) {
	pending_approval_tool_call_id = p_tool_call_id;
	pending_approval_tool_name = p_tool_name;
	pending_approval_arguments = p_args;

	if (!p_tool_call_id.is_empty() && tool_entry_indices.has(p_tool_call_id)) {
		const int entry_index = tool_entry_indices[p_tool_call_id];
		if (entry_index >= 0 && entry_index < transcript.size()) {
			transcript.write[entry_index].footer_right = "Approval required";
			_update_entry_visuals(entry_index);
		}
	}

	_add_activity_entry(TimelineEntry::KIND_ACTIVITY, "Approval required", _humanize_tool_name(p_tool_name), p_tool_name, p_tool_call_id);
	_refresh_approval_section();
}

void AIChatPanel::_on_error_occurred(const String &p_error) {
	pending_approval_tool_call_id = "";
	pending_approval_tool_name = "";
	pending_approval_arguments.clear();

	if (active_assistant_entry != -1 && active_assistant_entry < transcript.size()) {
		TimelineEntry &entry = transcript.write[active_assistant_entry];
		entry.is_pending = false;
		_finalize_entry_thinking(entry, OS::get_singleton()->get_ticks_msec());
		_flush_entry_stream_updates(active_assistant_entry, true);
		_finalize_entry_stream_display(active_assistant_entry);
		if (entry.duration_seconds < 0.0 && entry.started_msec > 0) {
			entry.duration_seconds = (OS::get_singleton()->get_ticks_msec() - entry.started_msec) / 1000.0;
		}
		_update_entry_visuals(active_assistant_entry);
		active_assistant_entry = -1;
	}
	pending_assistant_started_msec = 0;
	_add_activity_entry(TimelineEntry::KIND_ERROR, p_error);
	_refresh_approval_section();
	_refresh_header_state();
}

void AIChatPanel::_on_session_state_changed(int p_state) {
	const bool is_busy = (p_state != AIAgentSession::STATE_IDLE && p_state != AIAgentSession::STATE_ERROR);
	if (p_state != AIAgentSession::STATE_WAITING_FOR_APPROVAL) {
		pending_approval_tool_call_id = "";
		pending_approval_tool_name = "";
		pending_approval_arguments.clear();
	}
	send_button->set_disabled(is_busy);
	_update_action_slot_state(is_busy, true);

	if (p_state == AIAgentSession::STATE_WAITING_FOR_RESPONSE && pending_assistant_started_msec == 0) {
		pending_assistant_started_msec = OS::get_singleton()->get_ticks_msec();
		const int entry_index = _ensure_assistant_entry(true);
		if (entry_index >= 0 && entry_index < transcript.size()) {
			_update_entry_visuals(entry_index);
			if (_should_autoscroll() && transcript[entry_index].root) {
				_maybe_autoscroll(transcript[entry_index].root);
			}
		}
	} else if (!is_busy) {
		if (active_assistant_entry != -1 && active_assistant_entry < transcript.size()) {
			TimelineEntry &entry = transcript.write[active_assistant_entry];
			entry.is_pending = false;
			_finalize_entry_thinking(entry, OS::get_singleton()->get_ticks_msec());
			_flush_entry_stream_updates(active_assistant_entry, true);
			_finalize_entry_stream_display(active_assistant_entry);
			if (entry.duration_seconds < 0.0 && entry.started_msec > 0) {
				entry.duration_seconds = (OS::get_singleton()->get_ticks_msec() - entry.started_msec) / 1000.0;
			}
			_update_entry_visuals(active_assistant_entry);
		}
		active_assistant_entry = -1;
		pending_assistant_started_msec = 0;
	}

	_refresh_header_state();
	_refresh_approval_section();

	// Plan → Execute: expose the inline action only on the latest completed plan response.
	if (!is_busy && session.is_valid() && session->get_mode() == AI_AGENT_MODE_PLAN) {
		_clear_executable_plan_entry();
		for (int i = transcript.size() - 1; i >= 0; i--) {
			if (transcript[i].kind == TimelineEntry::KIND_ASSISTANT && !transcript[i].content.is_empty()) {
				_set_executable_plan_entry(i);
				break;
			}
		}
	} else if (is_busy) {
		_clear_executable_plan_entry();
	}
}

String AIChatPanel::_escape_bbcode(const String &p_text) const {
	String escaped = p_text;
	escaped = escaped.replace("[", "[lb]");
	escaped = escaped.replace("]", "[rb]");
	return escaped;
}

void AIChatPanel::_refresh_header_state() {
	AIAgentModeId current_mode = session.is_valid() ? session->get_mode() : AI_AGENT_MODE_ASK;
	AIAgentModeProfile mode_profile = ai_agent_get_mode_profile(current_mode);

	if (mode_button) {
		PopupMenu *popup = mode_button->get_popup();
		popup->clear();
		const AIAgentModeId modes[] = { AI_AGENT_MODE_ASK, AI_AGENT_MODE_EDIT, AI_AGENT_MODE_PLAN, AI_AGENT_MODE_DEBUG, AI_AGENT_MODE_ORCHESTRATE };
		for (AIAgentModeId mode_id : modes) {
			const AIAgentModeProfile profile = ai_agent_get_mode_profile(mode_id);
			popup->add_icon_item(_get_ai_editor_icon(this, profile.icon_name), profile.title, mode_id);
			const int item_index = popup->get_item_index(mode_id);
			if (item_index >= 0) {
				popup->set_item_icon_max_width(item_index, (int)Math::round(12.0f * EDSCALE));
			}
		}
		mode_button->set_button_icon(_get_ai_editor_icon(this, mode_profile.icon_name));
		mode_button->set_text(mode_profile.title);
		mode_button->set_tooltip_text(mode_profile.description);
	}
	_refresh_model_menu();
	if (input_field) {
		switch (current_mode) {
			case AI_AGENT_MODE_ASK:
				input_field->set_placeholder("Ask AI...");
				break;
			case AI_AGENT_MODE_EDIT:
				input_field->set_placeholder("Describe a change...");
				break;
			case AI_AGENT_MODE_PLAN:
				input_field->set_placeholder("Describe a plan...");
				break;
			case AI_AGENT_MODE_DEBUG:
				input_field->set_placeholder("Describe the bug or error...");
				break;
			case AI_AGENT_MODE_ORCHESTRATE:
				input_field->set_placeholder("Describe the larger task...");
				break;
		}
	}
}

void AIChatPanel::_refresh_approval_section() {
	if (!approval_card) {
		return;
	}

	Ref<AIAgentConfig> cfg;
	if (session.is_valid()) {
		cfg = session->get_config();
	} else if (settings_panel) {
		cfg = settings_panel->get_config();
	}

	const AIAgentConfig::ApprovalPolicy policy = cfg.is_valid() ? cfg->get_approval_policy() : AIAgentConfig::APPROVAL_ASK;
	if (approval_policy_ask_button) {
		approval_policy_ask_button->set_pressed(policy == AIAgentConfig::APPROVAL_ASK);
	}
	if (approval_policy_allow_button) {
		approval_policy_allow_button->set_pressed(policy == AIAgentConfig::APPROVAL_ALWAYS_ALLOW);
	}

	const bool has_pending_approval = !pending_approval_tool_call_id.is_empty();
	approval_card->set_visible(has_pending_approval);
	if (!has_pending_approval) {
		return;
	}

	if (approval_title_label) {
		approval_title_label->set_text(vformat("Allow %s?", _humanize_tool_name(pending_approval_tool_name)));
	}
	if (approval_details_label) {
		const Color muted = get_theme_color("font_placeholder_color", EditorStringName(Editor));
		const String args_text = _escape_bbcode(JSON::stringify(pending_approval_arguments, "  "));
		approval_details_label->set_text("[color=#" + muted.to_html(false) + "]Arguments[/color]\n" + args_text);
	}
}

void AIChatPanel::_render_transcript() {
	_rebuild_timeline();
	_refresh_empty_state();
	_refresh_scroll_to_latest_button();
}

void AIChatPanel::_restore_transcript_from_session_history() {
	if (!session.is_valid()) {
		return;
	}

	transcript.clear();
	tool_entry_indices.clear();
	active_assistant_entry = -1;
	latest_executable_plan_entry = -1;

	TypedArray<Dictionary> history = session->get_history();
	for (int i = 0; i < history.size(); i++) {
		Ref<AIMessage> message = AIMessage::from_dict(history[i]);
		if (message.is_null()) {
			continue;
		}

		if (message->get_role() == AIMessage::ROLE_SYSTEM) {
			const String content = message->get_content();
			if (content.begins_with("You are Godoty's")) {
				continue;
			}
			_add_activity_entry(TimelineEntry::KIND_SYSTEM, content.substr(0, 140));
			continue;
		}

		if (message->get_role() == AIMessage::ROLE_USER) {
			_add_user_entry(message->get_content());
			continue;
		}

		if (message->get_role() == AIMessage::ROLE_ASSISTANT) {
			const int entry_index = _ensure_assistant_entry(false);
			TimelineEntry &entry = transcript.write[entry_index];
			entry.content = message->get_content();
			entry.thinking_content = message->get_thinking_content();
			entry.is_pending = false;
			entry.thinking_phase_finished = !entry.thinking_content.is_empty();
			_update_entry_visuals(entry_index);
			active_assistant_entry = -1;
			continue;
		}

		if (message->get_role() == AIMessage::ROLE_TOOL) {
			const Dictionary metadata = message->get_metadata();
			const String tool_name = metadata.get("tool_name", "tool");
			String title = "Restored tool result";
			if (!tool_name.is_empty()) {
				title += ": " + _humanize_tool_name(tool_name);
			}
			_add_activity_entry(TimelineEntry::KIND_SYSTEM, title, _summarize_tool_result(message->get_content()));
		}
	}

	_render_transcript();
	_set_transcript_autoscroll_enabled(true);
	callable_mp(this, &AIChatPanel::_scroll_transcript_to_bottom).call_deferred();
}

void AIChatPanel::_rebuild_timeline() {
	if (!timeline_list || !empty_state || !empty_state_wrap) {
		return;
	}

	while (timeline_list->get_child_count() > 1) {
		Node *child = timeline_list->get_child(1);
		timeline_list->remove_child(child);
		child->queue_free();
	}

	for (int i = 0; i < transcript.size(); i++) {
		_create_entry_ui(i, false);
	}

	_refresh_empty_state();
	_refresh_scroll_to_latest_button();
}

void AIChatPanel::_refresh_empty_state() {
	if (!empty_state || !empty_state_wrap) {
		return;
	}

	const Color muted = get_theme_color("font_placeholder_color", EditorStringName(Editor));
	if (!transcript.is_empty()) {
		empty_state_wrap->set_visible(false);
		_refresh_scroll_to_latest_button();
		return;
	}

	Ref<AIAgentConfig> cfg;
	if (session.is_valid()) {
		cfg = session->get_config();
	} else if (settings_panel) {
		cfg = settings_panel->get_config();
	}

	String text = "[center][color=#" + muted.to_html(false) + "]Start a conversation[/color][/center]\n";
	if (cfg.is_valid() && cfg->is_configured()) {
		const String model_name = cfg->get_model_name().is_empty() ? cfg->get_default_model_name() : cfg->get_model_name();
		text += "[center][color=#" + muted.to_html(false) + "]Using " + _escape_bbcode(model_name) + " on " + _escape_bbcode(cfg->get_provider_name()) + ".[/color][/center]";
	} else {
		text += "[center][color=#" + muted.to_html(false) + "]Open Settings to connect a provider and save credentials.[/color][/center]";
	}

	empty_state->set_text(text);
	empty_state_wrap->set_visible(true);
	_refresh_scroll_to_latest_button();
}

void AIChatPanel::_create_entry_ui(int p_index, bool p_animate_in) {
	ERR_FAIL_INDEX(p_index, transcript.size());
	ERR_FAIL_NULL(timeline_list);

	const Color strong = get_theme_color("font_color", EditorStringName(Editor));
	const Color muted = get_theme_color("font_placeholder_color", EditorStringName(Editor));

	auto make_text_block = [&](bool p_code = false) {
		RichTextLabel *label = memnew(RichTextLabel);
		label->set_h_size_flags(SIZE_EXPAND_FILL);
		label->set_fit_content(true);
		label->set_scroll_active(false);
		label->set_selection_enabled(true);
		label->set_use_bbcode(true);
		label->set_threaded(false);
		Ref<StyleBoxFlat> text_style;
		text_style.instantiate();
		text_style->set_bg_color(Color(0, 0, 0, 0));
		text_style->set_border_width_all(0);
		text_style->set_content_margin_all(0);
		label->add_theme_style_override("normal", text_style);
		label->add_theme_style_override("focus", text_style);
		if (p_code) {
			label->add_theme_color_override("default_color", muted.lerp(strong, 0.5f));
		}
		return label;
	};

	TimelineEntry &entry = transcript.write[p_index];
	entry.root = nullptr;
	entry.body = nullptr;
	entry.panel = nullptr;
	entry.content_panel = nullptr;
	entry.title_label = nullptr;
	entry.secondary_label = nullptr;
	entry.thinking_log_label = nullptr;
	entry.stream_preview = nullptr;
	entry.content_label = nullptr;
	entry.details_label = nullptr;
	entry.output_label = nullptr;
	entry.inline_action_row = nullptr;
	entry.inline_plan_button = nullptr;
	entry.footer_row = nullptr;
	entry.footer_left_label = nullptr;
	entry.footer_right_label = nullptr;

	VBoxContainer *wrapper = memnew(VBoxContainer);
	wrapper->set_h_size_flags(SIZE_EXPAND_FILL);
	wrapper->set_clip_contents(true);
	wrapper->set_self_modulate(Color(1, 1, 1, 1));
	timeline_list->add_child(wrapper);
	timeline_list->move_child(wrapper, p_index + 1);

	switch (entry.kind) {
		case TimelineEntry::KIND_USER: {
			MarginContainer *row = memnew(MarginContainer);
			row->set_h_size_flags(SIZE_EXPAND_FILL);
			row->add_theme_constant_override("margin_left", (int)Math::round(72.0f * EDSCALE));
			row->add_theme_constant_override("margin_right", 0);

			PanelContainer *panel = memnew(PanelContainer);
			panel->set_h_size_flags(SIZE_EXPAND_FILL);
			MarginContainer *margin = memnew(MarginContainer);
			margin->add_theme_constant_override("margin_left", 12 * EDSCALE);
			margin->add_theme_constant_override("margin_top", 10 * EDSCALE);
			margin->add_theme_constant_override("margin_right", 12 * EDSCALE);
			margin->add_theme_constant_override("margin_bottom", 10 * EDSCALE);
			panel->add_child(margin);

			RichTextLabel *content_label = make_text_block(false);
			margin->add_child(content_label);

			row->add_child(panel);
			wrapper->add_child(row);

			entry.panel = panel;
			entry.content_label = content_label;
			entry.body = row;
		} break;

		case TimelineEntry::KIND_ASSISTANT: {
			VBoxContainer *row = memnew(VBoxContainer);
			row->set_h_size_flags(SIZE_EXPAND_FILL);
			row->add_theme_constant_override("separation", 4 * EDSCALE);

			Label *thinking_log = memnew(Label);
			thinking_log->set_h_size_flags(SIZE_EXPAND_FILL);
			thinking_log->set_clip_text(true);
			row->add_child(thinking_log);

			PanelContainer *panel = memnew(PanelContainer);
			MarginContainer *margin = memnew(MarginContainer);
			margin->add_theme_constant_override("margin_left", 12 * EDSCALE);
			margin->add_theme_constant_override("margin_top", 10 * EDSCALE);
			margin->add_theme_constant_override("margin_right", 12 * EDSCALE);
			margin->add_theme_constant_override("margin_bottom", 10 * EDSCALE);
			panel->add_child(margin);

			VBoxContainer *content_column = memnew(VBoxContainer);
			content_column->set_h_size_flags(SIZE_EXPAND_FILL);
			content_column->add_theme_constant_override("separation", 0);
			margin->add_child(content_column);

			AIStreamPreview *stream_preview = memnew(AIStreamPreview);
			stream_preview->set_visible(false);
			content_column->add_child(stream_preview);

			RichTextLabel *content_label = make_text_block(false);
			content_column->add_child(content_label);

			HBoxContainer *inline_action_row = memnew(HBoxContainer);
			inline_action_row->set_h_size_flags(SIZE_EXPAND_FILL);
			inline_action_row->add_theme_constant_override("separation", (int)Math::round(6.0f * EDSCALE));
			inline_action_row->set_visible(false);
			content_column->add_child(inline_action_row);
			inline_action_row->add_spacer();

			Button *inline_plan_button = memnew(Button);
			inline_plan_button->set_text("Execute Plan");
			inline_plan_button->set_focus_mode(FOCUS_NONE);
			inline_plan_button->set_visible(false);
			inline_plan_button->connect("pressed", callable_mp(this, &AIChatPanel::_on_execute_plan_pressed).bind(p_index));
			inline_action_row->add_child(inline_plan_button);

			row->add_child(panel);
			wrapper->add_child(row);

			entry.thinking_log_label = thinking_log;
			entry.content_panel = panel;
			entry.stream_preview = stream_preview;
			entry.content_label = content_label;
			entry.inline_action_row = inline_action_row;
			entry.inline_plan_button = inline_plan_button;
			entry.body = row;
		} break;

		case TimelineEntry::KIND_TOOL_CARD: {
			PanelContainer *panel = memnew(PanelContainer);
			panel->set_h_size_flags(SIZE_EXPAND_FILL);
			MarginContainer *margin = memnew(MarginContainer);
			margin->add_theme_constant_override("margin_left", 12 * EDSCALE);
			margin->add_theme_constant_override("margin_top", 10 * EDSCALE);
			margin->add_theme_constant_override("margin_right", 12 * EDSCALE);
			margin->add_theme_constant_override("margin_bottom", 10 * EDSCALE);
			panel->add_child(margin);

			VBoxContainer *content = memnew(VBoxContainer);
			content->add_theme_constant_override("separation", 5 * EDSCALE);
			margin->add_child(content);

			Label *title = memnew(Label);
			title->set_autowrap_mode(TextServer::AUTOWRAP_WORD_SMART);
			content->add_child(title);

			Label *secondary = memnew(Label);
			secondary->set_autowrap_mode(TextServer::AUTOWRAP_WORD_SMART);
			content->add_child(secondary);

			RichTextLabel *details = make_text_block(true);
			content->add_child(details);

			RichTextLabel *output = make_text_block(true);
			content->add_child(output);

			HBoxContainer *footer = memnew(HBoxContainer);
			footer->add_theme_constant_override("separation", 6 * EDSCALE);
			Label *footer_left = memnew(Label);
			Label *footer_right = memnew(Label);
			footer->add_child(footer_left);
			footer->add_spacer();
			footer->add_child(footer_right);
			content->add_child(footer);

			wrapper->add_child(panel);

			entry.panel = panel;
			entry.title_label = title;
			entry.secondary_label = secondary;
			entry.details_label = details;
			entry.output_label = output;
			entry.footer_row = footer;
			entry.footer_left_label = footer_left;
			entry.footer_right_label = footer_right;
			entry.body = panel;
		} break;

		case TimelineEntry::KIND_ACTIVITY:
		case TimelineEntry::KIND_SYSTEM:
		case TimelineEntry::KIND_ERROR: {
			VBoxContainer *row = memnew(VBoxContainer);
			row->set_h_size_flags(SIZE_EXPAND_FILL);
			row->add_theme_constant_override("separation", 1 * EDSCALE);

			Label *title = memnew(Label);
			title->set_autowrap_mode(TextServer::AUTOWRAP_WORD_SMART);
			row->add_child(title);

			Label *secondary = memnew(Label);
			secondary->set_autowrap_mode(TextServer::AUTOWRAP_WORD_SMART);
			row->add_child(secondary);

			wrapper->add_child(row);

			entry.title_label = title;
			entry.secondary_label = secondary;
			entry.body = row;
		} break;
	}

	entry.root = wrapper;
	if (entry.root) {
		entry.root->add_theme_constant_override("minimum_character_width", 0);
	}

	_update_entry_visuals(p_index);
	_apply_theme();
	if (p_animate_in) {
		_animate_entry_in(p_index);
	}
}

void AIChatPanel::_animate_entry_in(int p_index) {
	ERR_FAIL_INDEX(p_index, transcript.size());

	TimelineEntry &entry = transcript.write[p_index];
	if (!entry.root || !entry.body || !is_inside_tree()) {
		return;
	}
	if (entry.insert_tween.is_valid()) {
		entry.insert_tween->kill();
	}

	const float target_height = MAX((float)entry.body->get_combined_minimum_size().y, MAX((float)entry.body->get_minimum_size().y, 1.0f));
	_set_control_height(0.0f, entry.root);
	_set_control_opacity(0.0f, entry.body);

	entry.insert_tween = entry.root->create_tween();
	entry.insert_tween->set_parallel(true);
	entry.insert_tween->set_trans(Tween::TRANS_CUBIC);
	entry.insert_tween->set_ease(Tween::EASE_OUT);
	entry.insert_tween->tween_property(entry.root, NodePath("custom_minimum_size"), Size2(0, target_height), ENTRY_REVEAL_DURATION);
	Color body_target_modulate = entry.body->get_self_modulate();
	body_target_modulate.a = 1.0f;
	entry.insert_tween->tween_property(entry.body, NodePath("self_modulate"), body_target_modulate, ENTRY_FADE_DURATION);
	entry.insert_tween->chain()->tween_callback(callable_mp(entry.root, &Control::set_custom_minimum_size).bind(Size2()));
}

void AIChatPanel::_animate_entry_out(Control *p_wrapper, Control *p_body) {
	if (!p_wrapper || !p_body || !is_inside_tree()) {
		if (p_wrapper) {
			p_wrapper->queue_free();
		}
		return;
	}

	const float start_height = MAX((float)p_wrapper->get_size().y, MAX((float)p_body->get_combined_minimum_size().y, 1.0f));
	_set_control_height(start_height, p_wrapper);

	Ref<Tween> tween = p_wrapper->create_tween();
	tween->set_parallel(true);
	tween->set_trans(Tween::TRANS_CUBIC);
	tween->set_ease(Tween::EASE_OUT);
	tween->tween_property(p_wrapper, NodePath("custom_minimum_size"), Size2(0, 0), ENTRY_REVEAL_DURATION);
	Color body_target_modulate = p_body->get_self_modulate();
	body_target_modulate.a = 0.0f;
	tween->tween_property(p_body, NodePath("self_modulate"), body_target_modulate, ENTRY_FADE_DURATION);
	tween->chain()->tween_callback(callable_mp(static_cast<Node *>(p_wrapper), &Node::queue_free));
}

void AIChatPanel::_set_control_height(float p_height, Control *p_control) {
	if (!p_control) {
		return;
	}
	p_control->set_custom_minimum_size(Size2(0, MAX(0.0f, p_height)));
}

void AIChatPanel::_clear_control_height(Control *p_control) {
	if (!p_control) {
		return;
	}
	p_control->set_custom_minimum_size(Size2());
}

void AIChatPanel::_set_control_opacity(float p_opacity, Control *p_control) {
	if (!p_control) {
		return;
	}
	Color modulate = p_control->get_self_modulate();
	modulate.a = CLAMP(p_opacity, 0.0f, 1.0f);
	p_control->set_self_modulate(modulate);
}

void AIChatPanel::_start_entry_thinking(TimelineEntry &r_entry, uint64_t p_now) {
	if (r_entry.thinking_started_msec != 0) {
		return;
	}

	r_entry.thinking_started_msec = p_now;
	r_entry.thinking_duration_seconds = -1.0;
}

void AIChatPanel::_stop_entry_thinking(TimelineEntry &r_entry, uint64_t p_now) {
	if (r_entry.thinking_started_msec == 0) {
		return;
	}

	if (p_now >= r_entry.thinking_started_msec) {
		r_entry.accumulated_thinking_msec += p_now - r_entry.thinking_started_msec;
	}
	r_entry.thinking_started_msec = 0;
	r_entry.thinking_duration_seconds = (double)r_entry.accumulated_thinking_msec / 1000.0;
}

void AIChatPanel::_finalize_entry_thinking(TimelineEntry &r_entry, uint64_t p_now) {
	if (r_entry.thinking_started_msec != 0) {
		_stop_entry_thinking(r_entry, p_now);
	}

	if (r_entry.thinking_content.is_empty()) {
		r_entry.thinking_phase_finished = false;
		r_entry.thinking_duration_seconds = -1.0;
		return;
	}

	r_entry.thinking_phase_finished = true;
	if (r_entry.accumulated_thinking_msec > 0) {
		r_entry.thinking_duration_seconds = (double)r_entry.accumulated_thinking_msec / 1000.0;
		return;
	}

	if (r_entry.thinking_duration_seconds < 0.0 && r_entry.started_msec > 0 && p_now >= r_entry.started_msec) {
		r_entry.thinking_duration_seconds = (double)(p_now - r_entry.started_msec) / 1000.0;
	}
}

double AIChatPanel::_get_entry_thinking_seconds(const TimelineEntry &p_entry, uint64_t p_now) const {
	if (p_entry.thinking_duration_seconds >= 0.0) {
		return p_entry.thinking_duration_seconds;
	}

	uint64_t total_msec = p_entry.accumulated_thinking_msec;
	if (p_entry.thinking_started_msec != 0 && p_now >= p_entry.thinking_started_msec) {
		total_msec += p_now - p_entry.thinking_started_msec;
	}
	return (double)total_msec / 1000.0;
}

void AIChatPanel::_update_action_slot_state(bool p_busy, bool p_animate) {
	action_slot_busy = p_busy;
	if (!send_button_slot || !cancel_button_slot) {
		return;
	}

	if (composer_action_tween.is_valid()) {
		composer_action_tween->kill();
	}

	Control *show_slot = p_busy ? (Control *)cancel_button_slot : (Control *)send_button_slot;
	Control *hide_slot = p_busy ? (Control *)send_button_slot : (Control *)cancel_button_slot;

	if (!p_animate || !is_inside_tree()) {
		show_slot->set_visible(true);
		hide_slot->set_visible(false);
		_set_control_opacity(1.0f, show_slot);
		_set_control_opacity(0.0f, hide_slot);
		return;
	}

	show_slot->set_visible(true);
	_set_control_opacity(0.0f, show_slot);
	_set_control_opacity(1.0f, hide_slot);

	composer_action_tween = composer_action_slot->create_tween();
	composer_action_tween->set_parallel(true);
	composer_action_tween->set_trans(Tween::TRANS_CUBIC);
	composer_action_tween->set_ease(Tween::EASE_OUT);
	Color show_target_modulate = show_slot->get_self_modulate();
	show_target_modulate.a = 1.0f;
	composer_action_tween->tween_property(show_slot, NodePath("self_modulate"), show_target_modulate, ENTRY_FADE_DURATION);
	Color hide_target_modulate = hide_slot->get_self_modulate();
	hide_target_modulate.a = 0.0f;
	composer_action_tween->tween_property(hide_slot, NodePath("self_modulate"), hide_target_modulate, ENTRY_FADE_DURATION);
	composer_action_tween->chain()->tween_callback(callable_mp(static_cast<CanvasItem *>(hide_slot), &CanvasItem::set_visible).bind(false));
}

void AIChatPanel::_update_entry_visuals(int p_index) {
	if (p_index < 0 || p_index >= transcript.size()) {
		return;
	}

	TimelineEntry &entry = transcript.write[p_index];
	if (!entry.root) {
		return;
	}

	const Color strong = get_theme_color("font_color", EditorStringName(Editor));
	const Color muted = get_theme_color("font_placeholder_color", EditorStringName(Editor));
	const Color background = get_theme_color("dark_color_1", EditorStringName(Editor));
	const Color surface = get_theme_color("dark_color_2", EditorStringName(Editor));
	const Color error = get_theme_color("error_color", EditorStringName(Editor));
	const int small_radius = (int)Math::round(9.0f * EDSCALE);
	const int medium_radius = (int)Math::round(11.0f * EDSCALE);
	const uint64_t now = OS::get_singleton()->get_ticks_msec();

	auto make_style = [&](const Color &p_fill, const Color &p_border, int p_radius) {
		Ref<StyleBoxFlat> style;
		style.instantiate();
		style->set_bg_color(p_fill);
		style->set_border_color(p_border);
		style->set_border_width_all(1);
		style->set_corner_radius_all(p_radius);
		return style;
	};

	switch (entry.kind) {
		case TimelineEntry::KIND_USER: {
			if (entry.panel) {
				entry.panel->add_theme_style_override("panel", make_style(background.lerp(surface, 0.36f), strong.lerp(surface, 0.92f), medium_radius));
			}
			if (entry.content_label) {
				entry.content_label->set_text("[color=#" + strong.to_html(false) + "]" + _escape_bbcode(entry.content) + "[/color]");
			}
		} break;

		case TimelineEntry::KIND_ASSISTANT: {
			const bool has_thinking = !entry.thinking_content.is_empty();
			const bool has_content = !entry.content.is_empty();
			const bool has_stream_preview = entry.stream_preview && entry.stream_preview->has_content();
			const bool show_pending_placeholder = entry.is_pending && !has_content && !has_stream_preview;
			const bool show_stream_view = entry.is_pending && has_stream_preview;
			if (entry.thinking_log_label) {
				const double duration = _get_entry_thinking_seconds(entry, now);
				entry.thinking_log_label->set_visible(entry.is_pending || has_thinking);
				entry.thinking_log_label->set_text(String((entry.is_pending && !entry.thinking_phase_finished) ? "Thinking for " : "Thought for ") + _seconds_label(duration));
				entry.thinking_log_label->add_theme_color_override("font_color", muted.lerp(strong, 0.18f));
			}
			if (entry.content_panel) {
				entry.content_panel->set_visible(has_content || has_stream_preview || show_pending_placeholder);
				entry.content_panel->add_theme_style_override("panel", make_style(background.lerp(surface, 0.22f), strong.lerp(surface, 0.93f), small_radius));
			}
			if (entry.stream_preview) {
				Ref<Font> preview_font = entry.content_label ? entry.content_label->get_theme_font(SNAME("normal_font")) : get_theme_font(SNAME("normal_font"), SNAME("RichTextLabel"));
				int preview_font_size = entry.content_label ? entry.content_label->get_theme_font_size(SNAME("normal_font_size")) : get_theme_font_size(SNAME("normal_font_size"), SNAME("RichTextLabel"));
				float preview_line_spacing = entry.content_label ? (float)entry.content_label->get_theme_constant(SNAME("line_separation")) : (float)get_theme_constant(SNAME("line_separation"), SNAME("RichTextLabel"));
				entry.stream_preview->configure(preview_font, preview_font_size, preview_line_spacing, strong);
				entry.stream_preview->set_visible(show_stream_view);
			}
			if (entry.content_label) {
				entry.content_label->set_visible((has_content || show_pending_placeholder) && !show_stream_view);
				if (show_pending_placeholder) {
					entry.content_label->set_text("[color=#" + muted.to_html(false) + "]Thinking...[/color]");
				} else {
					entry.content_label->set_text("[color=#" + strong.to_html(false) + "]" + _escape_bbcode(entry.content) + "[/color]");
				}
				entry.content_label->set_visible_characters(-1);
			}
			if (entry.inline_action_row) {
				const bool show_inline_action = entry.can_execute_plan && session.is_valid() && !session->is_busy() && !entry.is_pending && has_content;
				entry.inline_action_row->set_visible(show_inline_action);
			}
			if (entry.inline_plan_button) {
				const bool show_inline_action = entry.can_execute_plan && session.is_valid() && !session->is_busy() && !entry.is_pending && has_content;
				entry.inline_plan_button->set_visible(show_inline_action);
				entry.inline_plan_button->set_disabled(!show_inline_action);
			}
		} break;

		case TimelineEntry::KIND_TOOL_CARD: {
			if (entry.panel) {
				entry.panel->add_theme_style_override("panel", make_style(background.lerp(surface, 0.26f), strong.lerp(surface, 0.92f), small_radius));
			}
			if (entry.title_label) {
				entry.title_label->set_text(entry.title);
				entry.title_label->add_theme_color_override("font_color", strong);
			}
			if (entry.secondary_label) {
				entry.secondary_label->set_text(entry.secondary_text);
				entry.secondary_label->set_visible(!entry.secondary_text.is_empty());
				entry.secondary_label->add_theme_color_override("font_color", muted.lerp(strong, 0.08f));
			}
			if (entry.details_label) {
				entry.details_label->set_visible(!entry.content.is_empty());
				entry.details_label->set_text("[color=#" + muted.to_html(false) + "][code]" + _escape_bbcode(entry.content) + "[/code][/color]");
			}
			if (entry.output_label) {
				entry.output_label->set_visible(!entry.footer_left.is_empty());
				entry.output_label->set_text("[color=#" + strong.to_html(false) + "][code]" + _escape_bbcode(entry.footer_left) + "[/code][/color]");
			}
			if (entry.footer_left_label) {
				entry.footer_left_label->set_text(entry.tool_call_id.is_empty() ? "" : entry.tool_call_id);
				entry.footer_left_label->add_theme_color_override("font_color", muted);
			}
			if (entry.footer_right_label) {
				entry.footer_right_label->set_text(entry.footer_right);
				entry.footer_right_label->add_theme_color_override("font_color", entry.footer_right == "Failed" ? error : muted.lerp(strong, 0.08f));
			}
			if (entry.footer_row) {
				entry.footer_row->set_visible(!entry.tool_call_id.is_empty() || !entry.footer_right.is_empty());
			}
		} break;

		case TimelineEntry::KIND_SYSTEM:
		case TimelineEntry::KIND_ACTIVITY:
		case TimelineEntry::KIND_ERROR: {
			const Color title_color = entry.kind == TimelineEntry::KIND_ERROR ? error : (entry.kind == TimelineEntry::KIND_SYSTEM ? muted.lerp(strong, 0.45f) : strong);
			if (entry.title_label) {
				entry.title_label->set_text(entry.title);
				entry.title_label->add_theme_color_override("font_color", title_color);
			}
			if (entry.secondary_label) {
				entry.secondary_label->set_visible(!entry.secondary_text.is_empty());
				entry.secondary_label->set_text(entry.secondary_text);
				entry.secondary_label->add_theme_color_override("font_color", muted);
			}
		} break;
	}
}

void AIChatPanel::_flush_active_stream_updates(bool p_force) {
	if (active_assistant_entry < 0 || active_assistant_entry >= transcript.size()) {
		return;
	}

	_flush_entry_stream_updates(active_assistant_entry, p_force);
}

void AIChatPanel::_flush_entry_stream_updates(int p_index, bool p_force) {
	if (p_index < 0 || p_index >= transcript.size()) {
		return;
	}

	TimelineEntry &entry = transcript.write[p_index];
	if (entry.kind != TimelineEntry::KIND_ASSISTANT) {
		return;
	}
	if (!entry.stream_dirty && !p_force) {
		return;
	}

	const uint64_t now = OS::get_singleton()->get_ticks_msec();
	if (!p_force && entry.last_stream_flush_msec != 0 && now - entry.last_stream_flush_msec < STREAM_FLUSH_INTERVAL_MSEC) {
		return;
	}

	if (!p_force && entry.first_visible_chunk_msec != 0 && now - entry.first_visible_chunk_msec < STREAM_WARMUP_MSEC) {
		return;
	}

	bool updated = false;
	if (!entry.pending_visible_stream_delta.is_empty()) {
		String next_slice;
		if (p_force) {
			next_slice = entry.pending_visible_stream_delta;
			entry.pending_visible_stream_delta = "";
		} else {
			const double cadence_seconds = (double)STREAM_FLUSH_INTERVAL_MSEC / 1000.0;
			int preferred_count = CLAMP((int)Math::round(STREAM_TARGET_CHARACTERS_PER_SECOND * cadence_seconds), STREAM_MIN_CHARACTERS_PER_FLUSH, STREAM_MAX_CHARACTERS_PER_FLUSH);
			if (!entry.pending_visible_stream_delta.is_empty()) {
				const int backlog = entry.pending_visible_stream_delta.length();
				const int catch_up_count = (int)Math::ceil((double)(backlog * STREAM_FLUSH_INTERVAL_MSEC) / (double)STREAM_CATCH_UP_WINDOW_MSEC);
				preferred_count = MAX(preferred_count, catch_up_count);
			}
			next_slice = _take_stream_slice(entry.pending_visible_stream_delta, preferred_count);
		}

		if (!next_slice.is_empty()) {
			_append_stream_preview_text(p_index, next_slice);
			updated = true;
		}
	}

	entry.stream_dirty = !entry.pending_visible_stream_delta.is_empty();
	entry.last_stream_flush_msec = now;
	if (updated || p_force) {
		_update_entry_visuals(p_index);
	}
	if (_should_autoscroll() && entry.stream_should_autoscroll && entry.root) {
		_maybe_autoscroll(entry.root);
		entry.stream_should_autoscroll = false;
	}
}

void AIChatPanel::_refresh_active_runtime_state() {
	if (active_assistant_entry < 0 || active_assistant_entry >= transcript.size()) {
		return;
	}

	const uint64_t now = OS::get_singleton()->get_ticks_msec();
	if (last_runtime_state_refresh_msec != 0 && now - last_runtime_state_refresh_msec < RUNTIME_REFRESH_INTERVAL_MSEC) {
		return;
	}
	last_runtime_state_refresh_msec = now;

	const TimelineEntry &entry = transcript[active_assistant_entry];
	if (entry.kind != TimelineEntry::KIND_ASSISTANT || !entry.thinking_log_label || entry.thinking_duration_seconds >= 0.0 || (!entry.is_pending && entry.thinking_content.is_empty())) {
		return;
	}

	const double duration = _get_entry_thinking_seconds(entry, now);
	entry.thinking_log_label->set_text(String((entry.is_pending && !entry.thinking_phase_finished) ? "Thinking for " : "Thought for ") + _seconds_label(duration));
}

void AIChatPanel::_reset_entry_stream_preview(int p_index) {
	if (p_index < 0 || p_index >= transcript.size()) {
		return;
	}

	TimelineEntry &entry = transcript.write[p_index];
	if (!entry.stream_preview) {
		return;
	}

	entry.stream_preview->clear_preview();
	entry.stream_preview->set_visible(false);
}

void AIChatPanel::_finalize_entry_stream_display(int p_index) {
	if (p_index < 0 || p_index >= transcript.size()) {
		return;
	}

	TimelineEntry &entry = transcript.write[p_index];
	if (entry.kind != TimelineEntry::KIND_ASSISTANT) {
		return;
	}

	if (entry.content_label) {
		const Color strong = get_theme_color("font_color", EditorStringName(Editor));
		entry.content_label->set_text("[color=#" + strong.to_html(false) + "]" + _escape_bbcode(entry.content) + "[/color]");
	}
	entry.pending_visible_stream_delta = "";
	entry.stream_dirty = false;
	entry.first_visible_chunk_msec = 0;
	_reset_entry_stream_preview(p_index);
	_update_entry_visuals(p_index);
}

void AIChatPanel::_append_stream_preview_text(int p_index, const String &p_text) {
	if (p_index < 0 || p_index >= transcript.size() || p_text.is_empty()) {
		return;
	}

	TimelineEntry &entry = transcript.write[p_index];
	if (!entry.stream_preview) {
		return;
	}

	entry.stream_preview->append_preview_text(p_text);
	entry.stream_preview->set_visible(entry.is_pending);
	if (entry.content_label) {
		entry.content_label->set_visible(false);
	}
}

void AIChatPanel::_clear_executable_plan_entry() {
	if (latest_executable_plan_entry >= 0 && latest_executable_plan_entry < transcript.size()) {
		transcript.write[latest_executable_plan_entry].can_execute_plan = false;
		_update_entry_visuals(latest_executable_plan_entry);
	}
	latest_executable_plan_entry = -1;
}

void AIChatPanel::_set_executable_plan_entry(int p_entry_index) {
	_clear_executable_plan_entry();
	if (p_entry_index < 0 || p_entry_index >= transcript.size()) {
		return;
	}

	TimelineEntry &entry = transcript.write[p_entry_index];
	if (entry.kind != TimelineEntry::KIND_ASSISTANT || entry.content.is_empty()) {
		return;
	}

	entry.can_execute_plan = true;
	latest_executable_plan_entry = p_entry_index;
	_update_entry_visuals(p_entry_index);
}

void AIChatPanel::_on_transcript_scroll_value_changed(double p_value) {
	(void)p_value;
	if (transcript_scroll_updating) {
		return;
	}

	_set_transcript_autoscroll_enabled(_is_near_transcript_bottom());
}

void AIChatPanel::_on_scroll_to_latest_pressed() {
	_set_transcript_autoscroll_enabled(true, true);
}

bool AIChatPanel::_is_near_transcript_bottom() const {
	if (!transcript_scroll || !transcript_scroll->get_v_scroll_bar()) {
		return true;
	}

	const VScrollBar *bar = transcript_scroll->get_v_scroll_bar();
	return bar->get_value() >= (bar->get_max() - bar->get_page() - (24 * EDSCALE));
}

bool AIChatPanel::_should_autoscroll() const {
	return transcript_autoscroll_enabled;
}

void AIChatPanel::_maybe_autoscroll(Control *p_focus_control) {
	if (!_should_autoscroll()) {
		return;
	}

	if (!transcript_scroll) {
		return;
	}

	(void)p_focus_control;
	_scroll_transcript_to_bottom();
}

void AIChatPanel::_scroll_transcript_to_bottom() {
	if (!transcript_scroll || !transcript_scroll->get_v_scroll_bar()) {
		return;
	}

	transcript_scroll_updating = true;
	transcript_scroll->set_v_scroll((int)transcript_scroll->get_v_scroll_bar()->get_max());
	transcript_scroll_updating = false;
	_refresh_scroll_to_latest_button();
}

void AIChatPanel::_set_transcript_autoscroll_enabled(bool p_enabled, bool p_scroll_now) {
	transcript_autoscroll_enabled = p_enabled;
	if (!p_enabled) {
		for (int i = 0; i < transcript.size(); i++) {
			transcript.write[i].stream_should_autoscroll = false;
		}
	}
	if (p_enabled && p_scroll_now) {
		_scroll_transcript_to_bottom();
	}
	_refresh_scroll_to_latest_button();
}

void AIChatPanel::_refresh_scroll_to_latest_button() {
	if (!scroll_to_latest_button) {
		return;
	}

	const bool show_button = current_tab == 0 && !transcript.is_empty() && !transcript_autoscroll_enabled;
	scroll_to_latest_button->set_visible(show_button);
}

void AIChatPanel::_remove_entry(int p_index) {
	if (p_index < 0 || p_index >= transcript.size()) {
		return;
	}

	Control *root = transcript[p_index].root;
	Control *body = transcript[p_index].body;
	transcript.remove_at(p_index);

	HashMap<String, int> updated_indices;
	for (const KeyValue<String, int> &E : tool_entry_indices) {
		if (E.value == p_index) {
			continue;
		}
		updated_indices.insert(E.key, E.value > p_index ? E.value - 1 : E.value);
	}
	tool_entry_indices = updated_indices;

	if (active_assistant_entry == p_index) {
		active_assistant_entry = -1;
	} else if (active_assistant_entry > p_index) {
		active_assistant_entry--;
	}
	if (latest_executable_plan_entry == p_index) {
		latest_executable_plan_entry = -1;
	} else if (latest_executable_plan_entry > p_index) {
		latest_executable_plan_entry--;
	}

	_refresh_empty_state();
	_animate_entry_out(root, body);
}

int AIChatPanel::_add_user_entry(const String &p_text) {
	TimelineEntry entry;
	entry.kind = TimelineEntry::KIND_USER;
	entry.content = p_text;
	transcript.push_back(entry);
	_create_entry_ui(transcript.size() - 1, true);
	_refresh_empty_state();
	return transcript.size() - 1;
}

int AIChatPanel::_ensure_assistant_entry(bool p_streaming) {
	if (active_assistant_entry != -1 && active_assistant_entry < transcript.size()) {
		TimelineEntry &active_entry = transcript.write[active_assistant_entry];
		active_entry.is_pending = p_streaming;
		if (p_streaming) {
			_start_entry_thinking(active_entry, OS::get_singleton()->get_ticks_msec());
		}
		return active_assistant_entry;
	}

	TimelineEntry entry;
	entry.kind = TimelineEntry::KIND_ASSISTANT;
	entry.is_pending = p_streaming;
	entry.thinking_phase_finished = false;
	entry.thinking_duration_seconds = -1.0;
	entry.thinking_started_msec = 0;
	entry.accumulated_thinking_msec = 0;
	entry.started_msec = pending_assistant_started_msec != 0 ? pending_assistant_started_msec : OS::get_singleton()->get_ticks_msec();
	transcript.push_back(entry);
	active_assistant_entry = transcript.size() - 1;
	last_runtime_state_refresh_msec = 0;
	if (p_streaming) {
		_start_entry_thinking(transcript.write[active_assistant_entry], transcript[active_assistant_entry].started_msec);
	}
	_create_entry_ui(active_assistant_entry, true);
	_refresh_empty_state();
	return active_assistant_entry;
}

int AIChatPanel::_add_activity_entry(TimelineEntry::Kind p_kind, const String &p_title, const String &p_secondary, const String &p_tool_name, const String &p_tool_call_id) {
	TimelineEntry entry;
	entry.kind = p_kind;
	entry.title = p_title;
	entry.secondary_text = p_secondary;
	entry.tool_name = p_tool_name;
	entry.tool_call_id = p_tool_call_id;
	entry.footer_right = p_kind == TimelineEntry::KIND_ERROR ? "Failed" : "";
	transcript.push_back(entry);
	_create_entry_ui(transcript.size() - 1, true);
	_refresh_empty_state();
	return transcript.size() - 1;
}

int AIChatPanel::_add_tool_card_entry(const String &p_tool_name, const Dictionary &p_args, const String &p_tool_call_id) {
	TimelineEntry entry;
	entry.kind = TimelineEntry::KIND_TOOL_CARD;
	entry.title = "Ran " + _humanize_tool_name(p_tool_name);
	entry.secondary_text = _primary_tool_target(p_args);
	entry.content = _format_tool_arguments(p_args);
	entry.footer_right = "Running";
	entry.tool_name = p_tool_name;
	entry.tool_call_id = p_tool_call_id;
	entry.arguments = p_args;
	transcript.push_back(entry);
	_create_entry_ui(transcript.size() - 1, true);
	_refresh_empty_state();
	return transcript.size() - 1;
}

void AIChatPanel::_finalize_active_assistant_entry(const Ref<AIMessage> &p_message) {
	const bool has_visible_content = !p_message->get_content().is_empty();
	const bool has_thinking_content = !p_message->get_thinking_content().is_empty();
	if (active_assistant_entry == -1 && !has_visible_content && !has_thinking_content) {
		pending_assistant_started_msec = 0;
		return;
	}

	const int entry_index = _ensure_assistant_entry(false);
	TimelineEntry &entry = transcript.write[entry_index];
	entry.content = p_message->get_content();
	entry.thinking_content = p_message->get_thinking_content();
	entry.is_pending = false;
	_finalize_entry_thinking(entry, OS::get_singleton()->get_ticks_msec());
	_flush_entry_stream_updates(entry_index, true);
	_finalize_entry_stream_display(entry_index);
	if (entry.duration_seconds < 0.0) {
		entry.duration_seconds = (OS::get_singleton()->get_ticks_msec() - entry.started_msec) / 1000.0;
	}
	_update_entry_visuals(entry_index);

	if (!has_visible_content && !has_thinking_content) {
		_remove_entry(entry_index);
	} else {
		active_assistant_entry = -1;
	}
	pending_assistant_started_msec = 0;
}

String AIChatPanel::_humanize_tool_name(const String &p_tool_name) const {
	PackedStringArray parts = p_tool_name.split("_");
	for (int i = 0; i < parts.size(); i++) {
		if (!parts[i].is_empty()) {
			parts.write[i] = parts[i].substr(0, 1).to_upper() + parts[i].substr(1);
		}
	}
	return String(" ").join(parts);
}

String AIChatPanel::_format_tool_arguments(const Dictionary &p_args) const {
	if (p_args.is_empty()) {
		return "{}";
	}
	return JSON::stringify(p_args, "  ");
}

String AIChatPanel::_format_tool_result(const Variant &p_result) const {
	if (p_result.get_type() == Variant::STRING) {
		return p_result;
	}
	return JSON::stringify(p_result, "  ");
}

String AIChatPanel::_summarize_tool_result(const Variant &p_result) const {
	String text = _format_tool_result(p_result).strip_edges();
	PackedStringArray lines = text.split("\n");
	for (int i = 0; i < lines.size(); i++) {
		const String line = lines[i].strip_edges();
		if (!line.is_empty()) {
			return line.substr(0, 140);
		}
	}
	return text.substr(0, 140);
}

String AIChatPanel::_primary_tool_target(const Dictionary &p_args) const {
	static const char *keys[] = { "path", "node_path", "parent_path", "directory", "from", "to", "query", "pattern", "name", "property" };
	for (const char *key : keys) {
		const String key_name = key;
		if (p_args.has(key_name)) {
			return String(p_args[key_name]);
		}
	}
	return "";
}

String AIChatPanel::_tool_activity_title(const String &p_tool_name, const Dictionary &p_args) const {
	const String target = _primary_tool_target(p_args);
	if (p_tool_name == "read_file" || p_tool_name == "list_directory") {
		return target.is_empty() ? "Analyzed project files" : "Analyzed " + target;
	}
	if (p_tool_name == "search_files" || p_tool_name == "grep_files") {
		return target.is_empty() ? "Searched project files" : "Searched " + target;
	}
	if (p_tool_name == "get_console_output") {
		return "Checked console output";
	}
	if (p_tool_name == "get_performance_metrics") {
		return "Checked performance metrics";
	}
	if (p_tool_name == "get_node_property") {
		return target.is_empty() ? "Checked node property" : "Checked " + target;
	}
	if (p_tool_name == "pause_game") {
		return "Paused running game";
	}
	if (p_tool_name == "resume_game") {
		return "Resumed running game";
	}
	return "Ran " + _humanize_tool_name(p_tool_name);
}

bool AIChatPanel::_tool_prefers_activity_row(const String &p_tool_name) const {
	return p_tool_name == "read_file" ||
			p_tool_name == "list_directory" ||
			p_tool_name == "grep_files" ||
			p_tool_name == "search_files" ||
			p_tool_name == "get_console_output" ||
			p_tool_name == "get_performance_metrics" ||
			p_tool_name == "get_node_property" ||
			p_tool_name == "pause_game" ||
			p_tool_name == "resume_game";
}

void AIChatPanel::_input_gui_input(const Ref<InputEvent> &p_event) {
	Ref<InputEventKey> key = p_event;
	if (key.is_valid() && key->is_pressed() && !key->is_echo()) {
		const Key keycode = key->get_keycode();
		const bool is_enter = keycode == Key::ENTER || keycode == Key::KP_ENTER;
		if (!is_enter) {
			return;
		}

		if (key->is_shift_pressed() && !key->is_command_or_control_pressed()) {
			return;
		}

		if (key->is_command_or_control_pressed() || !key->is_shift_pressed()) {
			_send_message();
			input_field->accept_event();
		}
	}
}

#endif // TOOLS_ENABLED
