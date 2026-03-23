/**************************************************************************/
/*  anthropic_provider.cpp                                                */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "anthropic_provider.h"

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

struct PartialAnthropicToolCall {
	String id;
	String name;
	String input_json;
};

struct AnthropicStreamRequestData {
	AnthropicProvider *provider = nullptr;
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

void ensure_tool_call(Vector<PartialAnthropicToolCall> &r_tool_calls, int p_index) {
	while (r_tool_calls.size() <= p_index) {
		r_tool_calls.push_back(PartialAnthropicToolCall());
	}
}

TypedArray<Dictionary> finalize_tool_calls(const Vector<PartialAnthropicToolCall> &p_tool_calls) {
	TypedArray<Dictionary> tool_calls;
	for (int i = 0; i < p_tool_calls.size(); i++) {
		const PartialAnthropicToolCall &tool_call = p_tool_calls[i];
		if (tool_call.id.is_empty() && tool_call.name.is_empty() && tool_call.input_json.is_empty()) {
			continue;
		}

		Dictionary tc;
		tc["id"] = tool_call.id;
		tc["type"] = "function";

		Dictionary function;
		function["name"] = tool_call.name;
		function["arguments"] = tool_call.input_json.is_empty() ? String("{}") : tool_call.input_json;
		tc["function"] = function;
		tool_calls.push_back(tc);
	}
	return tool_calls;
}

String extract_error_message(const String &p_response_text, int p_code) {
	String err_msg = "API error (HTTP " + itos(p_code) + ")";
	JSON json;
	if (json.parse(p_response_text) == OK && json.get_data().get_type() == Variant::DICTIONARY) {
		Dictionary response = json.get_data();
		if (response.has("error")) {
			Variant error_variant = response["error"];
			if (error_variant.get_type() == Variant::DICTIONARY) {
				Dictionary error = error_variant;
				if (error.has("message")) {
					err_msg += ": " + String(error["message"]);
				}
			} else {
				err_msg += ": " + String(error_variant);
			}
		}
	}
	return err_msg;
}
} // namespace

void AnthropicProvider::_bind_methods() {
}

bool AnthropicProvider::supports_model_discovery() const {
	return true;
}

Error AnthropicProvider::request_available_models(const Callable &p_callback) {
	return AIProvider::request_available_models(p_callback);
}

AnthropicProvider::AnthropicProvider() {
	model_name = "claude-sonnet-4-5-20250929";
	base_url = "https://api.anthropic.com/v1";
}

AnthropicProvider::~AnthropicProvider() {
	cancel_requested.set();
	_wait_for_thread();
	_cleanup_request();
}

String AnthropicProvider::_get_model_discovery_url() const {
	return base_url.trim_suffix("/") + "/models";
}

PackedStringArray AnthropicProvider::_get_model_discovery_headers() const {
	PackedStringArray headers;
	headers.push_back("Content-Type: application/json");
	if (!api_key.is_empty()) {
		headers.push_back("x-api-key: " + api_key);
	}
	headers.push_back("anthropic-version: 2023-06-01");
	return headers;
}

PackedStringArray AnthropicProvider::_parse_model_discovery_response(const Variant &p_response) const {
	PackedStringArray models = AIProvider::_parse_model_discovery_response(p_response);
	if (!models.is_empty()) {
		return models;
	}
	if (p_response.get_type() != Variant::DICTIONARY) {
		return models;
	}

	const Dictionary response = p_response;
	if (!response.has("models")) {
		return models;
	}

	const Array data = response["models"];
	for (int i = 0; i < data.size(); i++) {
		if (data[i].get_type() != Variant::DICTIONARY) {
			continue;
		}
		const Dictionary model = data[i];
		const String model_id = model.get("id", model.get("name", String()));
		if (model_id.is_empty() || models.has(model_id)) {
			continue;
		}
		models.push_back(model_id);
	}
	return models;
}

String AnthropicProvider::_extract_system_prompt(const TypedArray<Ref<AIMessage>> &p_messages) const {
	for (int i = 0; i < p_messages.size(); i++) {
		Ref<AIMessage> msg = p_messages[i];
		if (msg.is_valid() && msg->get_role() == AIMessage::ROLE_SYSTEM) {
			return msg->get_content();
		}
	}
	return "";
}

