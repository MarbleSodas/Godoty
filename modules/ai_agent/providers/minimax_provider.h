/**************************************************************************/
/*  minimax_provider.h                                                    */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "ai_provider.h"

// MiniMax AI provider — OpenAI-compatible Chat Completions API
// with native function calling and interleaved thinking support.
class MiniMaxProvider : public AIProvider {
	GDCLASS(MiniMaxProvider, AIProvider);

protected:
	static void _bind_methods();

public:
	Error send_message(
			const TypedArray<Ref<AIMessage>> &p_messages,
			const TypedArray<Dictionary> &p_tools,
			const Callable &p_callback) override;

	Error stream_message(
			const TypedArray<Ref<AIMessage>> &p_messages,
			const TypedArray<Dictionary> &p_tools,
			const Callable &p_stream_callback,
			const Callable &p_complete_callback) override;

	void cancel() override;

	Dictionary format_request(
			const TypedArray<Ref<AIMessage>> &p_messages,
			const TypedArray<Dictionary> &p_tools) const override;

	Ref<AIMessage> parse_response(const Dictionary &p_response) const override;

private:
	String _role_to_string(AIMessage::Role p_role) const;
	TypedArray<Dictionary> _format_messages(const TypedArray<Ref<AIMessage>> &p_messages) const;
	Ref<AIMessage> _parse_stream_chunk(const String &p_chunk) const;

	bool cancel_requested = false;

public:
	MiniMaxProvider();
};
