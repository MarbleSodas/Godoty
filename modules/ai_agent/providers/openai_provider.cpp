/**************************************************************************/
/*  openai_provider.cpp                                                   */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "openai_provider.h"

#include "core/crypto/crypto.h"
#include "core/io/http_client.h"
#include "core/io/json.h"
#include "core/object/message_queue.h"
#include "core/os/os.h"
#include "scene/main/http_request.h"
#include "scene/main/scene_tree.h"
#include "scene/main/window.h"

namespace {
struct ParsedHTTPURL {
	String host;
	int port = 0;
	String path = "/";
	bool use_tls = false;
	bool valid = false;
};

struct PartialOpenAIToolCall {
	String id;
	String name;
	String arguments;
};

struct OpenAIStreamRequestData {
	OpenAIProvider *provider = nullptr;
	String url;
	Vector<String> headers;
	PackedByteArray body;
};

bool pop_sse_event(String &r_buffer, String &r_event) {
	int separator_index = -1;
	int separator_length = 0;

	int lf_index = r_buffer.find("\n\n");
	if (lf_index != -1) {
		separator_index = lf_index;
		separator_length = 2;
	}

	int crlf_index = r_buffer.find("\r\n\r\n");
	if (crlf_index != -1 && (separator_index == -1 || crlf_index < separator_index)) {
		separator_index = crlf_index;
		separator_length = 4;
	}

	if (separator_index == -1) {
		return false;
	}

	r_event = r_buffer.substr(0, separator_index);
	r_buffer = r_buffer.substr(separator_index + separator_length);
	return true;
}

String extract_sse_data(const String &p_event) {
	PackedStringArray lines = p_event.split("\n");
	String data;

	for (int i = 0; i < lines.size(); i++) {
		String line = lines[i].strip_edges();
		if (!line.begins_with("data:")) {
			continue;
		}

		String line_data = line.substr(5).strip_edges(false, true);
		if (!data.is_empty()) {
			data += "\n";
		}
		data += line_data;
	}

	return data;
}

ParsedHTTPURL parse_http_url(const String &p_url) {
	ParsedHTTPURL parsed;
	String work = p_url.strip_edges();
	if (work.begins_with("https://")) {
		parsed.use_tls = true;
		parsed.port = 443;
		work = work.trim_prefix("https://");
	} else if (work.begins_with("http://")) {
		parsed.use_tls = false;
		parsed.port = 80;
		work = work.trim_prefix("http://");
	} else {
		return parsed;
	}

	int slash_pos = work.find("/");
	String host_port = slash_pos == -1 ? work : work.substr(0, slash_pos);
	parsed.path = slash_pos == -1 ? "/" : work.substr(slash_pos);

	int colon_pos = host_port.rfind(":");
	if (colon_pos != -1) {
		parsed.host = host_port.substr(0, colon_pos);
		parsed.port = host_port.substr(colon_pos + 1).to_int();
	} else {
		parsed.host = host_port;
	}

	parsed.valid = !parsed.host.is_empty() && parsed.port > 0;
	return parsed;
}

void merge_openai_tool_call_delta(Vector<PartialOpenAIToolCall> &r_tool_calls, const Array &p_delta_calls) {
	for (int i = 0; i < p_delta_calls.size(); i++) {
		Dictionary delta_call = p_delta_calls[i];
		int index = delta_call.get("index", i);
		while (r_tool_calls.size() <= index) {
			r_tool_calls.push_back(PartialOpenAIToolCall());
		}

		PartialOpenAIToolCall &tool_call = r_tool_calls.write[index];
		String id = delta_call.get("id", "");
		if (!id.is_empty()) {
			tool_call.id = id;
		}

		Dictionary function = delta_call.get("function", Dictionary());
		String name = function.get("name", "");
		if (!name.is_empty()) {
			tool_call.name = name;
		}

		String arguments = function.get("arguments", "");
		if (!arguments.is_empty()) {
			tool_call.arguments += arguments;
		}
	}
}

TypedArray<Dictionary> finalize_openai_tool_calls(const Vector<PartialOpenAIToolCall> &p_tool_calls) {
	TypedArray<Dictionary> tool_calls;
	for (int i = 0; i < p_tool_calls.size(); i++) {
		const PartialOpenAIToolCall &tool_call = p_tool_calls[i];
		if (tool_call.id.is_empty() && tool_call.name.is_empty() && tool_call.arguments.is_empty()) {
			continue;
		}

		Dictionary tc;
		tc["id"] = tool_call.id;
		tc["type"] = "function";

		Dictionary function;
		function["name"] = tool_call.name;
		function["arguments"] = tool_call.arguments;
		tc["function"] = function;
		tool_calls.push_back(tc);
	}

	return tool_calls;
}

String extract_openai_error_message(const String &p_response_text, int p_code) {
	String err_msg = "API error (HTTP " + itos(p_code) + ")";
	JSON json;
	if (json.parse(p_response_text) == OK && json.get_data().get_type() == Variant::DICTIONARY) {
		Dictionary resp = json.get_data();
		if (resp.has("error")) {
			Dictionary error = resp["error"];
			if (error.has("message")) {
				err_msg += ": " + (String)error["message"];
			}
		}
	}
	return err_msg;
}
} // namespace

