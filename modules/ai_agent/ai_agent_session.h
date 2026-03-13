/**************************************************************************/
/*  ai_agent_session.h                                                    */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "ai_agent_config.h"
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
	struct PendingToolCall {
		String tool_call_id;
		String tool_name;
		Dictionary arguments;
	};

	Ref<AIAgentConfig> config;
	Ref<AIProvider> provider;
	Vector<Ref<AIMessage>> messages;
	Vector<PendingToolCall> pending_tool_calls;
	SessionState state = STATE_IDLE;
	int max_tool_iterations = 10; // Prevent infinite tool loops.
	int current_tool_iteration = 0;

	// Internal handlers.
	void _send_user_message(const String &p_content, const Dictionary &p_context);
	TypedArray<Ref<AIMessage>> _build_request_messages(const Dictionary &p_context = Dictionary()) const;
	TypedArray<Dictionary> _get_enabled_tool_schemas() const;
	void _dispatch_request(const TypedArray<Ref<AIMessage>> &p_messages);
	void _on_response_received(const Ref<AIMessage> &p_response);
	void _on_stream_chunk(const Ref<AIMessage> &p_chunk);
	void _on_stream_complete(const Ref<AIMessage> &p_full_response);
	void _on_error(const String &p_error);
	void _process_tool_calls(const Ref<AIMessage> &p_message);
	void _continue_tool_processing();
	Ref<AIProvider> _create_provider_for_config() const;

public:
	// Configuration.
	void set_config(const Ref<AIAgentConfig> &p_config);
	Ref<AIAgentConfig> get_config() const;

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

	// Control.
	void cancel();
	void approve_tool_call(const String &p_tool_call_id);
	void deny_tool_call(const String &p_tool_call_id, const String &p_reason = "");

	// Settings.
	void set_max_tool_iterations(int p_max);
	int get_max_tool_iterations() const;

	AIAgentSession();
	~AIAgentSession();
};

VARIANT_ENUM_CAST(AIAgentSession::SessionState);
