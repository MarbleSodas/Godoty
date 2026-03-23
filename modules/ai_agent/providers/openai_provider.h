/**************************************************************************/
/*  openai_provider.h                                                     */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "ai_provider.h"
#include "core/os/thread.h"
#include "core/templates/safe_refcount.h"

class HTTPRequest;

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
	bool supports_model_discovery() const override;
	Error request_available_models(const Callable &p_callback) override;

	Dictionary format_request(
			const TypedArray<Ref<AIMessage>> &p_messages,
			const TypedArray<Dictionary> &p_tools) const override;

	Ref<AIMessage> parse_response(const Dictionary &p_response) const override;

private:
	String _get_model_discovery_url() const override;
	PackedStringArray _get_model_discovery_headers() const override;
	// Convert AIMessage role enum to OpenAI role string.
	String _role_to_string(AIMessage::Role p_role) const;
	// Convert messages array to OpenAI format.
	TypedArray<Dictionary> _format_messages(const TypedArray<Ref<AIMessage>> &p_messages) const;
	// Parse a streaming SSE chunk.
	Ref<AIMessage> _parse_stream_chunk(const String &p_chunk) const;

	// HTTP request completion handler.
	void _on_request_completed(int p_result, int p_code,
			const PackedStringArray &p_headers, const PackedByteArray &p_body);
	void _dispatch_stream_chunk(const String &p_text);
	void _dispatch_stream_complete(const String &p_content, const TypedArray<Dictionary> &p_tool_calls);
	void _dispatch_stream_error(const String &p_error);
	static void _stream_request_thread(void *p_userdata);
	void _wait_for_thread();

	// Clean up the HTTPRequest node.
	void _cleanup_request();

	HTTPRequest *http_request = nullptr;
	Callable pending_callback;
	Callable pending_stream_callback;
	Callable pending_complete_callback;
	SafeFlag cancel_requested;
	bool is_streaming = false;
	Thread request_thread;

public:
	OpenAIProvider();
	~OpenAIProvider();
};
