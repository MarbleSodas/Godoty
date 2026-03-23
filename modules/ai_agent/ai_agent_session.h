/**************************************************************************/
/*  ai_agent_session.h                                                    */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "ai_agent_config.h"
#include "ai_agent_mode.h"
#include "ai_message.h"
#include "ai_tool_registry.h"
#include "providers/ai_provider.h"
#include "core/object/ref_counted.h"
#include "core/object/class_db.h"

class AIAgentSession : public RefCounted {
	GDCLASS(AIAgentSession, RefCounted);

public:
	enum SessionState {
		STATE_IDLE,
		STATE_SENDING,
		STATE_WAITING_FOR_RESPONSE,
		STATE_PROCESSING_TOOL_CALLS,
		STATE_WAITING_FOR_APPROVAL,
		STATE_ERROR,
	};

protected:
	static void _bind_methods();

private:
	struct ParsedAssistantContent {
		String visible_content;
		String thinking_content;
		bool thinking_active = false;
	};

	struct PendingToolCall {
		String tool_call_id;
		String tool_name;
		Dictionary arguments;
	};

	struct SessionSnapshotBatch {
		Dictionary data;
	};

	Ref<AIAgentConfig> config;
	Ref<AIProvider> provider;
	Vector<Ref<AIMessage>> messages;
	Vector<PendingToolCall> pending_tool_calls;
	AIAgentModeId mode = AI_AGENT_MODE_ASK;
	SessionState state = STATE_IDLE;
	int max_tool_iterations = 10; // Prevent infinite tool loops.
	int current_tool_iteration = 0;
	String streaming_raw_content;
	String streaming_visible_content;
	String streaming_thinking_content;
	bool streaming_thinking_active = false;
	String session_id;
	String persisted_summary;
	Vector<SessionSnapshotBatch> snapshot_batches;
	int orchestration_depth = 0;
	int child_tasks_spawned_this_turn = 0;
	bool child_task_active = false;
	PendingToolCall active_child_task_call;
	Ref<AIAgentSession> active_child_session;
	String active_child_result_content;

	// Internal handlers.
	String _build_effective_system_prompt(const ResolvedAgentRunConfig &p_run_config) const;
	String _build_environment_notes(const ResolvedAgentRunConfig &p_run_config) const;
	String _read_project_rules() const;
	bool _has_non_system_history() const;
	Dictionary _build_turn_context(const Dictionary &p_context) const;
	void _append_context_message(TypedArray<Ref<AIMessage>> &r_messages, const String &p_title, const Dictionary &p_context) const;
	ParsedAssistantContent _parse_assistant_content(const String &p_raw_content) const;
	Ref<AIMessage> _sanitize_assistant_message(const Ref<AIMessage> &p_message) const;
	void _reset_streaming_accumulator();
	void _set_streaming_thinking_active(bool p_active);
	void _send_user_message(const String &p_content, const Dictionary &p_context);
	TypedArray<Ref<AIMessage>> _build_request_messages(const Dictionary &p_context = Dictionary()) const;
	TypedArray<Dictionary> _get_enabled_tool_schemas(const ResolvedAgentRunConfig &p_run_config) const;
	void _dispatch_request(const TypedArray<Ref<AIMessage>> &p_messages);
	void _on_response_received(const Ref<AIMessage> &p_response);
	void _on_stream_chunk(const Ref<AIMessage> &p_chunk);
	void _on_stream_complete(const Ref<AIMessage> &p_full_response);
	void _on_error(const String &p_error);
	void _process_tool_calls(const Ref<AIMessage> &p_message);
	void _continue_tool_processing();
	void _append_message(const Ref<AIMessage> &p_message);
	void _autosave_session() const;
	String _ensure_session_id();
	String _get_sessions_dir_path() const;
	String _get_session_save_path() const;
	String _get_tool_results_dir_path() const;
	String _get_snapshot_root_dir_path() const;
	bool _restore_session_from_path(const String &p_path);
	void _maybe_summarize_history();
	int _estimate_history_tokens() const;
	int _estimate_message_tokens(const Ref<AIMessage> &p_message) const;
	String _summarize_messages(const Vector<Ref<AIMessage>> &p_messages) const;
	void _fallback_trim_history();
	Dictionary _write_tool_result_artifact(const String &p_tool_call_id, const Variant &p_result) const;
	Dictionary _capture_snapshot_batch(const PendingToolCall &p_pending) const;
	bool _restore_snapshot_batch(const Dictionary &p_batch);
	void _finalize_tool_result(const PendingToolCall &p_pending, const Variant &p_result, const Dictionary &p_metadata = Dictionary());
	TypedArray<Dictionary> _build_orchestrator_tool_schemas() const;
	bool _is_orchestrator_tool(const String &p_tool_name) const;
	void _start_child_task(const PendingToolCall &p_pending);
	void _on_child_message_received(const Ref<AIMessage> &p_message);
	void _on_child_approval_required(const String &p_tool_name, const Dictionary &p_args, const String &p_tool_call_id);
	void _on_child_error(const String &p_error);
	void _on_child_session_completed();
	void _execute_parallel_read_only_batch();
	bool _tool_requires_user_approval(const String &p_tool_name) const;
	Ref<AIProvider> _create_provider_for_config() const;
	ResolvedAgentRunConfig _resolve_run_config() const;
	void _apply_run_config_to_provider(const ResolvedAgentRunConfig &p_run_config);

public:
	// Configuration.
	void set_config(const Ref<AIAgentConfig> &p_config);
	Ref<AIAgentConfig> get_config() const;
	void set_mode(AIAgentModeId p_mode);
	AIAgentModeId get_mode() const;

	// Session state.
	SessionState get_state() const;
	bool is_busy() const;

	// Conversation management.
	void send_message(const String &p_content);
	void send_message_with_context(const String &p_content, const Dictionary &p_context);
	void add_system_message(const String &p_content);
	void clear_history();
	TypedArray<Dictionary> get_history() const;
	int get_message_count() const;
	String get_session_id() const;
	bool restore_last_saved_session();
	bool has_ai_edit_snapshots() const;
	bool can_undo_last_ai_edit() const;
	bool undo_all_ai_edits();
	bool undo_last_ai_edit();

	// Control.
	void cancel();
	void approve_tool_call(const String &p_tool_call_id);
	void deny_tool_call(const String &p_tool_call_id, const String &p_reason = "");

	// Settings.
	void set_max_tool_iterations(int p_max);
	int get_max_tool_iterations() const;
	void set_orchestration_depth(int p_depth);
	int get_orchestration_depth() const;

	AIAgentSession();
	~AIAgentSession();
};

VARIANT_ENUM_CAST(AIAgentSession::SessionState);
