/**************************************************************************/
/*  anthropic_provider.h                                                  */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "ai_provider.h"
#include "core/os/thread.h"
#include "core/templates/safe_refcount.h"

class HTTPRequest;

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
	String _extract_system_prompt(const TypedArray<Ref<AIMessage>> &p_messages) const;
	TypedArray<Dictionary> _format_messages_anthropic(const TypedArray<Ref<AIMessage>> &p_messages) const;
	TypedArray<Dictionary> _convert_tools_to_anthropic(const TypedArray<Dictionary> &p_tools) const;

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
	Thread request_thread;

public:
	AnthropicProvider();
	~AnthropicProvider();
};
