/**************************************************************************/
/*  local_provider.h                                                      */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "ai_provider.h"
#include "core/os/thread.h"
#include "core/templates/safe_refcount.h"

class HTTPRequest;

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
	bool supports_model_discovery() const override;
	Error request_available_models(const Callable &p_callback) override;

	Dictionary format_request(
			const TypedArray<Ref<AIMessage>> &p_messages,
			const TypedArray<Dictionary> &p_tools) const override;

	Ref<AIMessage> parse_response(const Dictionary &p_response) const override;

	// Check if local server is running and reachable.
	bool is_server_available() const;

	void set_use_ollama_format(bool p_ollama);
	bool get_use_ollama_format() const;

	LocalLLMProvider();
	~LocalLLMProvider();

private:
	String _get_model_discovery_url() const override;
	PackedStringArray _get_model_discovery_headers() const override;
	PackedStringArray _parse_model_discovery_response(const Variant &p_response) const override;
	Ref<AIMessage> _parse_stream_chunk(const String &p_chunk) const;
	void _on_request_completed(int p_result, int p_code,
			const PackedStringArray &p_headers, const PackedByteArray &p_body);
	void _dispatch_stream_chunk(const String &p_text);
	void _dispatch_stream_complete(const String &p_content, const TypedArray<Dictionary> &p_tool_calls);
	void _dispatch_stream_error(const String &p_error);
	static void _stream_request_thread(void *p_userdata);
	void _wait_for_thread();
	void _cleanup_request();

	HTTPRequest *http_request = nullptr;
	Callable pending_callback;
	Callable pending_stream_callback;
	Callable pending_complete_callback;

	SafeFlag cancel_requested;
	bool is_streaming = false;
	bool use_ollama_format = true; // vs llama.cpp OpenAI-compatible format.
	Thread request_thread;
};
