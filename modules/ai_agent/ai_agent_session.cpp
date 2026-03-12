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
	ADD_SIGNAL(MethodInfo("stream_chunk_received",
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
	}

	return p;
}

void AIAgentSession::send_message(const String &p_content) {
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

	// Get tool schemas from the registry.
	TypedArray<Dictionary> tool_schemas;
	AIToolRegistry *registry = AIToolRegistry::get_singleton();
	if (registry) {
		// Filter to only enabled tools from config.
		PackedStringArray enabled = config->get_enabled_tools();
		if (enabled.is_empty()) {
			// If no filter, expose all tools.
			tool_schemas = registry->get_tool_schemas();
		} else {
			for (int i = 0; i < enabled.size(); i++) {
				if (registry->has_tool(enabled[i])) {
					tool_schemas.push_back(registry->get_tool_schema(enabled[i]));
				}
			}
		}
	}

	// Convert messages vector to typed array for the provider.
	TypedArray<Ref<AIMessage>> msgs;
	for (int i = 0; i < messages.size(); i++) {
		msgs.push_back(messages[i]);
	}

	state = STATE_WAITING_FOR_RESPONSE;
	emit_signal("state_changed", (int)state);

	// Send to provider.
	if (config->get_stream_responses()) {
		Error err = provider->stream_message(msgs, tool_schemas,
				callable_mp(this, &AIAgentSession::_on_stream_chunk),
				callable_mp(this, &AIAgentSession::_on_stream_complete));
		if (err != OK) {
			_on_error(vformat("Failed to send message: error %d", err));
		}
	} else {
		Error err = provider->send_message(msgs, tool_schemas,
				callable_mp(this, &AIAgentSession::_on_response_received));
		if (err != OK) {
			_on_error(vformat("Failed to send message: error %d", err));
		}
	}
}

void AIAgentSession::send_message_with_context(const String &p_content, const Dictionary &p_context) {
	// Inject context as a system message before the user's message.
	if (!p_context.is_empty()) {
		String context_str = "Current editor context:\n" + JSON::stringify(p_context, "  ");
		Ref<AIMessage> context_msg = AIMessage::create_system(context_str);
		messages.push_back(context_msg);
	}
	send_message(p_content);
}

void AIAgentSession::add_system_message(const String &p_content) {
	messages.push_back(AIMessage::create_system(p_content));
}

void AIAgentSession::clear_history() {
	messages.clear();
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
	state = STATE_IDLE;
	emit_signal("state_changed", (int)state);
}

void AIAgentSession::_on_response_received(const Ref<AIMessage> &p_response) {
	if (p_response.is_null()) {
		_on_error("Received null response from provider.");
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
		emit_signal("stream_chunk_received", p_chunk->get_content());
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
	for (int i = 0; i < tool_calls.size(); i++) {
		Dictionary tc = tool_calls[i];
		String tool_call_id = tc.get("id", "");

		Dictionary function = tc.get("function", Dictionary());
		String tool_name = function.get("name", "");
		String args_str = function.get("arguments", "{}");

		// Parse arguments.
		JSON json;
		json.parse(args_str);
		Dictionary arguments = json.get_data();

		emit_signal("tool_call_requested", tool_name, arguments, tool_call_id);

		// Check if tool requires approval.
		if (registry->tool_requires_approval(tool_name)) {
			state = STATE_WAITING_FOR_APPROVAL;
			emit_signal("state_changed", (int)state);
			emit_signal("approval_required", tool_name, arguments, tool_call_id);
			return; // Wait for approve_tool_call or deny_tool_call.
		}

		// Execute the tool.
		if (registry->has_tool(tool_name)) {
			Variant result = registry->execute_tool(tool_name, arguments);
			String result_str;
			if (result.get_type() == Variant::STRING) {
				result_str = result;
			} else {
				result_str = JSON::stringify(result);
			}

			emit_signal("tool_call_completed", tool_name, result);

			// Add tool result to conversation.
			Ref<AIMessage> tool_result = AIMessage::create_tool_result(tool_call_id, result_str);
			messages.push_back(tool_result);
		} else {
			// Tool not found — send error back to LLM.
			String error_msg = vformat("Tool '%s' not found. Available tools: %s",
					tool_name, String(", ").join(registry->get_tool_names()));
			Ref<AIMessage> tool_result = AIMessage::create_tool_result(tool_call_id, error_msg);
			messages.push_back(tool_result);
		}
	}

	// After processing all tool calls, send the results back to the LLM
	// for it to continue (the agentic loop).
	TypedArray<Ref<AIMessage>> msgs;
	for (int i = 0; i < messages.size(); i++) {
		msgs.push_back(messages[i]);
	}

	TypedArray<Dictionary> tool_schemas;
	if (registry) {
		tool_schemas = registry->get_tool_schemas();
	}

	state = STATE_WAITING_FOR_RESPONSE;
	emit_signal("state_changed", (int)state);

	if (config.is_valid() && config->get_stream_responses()) {
		provider->stream_message(msgs, tool_schemas,
				callable_mp(this, &AIAgentSession::_on_stream_chunk),
				callable_mp(this, &AIAgentSession::_on_stream_complete));
	} else {
		provider->send_message(msgs, tool_schemas,
				callable_mp(this, &AIAgentSession::_on_response_received));
	}
}

void AIAgentSession::approve_tool_call(const String &p_tool_call_id) {
	ERR_FAIL_COND_MSG(state != STATE_WAITING_FOR_APPROVAL, "Not waiting for approval.");

	AIToolRegistry *registry = AIToolRegistry::get_singleton();
	ERR_FAIL_NULL(registry);

	// Find the pending tool call in the last assistant message.
	if (messages.size() > 0) {
		Ref<AIMessage> last_msg = messages[messages.size() - 1];
		if (last_msg->has_tool_calls()) {
			// Re-process with approval granted.
			// For now, re-enter _process_tool_calls which will execute the tool.
			// TODO: Add per-call approval tracking.
			_process_tool_calls(last_msg);
		}
	}
}

void AIAgentSession::deny_tool_call(const String &p_tool_call_id, const String &p_reason) {
	ERR_FAIL_COND_MSG(state != STATE_WAITING_FOR_APPROVAL, "Not waiting for approval.");

	String reason = p_reason.is_empty() ? "User denied the tool call." : p_reason;
	Ref<AIMessage> denial = AIMessage::create_tool_result(p_tool_call_id, "DENIED: " + reason);
	messages.push_back(denial);

	state = STATE_IDLE;
	emit_signal("state_changed", (int)state);
	emit_signal("session_completed");
}

void AIAgentSession::set_max_tool_iterations(int p_max) {
	max_tool_iterations = MAX(1, p_max);
}

int AIAgentSession::get_max_tool_iterations() const {
	return max_tool_iterations;
}
