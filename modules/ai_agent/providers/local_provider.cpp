/**************************************************************************/
/*  local_provider.cpp                                                    */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "local_provider.h"
#include "core/io/json.h"

void LocalLLMProvider::_bind_methods() {
	ClassDB::bind_method(D_METHOD("set_use_ollama_format", "ollama"), &LocalLLMProvider::set_use_ollama_format);
	ClassDB::bind_method(D_METHOD("get_use_ollama_format"), &LocalLLMProvider::get_use_ollama_format);
	ClassDB::bind_method(D_METHOD("is_server_available"), &LocalLLMProvider::is_server_available);

	ADD_PROPERTY(PropertyInfo(Variant::BOOL, "use_ollama_format"), "set_use_ollama_format", "get_use_ollama_format");
}

LocalLLMProvider::LocalLLMProvider() {
	model_name = "llama3.1";
	base_url = "http://localhost:11434";
}

void LocalLLMProvider::set_use_ollama_format(bool p_ollama) {
	use_ollama_format = p_ollama;
}

bool LocalLLMProvider::get_use_ollama_format() const {
	return use_ollama_format;
}

bool LocalLLMProvider::is_server_available() const {
	// TODO: Perform a lightweight health check against the local server.
	return false;
}

Dictionary LocalLLMProvider::format_request(
		const TypedArray<Ref<AIMessage>> &p_messages,
		const TypedArray<Dictionary> &p_tools) const {
	Dictionary request;

	if (use_ollama_format) {
		// Ollama /api/chat format.
		request["model"] = model_name;
		TypedArray<Dictionary> msgs;
		for (int i = 0; i < p_messages.size(); i++) {
			Ref<AIMessage> msg = p_messages[i];
			if (msg.is_null()) {
				continue;
			}
			Dictionary m;
			switch (msg->get_role()) {
				case AIMessage::ROLE_SYSTEM:
					m["role"] = "system";
					break;
				case AIMessage::ROLE_USER:
					m["role"] = "user";
					break;
				case AIMessage::ROLE_ASSISTANT:
					m["role"] = "assistant";
					break;
				case AIMessage::ROLE_TOOL:
					m["role"] = "tool";
					break;
			}
			m["content"] = msg->get_content();
			msgs.push_back(m);
		}
		request["messages"] = msgs;
		if (p_tools.size() > 0) {
			request["tools"] = p_tools;
		}
	} else {
		// llama.cpp OpenAI-compatible format — same as OpenAI provider.
		request["model"] = model_name;
		TypedArray<Dictionary> msgs;
		for (int i = 0; i < p_messages.size(); i++) {
			Ref<AIMessage> msg = p_messages[i];
			if (msg.is_null()) {
				continue;
			}
			msgs.push_back(msg->to_dict());
		}
		request["messages"] = msgs;
		if (p_tools.size() > 0) {
			request["tools"] = p_tools;
		}
	}

	return request;
}

Ref<AIMessage> LocalLLMProvider::parse_response(const Dictionary &p_response) const {
	if (use_ollama_format) {
		// Ollama response: {message: {role, content}}
		if (!p_response.has("message")) {
			return Ref<AIMessage>();
		}
		Dictionary msg = p_response["message"];
		return AIMessage::create_assistant(msg.get("content", ""));
	} else {
		// OpenAI-compatible response format.
		if (!p_response.has("choices")) {
			return Ref<AIMessage>();
		}
		Array choices = p_response["choices"];
		if (choices.size() == 0) {
			return Ref<AIMessage>();
		}
		Dictionary choice = choices[0];
		Dictionary msg = choice.get("message", Dictionary());
		return AIMessage::create_assistant(msg.get("content", ""));
	}
}

Error LocalLLMProvider::send_message(
		const TypedArray<Ref<AIMessage>> &p_messages,
		const TypedArray<Dictionary> &p_tools,
		const Callable &p_callback) {
	if (is_busy) {
		return ERR_BUSY;
	}

	is_busy = true;
	cancel_requested = false;

	Dictionary request = format_request(p_messages, p_tools);
	request["stream"] = false;
	String body = JSON::stringify(request);

	// HTTP transport skeleton.
	is_busy = false;
	return OK;
}

Error LocalLLMProvider::stream_message(
		const TypedArray<Ref<AIMessage>> &p_messages,
		const TypedArray<Dictionary> &p_tools,
		const Callable &p_stream_callback,
		const Callable &p_complete_callback) {
	if (is_busy) {
		return ERR_BUSY;
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

void LocalLLMProvider::cancel() {
	cancel_requested = true;
	is_busy = false;
}