TypedArray<Dictionary> AnthropicProvider::_format_messages_anthropic(const TypedArray<Ref<AIMessage>> &p_messages) const {
	TypedArray<Dictionary> formatted;
	for (int i = 0; i < p_messages.size(); i++) {
		Ref<AIMessage> msg = p_messages[i];
		if (msg.is_null() || msg->get_role() == AIMessage::ROLE_SYSTEM) {
			continue;
		}

		Dictionary msg_dict;
		switch (msg->get_role()) {
			case AIMessage::ROLE_USER:
				msg_dict["role"] = "user";
				msg_dict["content"] = msg->get_content();
				break;
			case AIMessage::ROLE_ASSISTANT: {
				msg_dict["role"] = "assistant";
				if (msg->has_tool_calls()) {
					Array content_blocks;
					if (!msg->get_content().is_empty()) {
						Dictionary text_block;
						text_block["type"] = "text";
						text_block["text"] = msg->get_content();
						content_blocks.push_back(text_block);
					}
					TypedArray<Dictionary> tc = msg->get_tool_calls();
					for (int j = 0; j < tc.size(); j++) {
						Dictionary tool_call = (Dictionary)tc[j];
						Dictionary tool_block;
						tool_block["type"] = "tool_use";
						tool_block["id"] = tool_call.get("id", String());
						tool_block["name"] = ((Dictionary)tool_call.get("function", Dictionary())).get("name", String());
						String args_str = ((Dictionary)tool_call.get("function", Dictionary())).get("arguments", String("{}"));
						JSON json;
						json.parse(args_str);
						tool_block["input"] = json.get_data();
						content_blocks.push_back(tool_block);
					}
					msg_dict["content"] = content_blocks;
				} else {
					msg_dict["content"] = msg->get_content();
				}
			} break;
			case AIMessage::ROLE_TOOL: {
				msg_dict["role"] = "user";
				Array content_blocks;
				Dictionary result_block;
				result_block["type"] = "tool_result";
				result_block["tool_use_id"] = msg->get_tool_call_id();
				result_block["content"] = msg->get_content();
				content_blocks.push_back(result_block);
				msg_dict["content"] = content_blocks;
			} break;
			default:
				continue;
		}
		formatted.push_back(msg_dict);
	}
	return formatted;
}

TypedArray<Dictionary> AnthropicProvider::_convert_tools_to_anthropic(const TypedArray<Dictionary> &p_tools) const {
	TypedArray<Dictionary> converted;
	for (int i = 0; i < p_tools.size(); i++) {
		Dictionary tool = (Dictionary)p_tools[i];
		Dictionary anthropic_tool;
		if (tool.has("function")) {
			Dictionary func = tool["function"];
			anthropic_tool["name"] = func.get("name", String());
			anthropic_tool["description"] = func.get("description", String());
			anthropic_tool["input_schema"] = func.get("parameters", Dictionary());
		}
		converted.push_back(anthropic_tool);
	}
	return converted;
}

Dictionary AnthropicProvider::format_request(
		const TypedArray<Ref<AIMessage>> &p_messages,
		const TypedArray<Dictionary> &p_tools) const {
	Dictionary request;
	request["model"] = model_name;
	if (has_max_tokens_override()) {
		request["max_tokens"] = max_tokens;
	}
	request["messages"] = _format_messages_anthropic(p_messages);

	String system = _extract_system_prompt(p_messages);
	if (!system.is_empty()) {
		request["system"] = system;
	}

	if (p_tools.size() > 0) {
		request["tools"] = _convert_tools_to_anthropic(p_tools);
	}

	return request;
}

Ref<AIMessage> AnthropicProvider::parse_response(const Dictionary &p_response) const {
	if (!p_response.has("content")) {
		return Ref<AIMessage>();
	}

	Array content_blocks = p_response["content"];
	String text_content;
	TypedArray<Dictionary> tool_calls;

	for (int i = 0; i < content_blocks.size(); i++) {
		Dictionary block = content_blocks[i];
		String type = block.get("type", String());
		if (type == "text") {
			text_content += String(block.get("text", String()));
		} else if (type == "tool_use") {
			Dictionary tc;
			tc["id"] = block.get("id", String());
			Dictionary func;
			func["name"] = block.get("name", String());
			func["arguments"] = JSON::stringify(block.get("input", Dictionary()));
			tc["function"] = func;
			tc["type"] = "function";
			tool_calls.push_back(tc);
		}
	}

	return AIMessage::create_assistant(text_content, tool_calls);
}

