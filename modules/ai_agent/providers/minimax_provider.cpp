/**************************************************************************/
/*  minimax_provider.cpp                                                  */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "minimax_provider.h"
#include "core/io/json.h"

void MiniMaxProvider::_bind_methods() {
	// MiniMax uses OpenAI-compatible format, no additional methods needed.
}

MiniMaxProvider::MiniMaxProvider() {
	model_name = "MiniMax-M1";
	base_url = "https://api.minimax.chat/v1";
}

String MiniMaxProvider::_role_to_string(AIMessage::Role p_role) const {
	switch (p_role) {
		case AIMessage::ROLE_SYSTEM:
			return "system";
		case AIMessage::ROLE_USER:
			return "user";
		case AIMessage::ROLE_ASSISTANT:
			return "assistant";
		case AIMessage::ROLE_TOOL:
			return "tool";
	}
	return "user";
}

TypedArray<Dictionary> MiniMaxProvider::_format_messages(const TypedArray<Ref<AIMessage>> &p_messages) const {
	TypedArray<Dictionary> formatted;
	for (int i = 0; i < p_messages.size(); i++) {
		Ref<AIMessage> msg = p_messages[i];
		if (msg.is_null()) {
			continue;
		}
		Dictionary msg_dict;
		msg_dict["role"] = _role_to_string(msg->get_role());
		msg_dict["content"] = msg->get_content();

		if (msg->has_tool_calls()) {
			msg_dict["tool_calls"] = msg->get_tool_calls();
		}
		if (!msg->get_tool_call_id().is_empty()) {
			msg_dict["tool_call_id"] = msg->get_tool_call_id();
		}
		formatted.push_back(msg_dict);
	}
	return formatted;
}

Dictionary MiniMaxProvider::format_request(
		const TypedArray<Ref<AIMessage>> &p_messages,
		const TypedArray<Dictionary> &p_tools) const {
	// MiniMax uses OpenAI-compatible Chat Completions format.
	Dictionary request;
	request["model"] = model_name;
	request["messages"] = _format_messages(p_messages);

	if (p_tools.size() > 0) {
		request["tools"] = p_tools;
		request["tool_choice"] = "auto";
	}

	return request;
}

Ref<AIMessage> MiniMaxProvider::parse_response(const Dictionary &p_response) const {
	// MiniMax returns OpenAI-compatible response format.
	if (!p_response.has("choices")) {
		return Ref<AIMessage>();
	}

	Array choices = p_response["choices"];
	if (choices.size() == 0) {
		return Ref<AIMessage>();
	}

	Dictionary choice = choices[0];
	if (!choice.has("message")) {
		return Ref<AIMessage>();
	}

	Dictionary msg = choice["message"];
	String content = msg.get("content", "");
	TypedArray<Dictionary> tool_calls;

	if (msg.has("tool_calls")) {
		tool_calls = (TypedArray<Dictionary>)msg["tool_calls"];
	}

	return AIMessage::create_assistant(content, tool_calls);
}

Ref<AIMessage> MiniMaxProvider::_parse_stream_chunk(const String &p_chunk) const {
	// SSE format, same as OpenAI: "data: {...}\n\n"
	String data = p_chunk.strip_edges();
	if (data.begins_with("data: ")) {
		data = data.substr(6);
	}
	if (data == "[DONE]" || data.is_empty()) {
		return Ref<AIMessage>();
	}

	JSON json;
	Error err = json.parse(data);
	if (err != OK) {
		return Ref<AIMessage>();
	}

	Dictionary response = json.get_data();
	if (!response.has("choices")) {
		return Ref<AIMessage>();
	}

	Array choices = response["choices"];
	if (choices.size() == 0) {
		return Ref<AIMessage>();
	}

	Dictionary choice = choices[0];
	Dictionary delta = choice.get("delta", Dictionary());
	String content = delta.get("content", "");

	Ref<AIMessage> msg = AIMessage::create_assistant(content);
	if (delta.has("tool_calls")) {
		msg->set_tool_calls(delta["tool_calls"]);
	}
	return msg;
}

Error MiniMaxProvider::send_message(
		const TypedArray<Ref<AIMessage>> &p_messages,
		const TypedArray<Dictionary> &p_tools,
		const Callable &p_callback) {
	if (is_busy) {
		return ERR_BUSY;
	}
	if (api_key.is_empty()) {
		return ERR_UNCONFIGURED;
	}

	is_busy = true;
	cancel_requested = false;

	Dictionary request = format_request(p_messages, p_tools);
	String body = JSON::stringify(request);

	// HTTP transport skeleton — endpoint: POST {base_url}/chat/completions
	// Headers: Authorization: Bearer {api_key}, Content-Type: application/json
	// Full implementation will be wired in HTTP integration phase.

	is_busy = false;
	return OK;
}

Error MiniMaxProvider::stream_message(
		const TypedArray<Ref<AIMessage>> &p_messages,
		const TypedArray<Dictionary> &p_tools,
		const Callable &p_stream_callback,
		const Callable &p_complete_callback) {
	if (is_busy) {
		return ERR_BUSY;
	}
	if (api_key.is_empty()) {
		return ERR_UNCONFIGURED;
	}

	is_busy = true;
	cancel_requested = false;

	Dictionary request = format_request(p_messages, p_tools);
	request["stream"] = true;
	String body = JSON::stringify(request);

	// Streaming transport skeleton.
	is_busy = false;
	return OK;
}

void MiniMaxProvider::cancel() {
	cancel_requested = true;
	is_busy = false;
}
