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

class AIProvider : public RefCounted {
	GDCLASS(AIProvider, RefCounted);

protected:
	static void _bind_methods();

	String api_key;
	String base_url;
	String model_name;
	bool is_busy = false;

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

	bool get_is_busy() const;

	// Format messages into the provider-specific request format.
	virtual Dictionary format_request(
			const TypedArray<Ref<AIMessage>> &p_messages,
			const TypedArray<Dictionary> &p_tools) const = 0;

	// Parse the provider-specific response into an AIMessage.
	virtual Ref<AIMessage> parse_response(const Dictionary &p_response) const = 0;

	AIProvider() {}
	virtual ~AIProvider() {}
};
