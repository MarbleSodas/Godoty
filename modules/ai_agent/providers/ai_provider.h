/**************************************************************************/
/*  ai_provider.h                                                         */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "core/object/ref_counted.h"
#include "core/variant/dictionary.h"
#include "core/variant/typed_array.h"
#include "modules/ai_agent/ai_message.h"

class HTTPRequest;

class AIProvider : public RefCounted {
	GDCLASS(AIProvider, RefCounted);

protected:
	static void _bind_methods();

	String api_key;
	String base_url;
	String model_name;
	float temperature = 0.7f;
	int max_tokens = 4096;
	bool temperature_override_enabled = true;
	bool max_tokens_override_enabled = true;
	bool is_busy = false;
	HTTPRequest *model_discovery_request = nullptr;
	Callable pending_model_discovery_callback;

	virtual String _get_model_discovery_url() const;
	virtual PackedStringArray _get_model_discovery_headers() const;
	virtual PackedStringArray _parse_model_discovery_response(const Variant &p_response) const;
	void _on_model_discovery_request_completed(int p_result, int p_code, const PackedStringArray &p_headers, const PackedByteArray &p_body);
	void _cleanup_model_discovery_request();

public:
	// Override in subclasses to send messages to the LLM.
	virtual Error send_message(
			const TypedArray<Ref<AIMessage>> &p_messages,
			const TypedArray<Dictionary> &p_tools,
			const Callable &p_callback) = 0;

	// Override in subclasses for streaming responses.
	virtual Error stream_message(
			const TypedArray<Ref<AIMessage>> &p_messages,
			const TypedArray<Dictionary> &p_tools,
			const Callable &p_stream_callback,
			const Callable &p_complete_callback) = 0;

	// Cancel any in-progress request.
	virtual void cancel() = 0;

	void set_api_key(const String &p_key);
	String get_api_key() const;

	void set_base_url(const String &p_url);
	String get_base_url() const;

	void set_model_name(const String &p_name);
	String get_model_name() const;

	void set_temperature(float p_temp);
	float get_temperature() const;
	void clear_temperature_override();
	bool has_temperature_override() const;

	void set_max_tokens(int p_max);
	int get_max_tokens() const;
	void clear_max_tokens_override();
	bool has_max_tokens_override() const;

	bool get_is_busy() const;
	virtual bool supports_model_discovery() const;
	virtual Error request_available_models(const Callable &p_callback);

	// Format messages into the provider-specific request format.
	virtual Dictionary format_request(
			const TypedArray<Ref<AIMessage>> &p_messages,
			const TypedArray<Dictionary> &p_tools) const = 0;

	// Parse the provider-specific response into an AIMessage.
	virtual Ref<AIMessage> parse_response(const Dictionary &p_response) const = 0;

	AIProvider();
	virtual ~AIProvider();
};
