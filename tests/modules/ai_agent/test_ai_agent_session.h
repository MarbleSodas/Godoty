/**************************************************************************/
/*  test_ai_agent_session.h                                               */
/**************************************************************************/
/*                         This file is part of:                          */
/*                             GODOT ENGINE                               */
/*                        https://godotengine.org                         */
/**************************************************************************/

#pragma once

#define private public
#include "modules/ai_agent/ai_agent_session.h"
#undef private

#include "tests/test_macros.h"

class _TestAIProvider : public AIProvider {
	GDCLASS(_TestAIProvider, AIProvider);

protected:
	static void _bind_methods() {}

public:
	int send_count = 0;
	int stream_count = 0;
	int cancel_count = 0;
	TypedArray<Ref<AIMessage>> last_messages;
	TypedArray<Dictionary> last_tools;

	Error send_message(const TypedArray<Ref<AIMessage>> &p_messages,
			const TypedArray<Dictionary> &p_tools,
			const Callable &p_callback) override {
		send_count++;
		last_messages = p_messages;
		last_tools = p_tools;
		return OK;
	}

	Error stream_message(const TypedArray<Ref<AIMessage>> &p_messages,
			const TypedArray<Dictionary> &p_tools,
			const Callable &p_stream_callback,
			const Callable &p_complete_callback) override {
		stream_count++;
		last_messages = p_messages;
		last_tools = p_tools;
		return OK;
	}

	void cancel() override {
		cancel_count++;
	}

	Dictionary format_request(const TypedArray<Ref<AIMessage>> &p_messages,
			const TypedArray<Dictionary> &p_tools) const override {
		return Dictionary();
	}

	Ref<AIMessage> parse_response(const Dictionary &p_response) const override {
		return Ref<AIMessage>();
	}
};

class _TestAIToolHandler : public Object {
	GDCLASS(_TestAIToolHandler, Object);

protected:
	static void _bind_methods() {
		ClassDB::bind_method(D_METHOD("run", "arguments"), &_TestAIToolHandler::run);
	}

public:
	String run(const Dictionary &p_arguments) {
		return vformat("approved:%s", String(p_arguments.get("value", "")));
	}
};

namespace TestAIAgentSession {

static void _ensure_test_classes_registered() {
	static bool registered = false;
	if (registered) {
		return;
	}

	GDREGISTER_CLASS(_TestAIProvider);
	GDREGISTER_CLASS(_TestAIToolHandler);
	registered = true;
}

TEST_CASE("[AIAgentSession] Provider error replies become session errors") {
	AIAgentSession session;
	session._on_response_received(AIMessage::create_assistant("Error: Request timed out."));

	CHECK(session.get_state() == AIAgentSession::STATE_ERROR);
	CHECK(session.get_message_count() == 0);
}

TEST_CASE("[AIAgentSession] Request context is injected ephemerally") {
	AIAgentSession session;
	session.messages.push_back(AIMessage::create_system("System"));
	session.messages.push_back(AIMessage::create_user("Hello"));

	Dictionary context;
	context["scene"] = "Main";

	TypedArray<Ref<AIMessage>> request_messages = session._build_request_messages(context);
	Ref<AIMessage> context_message = request_messages[1];
	Ref<AIMessage> user_message = request_messages[2];

	CHECK(session.messages.size() == 2);
	CHECK(request_messages.size() == 3);
	CHECK(context_message->get_role() == AIMessage::ROLE_SYSTEM);
	CHECK(context_message->get_content().contains("Current editor context"));
	CHECK(user_message->get_content() == "Hello");
}

TEST_CASE("[AIAgentSession] Approving a pending tool executes it and continues the loop") {
	_ensure_test_classes_registered();

	AIToolRegistry registry;
	_TestAIToolHandler *handler = memnew(_TestAIToolHandler);
	registry.register_tool("mock_tool", "Test tool", Dictionary(),
			callable_mp(handler, &_TestAIToolHandler::run), true);

	AIAgentSession session;
	Ref<AIAgentConfig> config;
	config.instantiate();
	config->set_stream_responses(false);
	session.config = config;

	Ref<_TestAIProvider> provider;
	provider.instantiate();
	session.provider = provider;
	session.messages.push_back(AIMessage::create_user("Run the tool"));

	TypedArray<Dictionary> tool_calls;
	Dictionary tool_call;
	tool_call["id"] = "call_1";
	tool_call["type"] = "function";

	Dictionary function;
	function["name"] = "mock_tool";
	function["arguments"] = "{\"value\":\"42\"}";
	tool_call["function"] = function;
	tool_calls.push_back(tool_call);

	session._process_tool_calls(AIMessage::create_assistant("", tool_calls));

	CHECK(session.get_state() == AIAgentSession::STATE_WAITING_FOR_APPROVAL);
	CHECK(session.pending_tool_calls.size() == 1);

	session.approve_tool_call("call_1");

	CHECK(provider->send_count == 1);
	CHECK(session.pending_tool_calls.is_empty());
	CHECK(session.get_state() == AIAgentSession::STATE_WAITING_FOR_RESPONSE);
	CHECK(session.messages.size() == 2);
	CHECK(session.messages[1]->get_role() == AIMessage::ROLE_TOOL);
	CHECK(session.messages[1]->get_tool_call_id() == "call_1");
	CHECK(session.messages[1]->get_content().contains("approved:42"));

	memdelete(handler);
}

} // namespace TestAIAgentSession
