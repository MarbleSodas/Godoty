/**************************************************************************/
/*  anthropic_provider.h                                                  */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "ai_provider.h"

class AnthropicProvider : public AIProvider {
	GDCLASS(AnthropicProvider, AIProvider);

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
	// Anthropic uses a different message format — extract system prompt separately.
	String _extract_system_prompt(const TypedArray<Ref<AIMessage>> &p_messages) const;
	TypedArray<Dictionary> _format_messages_anthropic(const TypedArray<Ref<AIMessage>> &p_messages) const;
	// Convert OpenAI-style tool schemas to Anthropic format.
	TypedArray<Dictionary> _convert_tools_to_anthropic(const TypedArray<Dictionary> &p_tools) const;

	bool cancel_requested = false;

public:
	AnthropicProvider();
};
