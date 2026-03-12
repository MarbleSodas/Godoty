/**************************************************************************/
/*  local_provider.h                                                      */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "ai_provider.h"

// Local LLM provider supporting Ollama and llama.cpp server APIs.
class LocalLLMProvider : public AIProvider {
	GDCLASS(LocalLLMProvider, AIProvider);

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

	// Check if local server is running and reachable.
	bool is_server_available() const;

private:
	bool cancel_requested = false;
	bool use_ollama_format = true; // vs llama.cpp OpenAI-compatible format.

public:
	void set_use_ollama_format(bool p_ollama);
	bool get_use_ollama_format() const;

	LocalLLMProvider();
};