void OpenAIProvider::_bind_methods() {
	// No additional methods beyond the base class for now.
}

bool OpenAIProvider::supports_model_discovery() const {
	return true;
}

Error OpenAIProvider::request_available_models(const Callable &p_callback) {
	return AIProvider::request_available_models(p_callback);
}

OpenAIProvider::OpenAIProvider() {
	model_name = "gpt-5-mini";
	base_url = "https://api.openai.com/v1";
}

OpenAIProvider::~OpenAIProvider() {
	cancel_requested.set();
	_wait_for_thread();
	_cleanup_request();
}

String OpenAIProvider::_get_model_discovery_url() const {
	return base_url.trim_suffix("/") + "/models";
}

PackedStringArray OpenAIProvider::_get_model_discovery_headers() const {
	PackedStringArray headers;
	headers.push_back("Content-Type: application/json");
	if (!api_key.is_empty()) {
		headers.push_back("Authorization: Bearer " + api_key);
	}
	return headers;
}

String OpenAIProvider::_role_to_string(AIMessage::Role p_role) const {
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

TypedArray<Dictionary> OpenAIProvider::_format_messages(const TypedArray<Ref<AIMessage>> &p_messages) const {
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

Dictionary OpenAIProvider::format_request(
		const TypedArray<Ref<AIMessage>> &p_messages,
		const TypedArray<Dictionary> &p_tools) const {
	Dictionary request;
	request["model"] = model_name;
	request["messages"] = _format_messages(p_messages);
	if (has_temperature_override()) {
		request["temperature"] = temperature;
	}
	if (has_max_tokens_override()) {
		request["max_tokens"] = max_tokens;
	}

	if (p_tools.size() > 0) {
		request["tools"] = p_tools;
		request["tool_choice"] = "auto";
	}

	return request;
}

Ref<AIMessage> OpenAIProvider::parse_response(const Dictionary &p_response) const {
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

Ref<AIMessage> OpenAIProvider::_parse_stream_chunk(const String &p_chunk) const {
	// SSE format: "data: {...}\n\n"
	// Strip "data: " prefix.
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

void OpenAIProvider::_cleanup_request() {
	if (http_request) {
		http_request->cancel_request();
		http_request->queue_free();
		http_request = nullptr;
	}
}

void OpenAIProvider::_wait_for_thread() {
	if (request_thread.is_started()) {
		request_thread.wait_to_finish();
	}
}

void OpenAIProvider::_dispatch_stream_chunk(const String &p_text) {
	if (!is_streaming || cancel_requested.is_set() || p_text.is_empty()) {
		return;
	}

	if (pending_stream_callback.is_valid()) {
		pending_stream_callback.call(AIMessage::create_assistant(p_text));
	}
}

void OpenAIProvider::_dispatch_stream_complete(const String &p_content, const TypedArray<Dictionary> &p_tool_calls) {
	is_busy = false;
	if (cancel_requested.is_set()) {
		return;
	}

	if (pending_complete_callback.is_valid()) {
		pending_complete_callback.call(AIMessage::create_assistant(p_content, p_tool_calls));
	}
}

void OpenAIProvider::_dispatch_stream_error(const String &p_error) {
	is_busy = false;
	if (cancel_requested.is_set()) {
		return;
	}

	if (pending_complete_callback.is_valid()) {
		pending_complete_callback.call(AIMessage::create_assistant("Error: " + p_error));
	}
}

void OpenAIProvider::_stream_request_thread(void *p_userdata) {
	OpenAIStreamRequestData *request_data = static_cast<OpenAIStreamRequestData *>(p_userdata);
	OpenAIProvider *provider = request_data->provider;
	Ref<HTTPClient> client = HTTPClient::create();
	if (client.is_null()) {
		MessageQueue::get_main_singleton()->push_callable(
				callable_mp(provider, &OpenAIProvider::_dispatch_stream_error),
				String("Unable to create HTTP client."));
		memdelete(request_data);
		return;
	}

	ParsedHTTPURL parsed = parse_http_url(request_data->url);
	if (!parsed.valid) {
		MessageQueue::get_main_singleton()->push_callable(
				callable_mp(provider, &OpenAIProvider::_dispatch_stream_error),
				String("Invalid API URL."));
		memdelete(request_data);
		return;
	}

	client->set_blocking_mode(true);
	client->set_read_chunk_size(4096);

	Error err = client->connect_to_host(parsed.host, parsed.port,
			parsed.use_tls ? TLSOptions::client(Ref<X509Certificate>(), parsed.host) : Ref<TLSOptions>());
	if (err != OK) {
		MessageQueue::get_main_singleton()->push_callable(
				callable_mp(provider, &OpenAIProvider::_dispatch_stream_error),
				String(vformat("Failed to connect to API server (%d).", err)));
		memdelete(request_data);
		return;
	}

	bool request_sent = false;
	bool response_started = false;
	int response_code = 0;
	String event_buffer;
	String error_body;
	String accumulated_content;
	Vector<PartialOpenAIToolCall> tool_calls;

	while (!provider->cancel_requested.is_set()) {
		HTTPClient::Status status = client->get_status();
		switch (status) {
			case HTTPClient::STATUS_RESOLVING:
			case HTTPClient::STATUS_CONNECTING:
			case HTTPClient::STATUS_REQUESTING: {
				client->poll();
				OS::get_singleton()->delay_usec(1000);
			} break;

			case HTTPClient::STATUS_CONNECTED: {
				if (!request_sent) {
					err = client->request(HTTPClient::METHOD_POST, parsed.path,
							request_data->headers,
							request_data->body.is_empty() ? nullptr : request_data->body.ptr(),
							request_data->body.size());
					if (err != OK) {
						MessageQueue::get_main_singleton()->push_callable(
								callable_mp(provider, &OpenAIProvider::_dispatch_stream_error),
								String(vformat("Failed to send API request (%d).", err)));
						client->close();
						memdelete(request_data);
						return;
					}
					request_sent = true;
					continue;
				}

				if (response_started && response_code != HTTPClient::RESPONSE_OK) {
					MessageQueue::get_main_singleton()->push_callable(
							callable_mp(provider, &OpenAIProvider::_dispatch_stream_error),
							extract_openai_error_message(error_body, response_code));
				} else {
					MessageQueue::get_main_singleton()->push_callable(
							callable_mp(provider, &OpenAIProvider::_dispatch_stream_complete),
							accumulated_content,
							finalize_openai_tool_calls(tool_calls));
				}
				client->close();
				memdelete(request_data);
				return;
			}

			case HTTPClient::STATUS_BODY: {
				if (!response_started) {
					response_code = client->get_response_code();
					response_started = true;
				}

				client->poll();
				if (client->get_status() != HTTPClient::STATUS_BODY) {
					continue;
				}

				PackedByteArray chunk = client->read_response_body_chunk();
				if (chunk.is_empty()) {
					continue;
				}

				String text_chunk = String::utf8((const char *)chunk.ptr(), chunk.size());
				if (response_code != HTTPClient::RESPONSE_OK) {
					error_body += text_chunk;
					continue;
				}

				event_buffer += text_chunk;
				String event_block;
				while (pop_sse_event(event_buffer, event_block)) {
					String data = extract_sse_data(event_block);
					if (data.is_empty()) {
						continue;
					}
					if (data == "[DONE]") {
						continue;
					}

					JSON json;
					if (json.parse(data) != OK || json.get_data().get_type() != Variant::DICTIONARY) {
						continue;
					}

					Dictionary payload = json.get_data();
					Array choices = payload.get("choices", Array());
					if (choices.is_empty()) {
						continue;
					}

					Dictionary choice = choices[0];
					Dictionary delta = choice.get("delta", Dictionary());
					String content_delta = delta.get("content", "");
					if (!content_delta.is_empty()) {
						accumulated_content += content_delta;
						MessageQueue::get_main_singleton()->push_callable(
								callable_mp(provider, &OpenAIProvider::_dispatch_stream_chunk),
								content_delta);
					}

					Array delta_tool_calls = delta.get("tool_calls", Array());
					if (!delta_tool_calls.is_empty()) {
						merge_openai_tool_call_delta(tool_calls, delta_tool_calls);
					}
				}
			} break;

			case HTTPClient::STATUS_CANT_RESOLVE:
			case HTTPClient::STATUS_CANT_CONNECT:
			case HTTPClient::STATUS_CONNECTION_ERROR:
			case HTTPClient::STATUS_TLS_HANDSHAKE_ERROR: {
				MessageQueue::get_main_singleton()->push_callable(
						callable_mp(provider, &OpenAIProvider::_dispatch_stream_error),
						String(vformat("Connection failed (status %d).", status)));
				client->close();
				memdelete(request_data);
				return;
			}

			default: {
				OS::get_singleton()->delay_usec(1000);
			} break;
		}
	}

	client->close();
	memdelete(request_data);
}

void OpenAIProvider::_on_request_completed(int p_result, int p_code,
		const PackedStringArray &p_headers, const PackedByteArray &p_body) {
	is_busy = false;

	if (cancel_requested.is_set()) {
		_cleanup_request();
		return;
	}

	// Handle HTTP-level errors.
	if (p_result != HTTPRequest::RESULT_SUCCESS) {
		String err_msg;
		switch (p_result) {
			case HTTPRequest::RESULT_CANT_CONNECT:
				err_msg = "Cannot connect to API server.";
				break;
			case HTTPRequest::RESULT_CANT_RESOLVE:
				err_msg = "Cannot resolve API hostname.";
				break;
			case HTTPRequest::RESULT_CONNECTION_ERROR:
				err_msg = "Connection error.";
				break;
			case HTTPRequest::RESULT_TLS_HANDSHAKE_ERROR:
				err_msg = "TLS handshake error.";
				break;
			case HTTPRequest::RESULT_NO_RESPONSE:
				err_msg = "No response from server.";
				break;
			case HTTPRequest::RESULT_REQUEST_FAILED:
				err_msg = "Request failed.";
				break;
			case HTTPRequest::RESULT_TIMEOUT:
				err_msg = "Request timed out.";
				break;
			default:
				err_msg = "HTTP error (code " + itos(p_result) + ").";
				break;
		}

		Ref<AIMessage> error_msg = AIMessage::create_assistant("Error: " + err_msg);
		if (is_streaming && pending_complete_callback.is_valid()) {
			pending_complete_callback.call(error_msg);
		} else if (pending_callback.is_valid()) {
			pending_callback.call(error_msg);
		}
		_cleanup_request();
		return;
	}

	String response_text = String::utf8((const char *)p_body.ptr(), p_body.size());

	// Handle non-200 HTTP status codes.
	if (p_code != 200) {
		String err_msg = "API error (HTTP " + itos(p_code) + ")";
		// Try to extract error message from the response body.
		JSON json;
		if (json.parse(response_text) == OK) {
			Dictionary resp = json.get_data();
			if (resp.has("error")) {
				Dictionary error = resp["error"];
				if (error.has("message")) {
					err_msg += ": " + (String)error["message"];
				}
			}
		}

		Ref<AIMessage> error_msg = AIMessage::create_assistant("Error: " + err_msg);
		if (is_streaming && pending_complete_callback.is_valid()) {
			pending_complete_callback.call(error_msg);
		} else if (pending_callback.is_valid()) {
			pending_callback.call(error_msg);
		}
		_cleanup_request();
		return;
	}

	if (is_streaming) {
		// Parse SSE stream response — the full body is available now.
		// Split by double newlines (SSE event boundaries).
		PackedStringArray lines = response_text.split("\n");
		String accumulated_content;
		TypedArray<Dictionary> accumulated_tool_calls;

		for (int i = 0; i < lines.size(); i++) {
			String line = lines[i].strip_edges();
			if (line.is_empty()) {
				continue;
			}

			Ref<AIMessage> chunk = _parse_stream_chunk(line);
			if (chunk.is_valid() && !chunk->get_content().is_empty()) {
				accumulated_content += chunk->get_content();
				// Send each chunk to the stream callback.
				if (pending_stream_callback.is_valid()) {
					pending_stream_callback.call(chunk);
				}
			}
			if (chunk.is_valid() && chunk->has_tool_calls()) {
				// Accumulate tool calls across chunks.
				TypedArray<Dictionary> tc = chunk->get_tool_calls();
				for (int j = 0; j < tc.size(); j++) {
					accumulated_tool_calls.push_back(tc[j]);
				}
			}
		}

		// Send completion with full accumulated message.
		Ref<AIMessage> complete_msg = AIMessage::create_assistant(accumulated_content, accumulated_tool_calls);
		if (pending_complete_callback.is_valid()) {
			pending_complete_callback.call(complete_msg);
		}
	} else {
		// Parse standard JSON response.
		JSON json;
		Error err = json.parse(response_text);
		if (err != OK) {
			Ref<AIMessage> error_msg = AIMessage::create_assistant("Error: Failed to parse API response.");
			if (pending_callback.is_valid()) {
				pending_callback.call(error_msg);
			}
			_cleanup_request();
			return;
		}

		Dictionary response = json.get_data();
		Ref<AIMessage> result = parse_response(response);
		if (result.is_null()) {
			result = AIMessage::create_assistant("Error: Empty or invalid response from API.");
		}

		if (pending_callback.is_valid()) {
			pending_callback.call(result);
		}
	}

	_cleanup_request();
}

Error OpenAIProvider::send_message(
		const TypedArray<Ref<AIMessage>> &p_messages,
		const TypedArray<Dictionary> &p_tools,
		const Callable &p_callback) {
	if (is_busy) {
		return ERR_BUSY;
	}
	if (api_key.is_empty()) {
		return ERR_UNCONFIGURED;
	}

	_wait_for_thread();
	is_busy = true;
	is_streaming = false;
	cancel_requested.clear();
	pending_callback = p_callback;
	pending_stream_callback = Callable();
	pending_complete_callback = Callable();

	Dictionary request = format_request(p_messages, p_tools);
	String body = JSON::stringify(request);

	// Create HTTPRequest node and add to scene tree.
	_cleanup_request();
	http_request = memnew(HTTPRequest);
	http_request->set_use_threads(true);
	http_request->set_timeout(120.0); // 2 minute timeout.

	SceneTree *tree = SceneTree::get_singleton();
	ERR_FAIL_NULL_V(tree, ERR_UNAVAILABLE);
	tree->get_root()->call_deferred("add_child", http_request);

	http_request->connect("request_completed",
			callable_mp(this, &OpenAIProvider::_on_request_completed));

	// Build headers.
	PackedStringArray headers;
	headers.push_back("Content-Type: application/json");
	headers.push_back("Authorization: Bearer " + api_key);

	String url = base_url + "/chat/completions";

	// Use call_deferred to make the request after the node is added to tree.
	http_request->call_deferred("request", url,
			headers, HTTPClient::METHOD_POST, body);

	return OK;
}

Error OpenAIProvider::stream_message(
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

	_wait_for_thread();
	is_busy = true;
	is_streaming = true;
	cancel_requested.clear();
	pending_callback = Callable();
	pending_stream_callback = p_stream_callback;
	pending_complete_callback = p_complete_callback;

	Dictionary request = format_request(p_messages, p_tools);
	request["stream"] = true;
	CharString body_utf8 = JSON::stringify(request).utf8();

	OpenAIStreamRequestData *request_data = memnew(OpenAIStreamRequestData);
	request_data->provider = this;
	request_data->url = base_url + "/chat/completions";
	request_data->headers.push_back("Content-Type: application/json");
	request_data->headers.push_back("Authorization: Bearer " + api_key);
	if (body_utf8.length() > 0) {
		request_data->body.resize(body_utf8.length());
		memcpy(request_data->body.ptrw(), body_utf8.ptr(), body_utf8.length());
	}

	request_thread.start(&OpenAIProvider::_stream_request_thread, request_data);

	return OK;
}

void OpenAIProvider::cancel() {
	cancel_requested.set();
	_cleanup_request();
	_wait_for_thread();
	is_busy = false;
}
