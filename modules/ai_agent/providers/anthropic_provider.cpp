/**************************************************************************/
/*  anthropic_provider.cpp                                                */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "anthropic_provider.h"
#include "core/io/json.h"

void AnthropicProvider::_bind_methods() {
}

AnthropicProvider::AnthropicProvider() {
	model_name = "claude-sonnet-4-20250514";
	base_url = "https://api.anthropic.com/v1";
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
			continue; // System prompt is handled separately in Anthropic API.
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
					// Anthropic uses content blocks for tool use.
					Array content_blocks;
					if (!msg->get_content().is_empty()) {
						Dictionary text_block;
						text_block["type"] = "text";
						text_block["text"] = msg->get_content();
						content_blocks.push_back(text_block);
					}
					TypedArray<Dictionary> tc = msg->get_tool_calls();
					for (int j = 0; j < tc.size(); j++) {
						Dictionary tool_call = tc[j];
						Dictionary tool_block;
						tool_block["type"] = "tool_use";
						tool_block["id"] = tool_call.get("id", "");
						tool_block["name"] = tool_call.get("function", Dictionary()).get("name", "");
						String args_str = tool_call.get("function", Dictionary()).get("arguments", "{}");
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
		Dictionary tool = p_tools[i];
		Dictionary anthropic_tool;
		// OpenAI format: {type: "function", function: {name, description, parameters}}
		// Anthropic format: {name, description, input_schema}
		if (tool.has("function")) {
			Dictionary func = tool["function"];
			anthropic_tool["name"] = func.get("name", "");
			anthropic_tool["description"] = func.get("description", "");
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
	request["max_tokens"] = 4096;
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
		String type = block.get("type", "");
		if (type == "text") {
			text_content += block.get("text", "");
		} else if (type == "tool_use") {
			// Convert Anthropic tool_use to OpenAI-compatible format.
			Dictionary tc;
			tc["id"] = block.get("id", "");
			Dictionary func;
			func["name"] = block.get("name", "");
			func["arguments"] = JSON::stringify(block.get("input", Dictionary()));
			tc["function"] = func;
			tc["type"] = "function";
			tool_calls.push_back(tc);
		}
	}

	return AIMessage::create_assistant(text_content, tool_calls);
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

	is_busy = true;
	cancel_requested = false;

	Dictionary request = format_request(p_messages, p_tools);
	String body = JSON::stringify(request);

	// HTTP transport skeleton — will be wired up in integration phase.
	is_busy = false;
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

	is_busy = true;
	cancel_requested = false;

	Dictionary request = format_request(p_messages, p_tools);
	request["stream"] = true;
	String body = JSON::stringify(request);

	// Streaming transport skeleton — will be wired up in integration phase.
	is_busy = false;
	return OK;
}

void AnthropicProvider::cancel() {
	cancel_requested = true;
	is_busy = false;
}
