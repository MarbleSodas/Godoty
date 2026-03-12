/**************************************************************************/
/*  ai_agent_session.cpp                                                  */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "ai_agent_session.h"
#include "core/io/json.h"
#include "providers/anthropic_provider.h"
#include "providers/local_provider.h"
#include "providers/minimax_provider.h"
#include "providers/openai_provider.h"

void AIAgentSession::_bind_methods() {
	ClassDB::bind_method(D_METHOD("set_config", "config"), &AIAgentSession::set_config);
	ClassDB::bind_method(D_METHOD("get_config"), &AIAgentSession::get_config);
	ClassDB::bind_method(D_METHOD("get_state"), &AIAgentSession::get_state);
	ClassDB::bind_method(D_METHOD("is_busy"), &AIAgentSession::is_busy);
	ClassDB::bind_method(D_METHOD("send_message", "content"), &AIAgentSession::send_message);
	ClassDB::bind_method(D_METHOD("send_message_with_context", "content", "context"), &AIAgentSession::send_message_with_context);
	ClassDB::bind_method(D_METHOD("add_system_message", "content"), &AIAgentSession::add_system_message);
	ClassDB::bind_method(D_METHOD("clear_history"), &AIAgentSession::clear_history);
	ClassDB::bind_method(D_METHOD("get_history"), &AIAgentSession::get_history);
	ClassDB::bind_method(D_METHOD("get_message_count"), &AIAgentSession::get_message_count);
	ClassDB::bind_method(D_METHOD("cancel"), &AIAgentSession::cancel);
	ClassDB::bind_method(D_METHOD("approve_tool_call", "tool_call_id"), &AIAgentSession::approve_tool_call);
	ClassDB::bind_method(D_METHOD("deny_tool_call", "tool_call_id", "reason"), &AIAgentSession::deny_tool_call, DEFVAL(""));
	ClassDB::bind_method(D_METHOD("set_max_tool_iterations", "max"), &AIAgentSession::set_max_tool_iterations);
	ClassDB::bind_method(D_METHOD("get_max_tool_iterations"), &AIAgentSession::get_max_tool_iterations);

	ADD_PROPERTY(PropertyInfo(Variant::OBJECT, "config", PROPERTY_HINT_RESOURCE_TYPE, "AIAgentConfig"), "set_config", "get_config");
	ADD_PROPERTY(PropertyInfo(Variant::INT, "state", PROPERTY_HINT_NONE, "", PROPERTY_USAGE_NO_EDITOR), "", "get_state");
	ADD_PROPERTY(PropertyInfo(Variant::INT, "max_tool_iterations"), "set_max_tool_iterations", "get_max_tool_iterations");

	// Signals for UI integration.
	ADD_SIGNAL(MethodInfo("message_received",
			PropertyInfo(Variant::OBJECT, "message", PROPERTY_HINT_RESOURCE_TYPE, "AIMessage")));
	ADD_SIGNAL(MethodInfo("stream_chunk",
			PropertyInfo(Variant::STRING, "content")));
	ADD_SIGNAL(MethodInfo("tool_call_requested",
			PropertyInfo(Variant::STRING, "tool_name"),
			PropertyInfo(Variant::DICTIONARY, "arguments"),
			PropertyInfo(Variant::STRING, "tool_call_id")));
	ADD_SIGNAL(MethodInfo("tool_call_completed",
			PropertyInfo(Variant::STRING, "tool_name"),
			PropertyInfo(Variant::NIL, "result")));
	ADD_SIGNAL(MethodInfo("approval_required",
			PropertyInfo(Variant::STRING, "tool_name"),
			PropertyInfo(Variant::DICTIONARY, "arguments"),
			PropertyInfo(Variant::STRING, "tool_call_id")));
	ADD_SIGNAL(MethodInfo("error_occurred",
			PropertyInfo(Variant::STRING, "error_message")));
	ADD_SIGNAL(MethodInfo("session_completed"));
	ADD_SIGNAL(MethodInfo("state_changed",
			PropertyInfo(Variant::INT, "new_state")));

	BIND_ENUM_CONSTANT(STATE_IDLE);
	BIND_ENUM_CONSTANT(STATE_SENDING);
	BIND_ENUM_CONSTANT(STATE_WAITING_FOR_RESPONSE);
	BIND_ENUM_CONSTANT(STATE_PROCESSING_TOOL_CALLS);
	BIND_ENUM_CONSTANT(STATE_WAITING_FOR_APPROVAL);
	BIND_ENUM_CONSTANT(STATE_ERROR);
}