void AnthropicProvider::_cleanup_request() {
	if (http_request) {
		http_request->cancel_request();
		http_request->queue_free();
		http_request = nullptr;
	}
}

void AnthropicProvider::_wait_for_thread() {
	if (request_thread.is_started()) {
		request_thread.wait_to_finish();
	}
}

void AnthropicProvider::_dispatch_stream_chunk(const String &p_text) {
	if (!is_streaming || cancel_requested.is_set() || p_text.is_empty()) {
		return;
	}

	if (pending_stream_callback.is_valid()) {
		pending_stream_callback.call(AIMessage::create_assistant(p_text));
	}
}

void AnthropicProvider::_dispatch_stream_complete(const String &p_content, const TypedArray<Dictionary> &p_tool_calls) {
	is_busy = false;
	if (cancel_requested.is_set()) {
		return;
	}

	if (pending_complete_callback.is_valid()) {
		pending_complete_callback.call(AIMessage::create_assistant(p_content, p_tool_calls));
	}
}

void AnthropicProvider::_dispatch_stream_error(const String &p_error) {
	is_busy = false;
	if (cancel_requested.is_set()) {
		return;
	}

	if (pending_complete_callback.is_valid()) {
		pending_complete_callback.call(AIMessage::create_assistant("Error: " + p_error));
	}
}

