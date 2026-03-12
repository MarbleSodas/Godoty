/**************************************************************************/
/*  openai_provider.h                                                     */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "ai_provider.h"
#include "core/io/http_client.h"

class OpenAIProvider : public AIProvider {
	GDCLASS(OpenAIProvider, AIProvider);

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
	// Convert AIMessage role enum to OpenAI role string.
	String _role_to_string(AIMessage::Role p_role) const;
	// Convert messages array to OpenAI format.
	TypedArray<Dictionary> _format_messages(const TypedArray<Ref<AIMessage>> &p_messages) const;
	// Parse a streaming SSE chunk.
	Ref<AIMessage> _parse_stream_chunk(const String &p_chunk) const;

	Ref<HTTPClient> http_client;
	bool cancel_requested = false;

public:
	OpenAIProvider();
};