AIAgentSession::AIAgentSession() {
}

AIAgentSession::~AIAgentSession() {
}

void AIAgentSession::set_config(const Ref<AIAgentConfig> &p_config) {
	config = p_config;
	// Recreate provider when config changes.
	if (config.is_valid()) {
		provider = _create_provider_for_config();
	} else {
		provider.unref();
	}
}

Ref<AIAgentConfig> AIAgentSession::get_config() const {
	return config;
}

AIAgentSession::SessionState AIAgentSession::get_state() const {
	return state;
}

bool AIAgentSession::is_busy() const {
	return state != STATE_IDLE && state != STATE_ERROR;
}

Ref<AIProvider> AIAgentSession::_create_provider_for_config() const {
	ERR_FAIL_COND_V(config.is_null(), Ref<AIProvider>());

	Ref<AIProvider> p;
	switch (config->get_provider_type()) {
		case AIAgentConfig::PROVIDER_OPENAI: {
			Ref<OpenAIProvider> openai;
			openai.instantiate();
			p = openai;
		} break;
		case AIAgentConfig::PROVIDER_ANTHROPIC: {
			Ref<AnthropicProvider> anthropic;
			anthropic.instantiate();
			p = anthropic;
		} break;
		case AIAgentConfig::PROVIDER_MINIMAX: {
			Ref<MiniMaxProvider> minimax;
			minimax.instantiate();
			p = minimax;
		} break;
		case AIAgentConfig::PROVIDER_LOCAL: {
			Ref<LocalLLMProvider> local;
			local.instantiate();
			p = local;
		} break;
		case AIAgentConfig::PROVIDER_CUSTOM: {
			// Custom providers can be set directly.
			return Ref<AIProvider>();
		}
	}

	if (p.is_valid()) {
		p->set_api_key(config->get_api_key());
		p->set_base_url(config->get_effective_base_url());
		p->set_model_name(config->get_model_name());
		p->set_temperature(config->get_temperature());
		p->set_max_tokens(config->get_max_tokens());
	}

	return p;
}

void AIAgentSession::send_message(const String &p_content) {
	_send_user_message(p_content, Dictionary());
}

void AIAgentSession::send_message_with_context(const String &p_content, const Dictionary &p_context) {
	_send_user_message(p_content, p_context);
}

void AIAgentSession::_send_user_message(const String &p_content, const Dictionary &p_context) {
	ERR_FAIL_COND_MSG(is_busy(), "Session is busy. Cancel or wait for completion.");
	ERR_FAIL_COND_MSG(config.is_null(), "No AIAgentConfig set on this session.");
	ERR_FAIL_COND_MSG(provider.is_null(), "No AI provider available.");

	// Add the system prompt if this is the first message and one is configured.
	if (messages.is_empty() && !config->get_system_prompt().is_empty()) {
		messages.push_back(AIMessage::create_system(config->get_system_prompt()));
	}

	// Add the user's message.
	Ref<AIMessage> user_msg = AIMessage::create_user(p_content);
	messages.push_back(user_msg);

	state = STATE_SENDING;
	current_tool_iteration = 0;
	emit_signal("state_changed", (int)state);

	pending_tool_calls.clear();
	_dispatch_request(_build_request_messages(p_context));
}

TypedArray<Ref<AIMessage>> AIAgentSession::_build_request_messages(const Dictionary &p_context) const {
	TypedArray<Ref<AIMessage>> msgs;
	int context_insert_index = messages.size();
	if (!p_context.is_empty()) {
		context_insert_index = MAX(0, messages.size() - 1);
	}

	for (int i = 0; i < messages.size(); i++) {
		if (i == context_insert_index && !p_context.is_empty()) {
			String context_str = "Current editor context:\n" + JSON::stringify(p_context, "  ");
			msgs.push_back(AIMessage::create_system(context_str));
		}
		msgs.push_back(messages[i]);
	}

	return msgs;
}