void AnthropicProvider::_stream_request_thread(void *p_userdata) {
	AnthropicStreamRequestData *request_data = static_cast<AnthropicStreamRequestData *>(p_userdata);
	AnthropicProvider *provider = request_data->provider;
	Ref<HTTPClient> client = HTTPClient::create();
	if (client.is_null()) {
		MessageQueue::get_main_singleton()->push_callable(
				callable_mp(provider, &AnthropicProvider::_dispatch_stream_error),
				String("Unable to create HTTP client."));
		memdelete(request_data);
		return;
	}

	ParsedHTTPURL parsed = parse_http_url(request_data->url);
	if (!parsed.valid) {
		MessageQueue::get_main_singleton()->push_callable(
				callable_mp(provider, &AnthropicProvider::_dispatch_stream_error),
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
				callable_mp(provider, &AnthropicProvider::_dispatch_stream_error),
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
	Vector<PartialAnthropicToolCall> tool_calls;

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
								callable_mp(provider, &AnthropicProvider::_dispatch_stream_error),
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
							callable_mp(provider, &AnthropicProvider::_dispatch_stream_error),
							extract_error_message(error_body, response_code));
				} else {
					MessageQueue::get_main_singleton()->push_callable(
							callable_mp(provider, &AnthropicProvider::_dispatch_stream_complete),
							accumulated_content,
							finalize_tool_calls(tool_calls));
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

					JSON json;
					if (json.parse(data) != OK || json.get_data().get_type() != Variant::DICTIONARY) {
						continue;
					}

					Dictionary payload = json.get_data();
					String event_type = payload.get("type", "");
					if (event_type == "content_block_start") {
						int index = payload.get("index", 0);
						Dictionary content_block = payload.get("content_block", Dictionary());
						if (content_block.get("type", "") == "tool_use") {
							ensure_tool_call(tool_calls, index);
							PartialAnthropicToolCall &tool_call = tool_calls.write[index];
							tool_call.id = content_block.get("id", "");
							tool_call.name = content_block.get("name", "");
							Variant input = content_block.get("input", Dictionary());
							if (input.get_type() == Variant::DICTIONARY) {
								tool_call.input_json = JSON::stringify(input);
							}
						}
					} else if (event_type == "content_block_delta") {
						int index = payload.get("index", 0);
						Dictionary delta = payload.get("delta", Dictionary());
						String delta_type = delta.get("type", "");
						if (delta_type == "text_delta") {
							String text_delta = delta.get("text", "");
							if (!text_delta.is_empty()) {
								accumulated_content += text_delta;
								MessageQueue::get_main_singleton()->push_callable(
										callable_mp(provider, &AnthropicProvider::_dispatch_stream_chunk),
										text_delta);
							}
						} else if (delta_type == "input_json_delta") {
							ensure_tool_call(tool_calls, index);
							tool_calls.write[index].input_json += String(delta.get("partial_json", ""));
						}
					}
				}
			} break;

			case HTTPClient::STATUS_CANT_RESOLVE:
			case HTTPClient::STATUS_CANT_CONNECT:
			case HTTPClient::STATUS_CONNECTION_ERROR:
			case HTTPClient::STATUS_TLS_HANDSHAKE_ERROR: {
				MessageQueue::get_main_singleton()->push_callable(
						callable_mp(provider, &AnthropicProvider::_dispatch_stream_error),
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

void AnthropicProvider::_on_request_completed(int p_result, int p_code,
		const PackedStringArray &p_headers, const PackedByteArray &p_body) {
	is_busy = false;

	if (cancel_requested.is_set()) {
		_cleanup_request();
		return;
	}

	if (p_result != HTTPRequest::RESULT_SUCCESS) {
		String err_msg = "Connection error (code " + itos(p_result) + ").";
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

	if (p_code != 200) {
		String err_msg = "API error (HTTP " + itos(p_code) + ")";
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
		// Parse Anthropic SSE stream.
		// Anthropic uses event types: content_block_delta, content_block_start, message_stop, etc.
		PackedStringArray lines = response_text.split("\n");
		String accumulated_content;

		for (int i = 0; i < lines.size(); i++) {
			String line = lines[i].strip_edges();
			if (!line.begins_with("data: ")) {
				continue;
			}
			String data = line.substr(6);
			if (data.is_empty() || data == "[DONE]") {
				continue;
			}

			JSON json;
			if (json.parse(data) != OK) {
				continue;
			}

			Dictionary event = json.get_data();
			String event_type = event.get("type", "");

			if (event_type == "content_block_delta") {
				Dictionary delta = event.get("delta", Dictionary());
				String delta_type = delta.get("type", "");
				if (delta_type == "text_delta") {
					String text = delta.get("text", "");
					accumulated_content += text;
					Ref<AIMessage> chunk = AIMessage::create_assistant(text);
					if (pending_stream_callback.is_valid()) {
						pending_stream_callback.call(chunk);
					}
				}
			}
		}

		Ref<AIMessage> complete_msg = AIMessage::create_assistant(accumulated_content);
		if (pending_complete_callback.is_valid()) {
			pending_complete_callback.call(complete_msg);
		}
	} else {
		JSON json;
		if (json.parse(response_text) != OK) {
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

Error AnthropicProvider::send_message(
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

	_cleanup_request();
	http_request = memnew(HTTPRequest);
	http_request->set_use_threads(true);
	http_request->set_timeout(120.0);

	SceneTree *tree = SceneTree::get_singleton();
	ERR_FAIL_NULL_V(tree, ERR_UNAVAILABLE);
	tree->get_root()->call_deferred("add_child", http_request);

	http_request->connect("request_completed",
			callable_mp(this, &AnthropicProvider::_on_request_completed));

	// Anthropic-specific headers.
	PackedStringArray headers;
	headers.push_back("Content-Type: application/json");
	headers.push_back("x-api-key: " + api_key);
	headers.push_back("anthropic-version: 2023-06-01");

	String url = base_url + "/messages";

	http_request->call_deferred("request", url,
			headers, HTTPClient::METHOD_POST, body);

	return OK;
}

Error AnthropicProvider::stream_message(
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

	AnthropicStreamRequestData *request_data = memnew(AnthropicStreamRequestData);
	request_data->provider = this;
	request_data->url = base_url + "/messages";
	request_data->headers.push_back("Content-Type: application/json");
	request_data->headers.push_back("x-api-key: " + api_key);
	request_data->headers.push_back("anthropic-version: 2023-06-01");
	if (body_utf8.length() > 0) {
		request_data->body.resize(body_utf8.length());
		memcpy(request_data->body.ptrw(), body_utf8.ptr(), body_utf8.length());
	}

	request_thread.start(&AnthropicProvider::_stream_request_thread, request_data);

	return OK;
}

void AnthropicProvider::cancel() {
	cancel_requested.set();
	_cleanup_request();
	_wait_for_thread();
	is_busy = false;
}