TypedArray<Dictionary> AIAgentSession::_get_enabled_tool_schemas() const {
	TypedArray<Dictionary> tool_schemas;
	AIToolRegistry *registry = AIToolRegistry::get_singleton();
	if (!registry || config.is_null()) {
		return tool_schemas;
	}

	PackedStringArray enabled = config->get_enabled_tools();
	if (enabled.is_empty()) {
		return registry->get_tool_schemas();
	}

	for (int i = 0; i < enabled.size(); i++) {
		if (registry->has_tool(enabled[i])) {
			tool_schemas.push_back(registry->get_tool_schema(enabled[i]));
		}
	}

	return tool_schemas;
}

void AIAgentSession::_dispatch_request(const TypedArray<Ref<AIMessage>> &p_messages) {
	state = STATE_WAITING_FOR_RESPONSE;
	emit_signal("state_changed", (int)state);

	TypedArray<Dictionary> tool_schemas = _get_enabled_tool_schemas();
	Error err;
	if (config->get_stream_responses()) {
		err = provider->stream_message(p_messages, tool_schemas,
				callable_mp(this, &AIAgentSession::_on_stream_chunk),
				callable_mp(this, &AIAgentSession::_on_stream_complete));
	} else {
		err = provider->send_message(p_messages, tool_schemas,
				callable_mp(this, &AIAgentSession::_on_response_received));
	}

	if (err != OK) {
		_on_error(vformat("Failed to send message: error %d", err));
	}
}

void AIAgentSession::add_system_message(const String &p_content) {
	messages.push_back(AIMessage::create_system(p_content));
}

void AIAgentSession::clear_history() {
	messages.clear();
	pending_tool_calls.clear();
	state = STATE_IDLE;
	current_tool_iteration = 0;
	emit_signal("state_changed", (int)state);
}

TypedArray<Dictionary> AIAgentSession::get_history() const {
	TypedArray<Dictionary> history;
	for (int i = 0; i < messages.size(); i++) {
		history.push_back(messages[i]->to_dict());
	}
	return history;
}

int AIAgentSession::get_message_count() const {
	return messages.size();
}

void AIAgentSession::cancel() {
	if (provider.is_valid()) {
		provider->cancel();
	}
	pending_tool_calls.clear();
	state = STATE_IDLE;
	emit_signal("state_changed", (int)state);
}

void AIAgentSession::_on_response_received(const Ref<AIMessage> &p_response) {
	if (p_response.is_null()) {
		_on_error("Received null response from provider.");
		return;
	}

	if (!p_response->has_tool_calls() && p_response->get_content().begins_with("Error: ")) {
		_on_error(p_response->get_content().trim_prefix("Error: ").strip_edges());
		return;
	}

	messages.push_back(p_response);
	emit_signal("message_received", p_response);

	if (p_response->has_tool_calls()) {
		_process_tool_calls(p_response);
	} else {
		state = STATE_IDLE;
		emit_signal("state_changed", (int)state);
		emit_signal("session_completed");
	}
}

void AIAgentSession::_on_stream_chunk(const Ref<AIMessage> &p_chunk) {
	if (p_chunk.is_valid()) {
		emit_signal("stream_chunk", p_chunk->get_content());
	}
}

void AIAgentSession::_on_stream_complete(const Ref<AIMessage> &p_full_response) {
	_on_response_received(p_full_response);
}

void AIAgentSession::_on_error(const String &p_error) {
	state = STATE_ERROR;
	emit_signal("state_changed", (int)state);
	emit_signal("error_occurred", p_error);
}

void AIAgentSession::_process_tool_calls(const Ref<AIMessage> &p_message) {
	current_tool_iteration++;
	if (current_tool_iteration > max_tool_iterations) {
		_on_error("Maximum tool call iterations exceeded. Possible infinite loop.");
		return;
	}

	state = STATE_PROCESSING_TOOL_CALLS;
	emit_signal("state_changed", (int)state);

	AIToolRegistry *registry = AIToolRegistry::get_singleton();
	ERR_FAIL_NULL_MSG(registry, "AIToolRegistry singleton not available.");

	TypedArray<Dictionary> tool_calls = p_message->get_tool_calls();
	pending_tool_calls.clear();
	for (int i = 0; i < tool_calls.size(); i++) {
		Dictionary tc = tool_calls[i];
		Dictionary function = tc.get("function", Dictionary());
		String args_str = function.get("arguments", "{}");

		PendingToolCall pending;
		pending.tool_call_id = tc.get("id", "");
		pending.tool_name = function.get("name", "");

		JSON json;
		if (json.parse(args_str) == OK && json.get_data().get_type() == Variant::DICTIONARY) {
			pending.arguments = json.get_data();
		} else {
			pending.arguments = Dictionary();
		}
		pending_tool_calls.push_back(pending);
	}

	_continue_tool_processing();
}

void AIAgentSession::_continue_tool_processing() {
	AIToolRegistry *registry = AIToolRegistry::get_singleton();
	ERR_FAIL_NULL_MSG(registry, "AIToolRegistry singleton not available.");

	while (!pending_tool_calls.is_empty()) {
		PendingToolCall pending = pending_tool_calls[0];
		emit_signal("tool_call_requested", pending.tool_name, pending.arguments, pending.tool_call_id);

		if (registry->tool_requires_approval(pending.tool_name)) {
			state = STATE_WAITING_FOR_APPROVAL;
			emit_signal("state_changed", (int)state);
			emit_signal("approval_required", pending.tool_name, pending.arguments, pending.tool_call_id);
			return;
		}

		if (registry->has_tool(pending.tool_name)) {
			Variant result = registry->execute_tool(pending.tool_name, pending.arguments);
			String result_str;
			if (result.get_type() == Variant::STRING) {
				result_str = result;
			} else {
				result_str = JSON::stringify(result);
			}

			emit_signal("tool_call_completed", pending.tool_name, result);

			Ref<AIMessage> tool_result = AIMessage::create_tool_result(pending.tool_call_id, result_str);
			messages.push_back(tool_result);
		} else {
			String error_msg = vformat("Tool '%s' not found. Available tools: %s",
					pending.tool_name, String(", ").join(registry->get_tool_names()));
			Ref<AIMessage> tool_result = AIMessage::create_tool_result(pending.tool_call_id, error_msg);
			messages.push_back(tool_result);
		}

		pending_tool_calls.remove_at(0);
	}

	_dispatch_request(_build_request_messages());
}

void AIAgentSession::approve_tool_call(const String &p_tool_call_id) {
	ERR_FAIL_COND_MSG(state != STATE_WAITING_FOR_APPROVAL, "Not waiting for approval.");

	AIToolRegistry *registry = AIToolRegistry::get_singleton();
	ERR_FAIL_NULL(registry);
	ERR_FAIL_COND_MSG(pending_tool_calls.is_empty(), "No pending tool calls to approve.");

	PendingToolCall pending = pending_tool_calls[0];
	if (!p_tool_call_id.is_empty() && pending.tool_call_id != p_tool_call_id) {
		ERR_FAIL_MSG("Tool call ID does not match the current pending approval.");
	}

	pending_tool_calls.remove_at(0);

	Variant result = registry->has_tool(pending.tool_name) ? registry->execute_tool(pending.tool_name, pending.arguments) : Variant(vformat("Tool '%s' not found.", pending.tool_name));
	String result_str = result.get_type() == Variant::STRING ? String(result) : JSON::stringify(result);
	emit_signal("tool_call_completed", pending.tool_name, result);
	messages.push_back(AIMessage::create_tool_result(pending.tool_call_id, result_str));

	_continue_tool_processing();
}

void AIAgentSession::deny_tool_call(const String &p_tool_call_id, const String &p_reason) {
	ERR_FAIL_COND_MSG(state != STATE_WAITING_FOR_APPROVAL, "Not waiting for approval.");
	ERR_FAIL_COND_MSG(pending_tool_calls.is_empty(), "No pending tool calls to deny.");

	PendingToolCall pending = pending_tool_calls[0];
	if (!p_tool_call_id.is_empty() && pending.tool_call_id != p_tool_call_id) {
		ERR_FAIL_MSG("Tool call ID does not match the current pending approval.");
	}

	pending_tool_calls.remove_at(0);

	String reason = p_reason.is_empty() ? "User denied the tool call." : p_reason;
	Ref<AIMessage> denial = AIMessage::create_tool_result(pending.tool_call_id, "DENIED: " + reason);
	messages.push_back(denial);

	_continue_tool_processing();
}

void AIAgentSession::set_max_tool_iterations(int p_max) {
	max_tool_iterations = MAX(1, p_max);
}

int AIAgentSession::get_max_tool_iterations() const {
	return max_tool_iterations;
}
