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
#include "modules/ai_agent/editor/ai_settings_panel.h"
#undef private

#include "core/config/project_settings.h"
#include "core/io/dir_access.h"
#include "core/io/file_access.h"
#include "core/os/os.h"
#include "editor/settings/editor_settings.h"
#include "modules/ai_agent/ai_tool_registry.h"
#include "modules/ai_agent/providers/minimax_provider.h"
#include "modules/ai_agent/tools/reference_tools.h"
#include "modules/ai_agent/tools/resource_tools.h"
#include "modules/ai_agent/tools/scene_tools.h"
#include "modules/ai_agent/tools/script_tools.h"
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

class _TestStreamSink : public Object {
	GDCLASS(_TestStreamSink, Object);

protected:
	static void _bind_methods() {
		ClassDB::bind_method(D_METHOD("capture", "message"), &_TestStreamSink::capture);
	}

public:
	Vector<Ref<AIMessage>> chunks;

	void capture(const Ref<AIMessage> &p_message) {
		chunks.push_back(p_message);
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
	GDREGISTER_CLASS(_TestStreamSink);
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
	CHECK(context_message->get_content().contains("Caller-provided context"));
	CHECK(user_message->get_content() == "Hello");
}

TEST_CASE("[AIAgentSession] Assistant thinking markup is extracted from completed replies") {
	AIAgentSession session;
	Ref<AIMessage> message = AIMessage::create_assistant("Before<think>Inspecting files</think>After");

	Ref<AIMessage> sanitized = session._sanitize_assistant_message(message);

	CHECK(sanitized->get_content() == "BeforeAfter");
	CHECK(sanitized->get_thinking_content() == "Inspecting files");
}

TEST_CASE("[AIAgentSession] Leading whitespace after thinking markup is removed from replies") {
	AIAgentSession session;
	Ref<AIMessage> message = AIMessage::create_assistant("<think>Inspecting files</think>\n\nHello");

	Ref<AIMessage> sanitized = session._sanitize_assistant_message(message);

	CHECK(sanitized->get_content() == "Hello");
	CHECK(sanitized->get_thinking_content() == "Inspecting files");
}

TEST_CASE("[AIAgentSession] Stream chunks emit structured thinking without leaking split tags") {
	_ensure_test_classes_registered();

	AIAgentSession session;
	_TestStreamSink *sink = memnew(_TestStreamSink);
	session.connect("stream_chunk", callable_mp(sink, &_TestStreamSink::capture));

	session._on_stream_chunk(AIMessage::create_assistant("Hello <thi"));
	session._on_stream_chunk(AIMessage::create_assistant("nk>plan</think> world"));

	REQUIRE(sink->chunks.size() == 2);
	CHECK(sink->chunks[0]->get_content() == "Hello ");
	CHECK(sink->chunks[0]->get_thinking_content().is_empty());
	CHECK(sink->chunks[1]->get_content() == " world");
	CHECK(sink->chunks[1]->get_thinking_content() == "plan");

	memdelete(sink);
}

TEST_CASE("[AIAgentSession] Stream chunks keep raw think tags out of visible assistant text") {
	AIAgentSession session;

	session._on_stream_chunk(AIMessage::create_assistant("<think>Analyze"));
	CHECK(session.streaming_visible_content.is_empty());
	CHECK(session.streaming_thinking_content.is_empty());

	session._on_stream_chunk(AIMessage::create_assistant(" this</think>Done"));
	CHECK(session.streaming_visible_content == "Done");
	CHECK(session.streaming_thinking_content == "Analyze this");
}

TEST_CASE("[AIAgentSession] Stream chunks drop whitespace immediately after thinking markup") {
	AIAgentSession session;

	session._on_stream_chunk(AIMessage::create_assistant("<think>Analyze"));
	session._on_stream_chunk(AIMessage::create_assistant(" this</think>\n\nDone"));

	CHECK(session.streaming_visible_content == "Done");
	CHECK(session.streaming_thinking_content == "Analyze this");
}

TEST_CASE("[AIAgentSession] Thinking state change signal is registered") {
	CHECK(ClassDB::has_signal("AIAgentSession", "thinking_state_changed"));
}

TEST_CASE("[AIAgentSession] Thinking state changes when the stream exits the think block") {
	AIAgentSession session;

	session._on_stream_chunk(AIMessage::create_assistant("<think>Plan"));
	CHECK(session.streaming_thinking_active);
	session._on_stream_chunk(AIMessage::create_assistant(" carefully</think>Answer"));

	CHECK_FALSE(session.streaming_thinking_active);
}

TEST_CASE("[AIAgentSession] Thinking state waits for split think tags before emitting") {
	AIAgentSession session;

	session._on_stream_chunk(AIMessage::create_assistant("Before <thi"));
	CHECK_FALSE(session.streaming_thinking_active);

	session._on_stream_chunk(AIMessage::create_assistant("nk>Plan"));
	CHECK(session.streaming_thinking_active);

	session._on_stream_chunk(AIMessage::create_assistant("</think>After"));
	CHECK_FALSE(session.streaming_thinking_active);
}

TEST_CASE("[AIAgentSession] Thinking state resets when cancel clears an active stream") {
	AIAgentSession session;

	session._on_stream_chunk(AIMessage::create_assistant("<think>Plan"));
	CHECK(session.streaming_thinking_active);
	session.cancel();

	CHECK_FALSE(session.streaming_thinking_active);
}

TEST_CASE("[AIMessage] Thinking content survives serialization round trips") {
	Ref<AIMessage> message = AIMessage::create_assistant("Visible", TypedArray<Dictionary>(), "Reasoning");

	Dictionary serialized = message->to_dict();
	Ref<AIMessage> restored = AIMessage::from_dict(serialized);

	CHECK(restored->get_content() == "Visible");
	CHECK(restored->get_thinking_content() == "Reasoning");
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

TEST_CASE("[AIAgentSession] Always allow executes approval-gated tools without waiting") {
	_ensure_test_classes_registered();

	AIToolRegistry registry;
	_TestAIToolHandler *handler = memnew(_TestAIToolHandler);
	registry.register_tool("mock_tool", "Test tool", Dictionary(),
			callable_mp(handler, &_TestAIToolHandler::run), true);

	AIAgentSession session;
	Ref<AIAgentConfig> config;
	config.instantiate();
	config->set_approval_policy(AIAgentConfig::APPROVAL_ALWAYS_ALLOW);
	session.config = config;

	Ref<_TestAIProvider> provider;
	provider.instantiate();
	session.provider = provider;
	session.messages.push_back(AIMessage::create_user("Run the tool"));

	TypedArray<Dictionary> tool_calls;
	Dictionary tool_call;
	tool_call["id"] = "call_auto";
	tool_call["type"] = "function";

	Dictionary function;
	function["name"] = "mock_tool";
	function["arguments"] = "{\"value\":\"99\"}";
	tool_call["function"] = function;
	tool_calls.push_back(tool_call);

	session._process_tool_calls(AIMessage::create_assistant("", tool_calls));

	CHECK(session.get_state() == AIAgentSession::STATE_WAITING_FOR_RESPONSE);
	CHECK(session.pending_tool_calls.is_empty());
	CHECK(provider->send_count == 1);
	REQUIRE(session.messages.size() >= 2);
	CHECK(session.messages[1]->get_content().contains("approved:99"));

	memdelete(handler);
}

TEST_CASE("[AIAgentSession] Multiple approval-gated tools advance sequentially") {
	_ensure_test_classes_registered();

	AIToolRegistry registry;
	_TestAIToolHandler *handler = memnew(_TestAIToolHandler);
	registry.register_tool("mock_tool", "Test tool", Dictionary(),
			callable_mp(handler, &_TestAIToolHandler::run), true);

	AIAgentSession session;
	Ref<AIAgentConfig> config;
	config.instantiate();
	config->set_approval_policy(AIAgentConfig::APPROVAL_ASK);
	session.config = config;

	Ref<_TestAIProvider> provider;
	provider.instantiate();
	session.provider = provider;
	session.messages.push_back(AIMessage::create_user("Run two tools"));

	TypedArray<Dictionary> tool_calls;
	for (int i = 0; i < 2; i++) {
		Dictionary tool_call;
		tool_call["id"] = "call_seq_" + itos(i);
		tool_call["type"] = "function";

		Dictionary function;
		function["name"] = "mock_tool";
		function["arguments"] = vformat("{\"value\":\"%d\"}", i + 1);
		tool_call["function"] = function;
		tool_calls.push_back(tool_call);
	}

	session._process_tool_calls(AIMessage::create_assistant("", tool_calls));

	CHECK(session.get_state() == AIAgentSession::STATE_WAITING_FOR_APPROVAL);
	CHECK(session.pending_tool_calls.size() == 2);
	CHECK(provider->send_count == 0);

	session.approve_tool_call("call_seq_0");

	CHECK(session.get_state() == AIAgentSession::STATE_WAITING_FOR_APPROVAL);
	CHECK(session.pending_tool_calls.size() == 1);
	CHECK(provider->send_count == 0);
	REQUIRE(session.messages.size() >= 2);
	CHECK(session.messages[1]->get_content().contains("approved:1"));

	session.approve_tool_call("call_seq_1");

	CHECK(session.get_state() == AIAgentSession::STATE_WAITING_FOR_RESPONSE);
	CHECK(session.pending_tool_calls.is_empty());
	CHECK(provider->send_count == 1);
	REQUIRE(session.messages.size() >= 3);
	CHECK(session.messages[2]->get_content().contains("approved:2"));

	memdelete(handler);
}

TEST_CASE("[AIAgentSession] Switching to always allow resumes a pending approval queue") {
	_ensure_test_classes_registered();

	AIToolRegistry registry;
	_TestAIToolHandler *handler = memnew(_TestAIToolHandler);
	registry.register_tool("mock_tool", "Test tool", Dictionary(),
			callable_mp(handler, &_TestAIToolHandler::run), true);

	AIAgentSession session;
	Ref<AIAgentConfig> config;
	config.instantiate();
	config->set_approval_policy(AIAgentConfig::APPROVAL_ASK);
	session.config = config;

	Ref<_TestAIProvider> provider;
	provider.instantiate();
	session.provider = provider;
	session.messages.push_back(AIMessage::create_user("Run pending tools"));

	TypedArray<Dictionary> tool_calls;
	for (int i = 0; i < 2; i++) {
		Dictionary tool_call;
		tool_call["id"] = "call_resume_" + itos(i);
		tool_call["type"] = "function";

		Dictionary function;
		function["name"] = "mock_tool";
		function["arguments"] = vformat("{\"value\":\"%d\"}", i + 10);
		tool_call["function"] = function;
		tool_calls.push_back(tool_call);
	}

	session._process_tool_calls(AIMessage::create_assistant("", tool_calls));
	CHECK(session.get_state() == AIAgentSession::STATE_WAITING_FOR_APPROVAL);
	CHECK(session.pending_tool_calls.size() == 2);

	config->set_approval_policy(AIAgentConfig::APPROVAL_ALWAYS_ALLOW);
	session._continue_tool_processing();

	CHECK(session.get_state() == AIAgentSession::STATE_WAITING_FOR_RESPONSE);
	CHECK(session.pending_tool_calls.is_empty());
	CHECK(provider->send_count == 1);
	REQUIRE(session.messages.size() >= 3);
	CHECK(session.messages[1]->get_content().contains("approved:10"));
	CHECK(session.messages[2]->get_content().contains("approved:11"));

	memdelete(handler);
}

TEST_CASE("[AIToolRegistry] Static resource tools execute through the registry") {
	AIToolRegistry registry;
	ResourceTools::register_tools();

	const String test_dir = "user://ai_agent_registry_fixture";
	DirAccess::make_dir_recursive_absolute(test_dir);

	{
		Ref<FileAccess> file = FileAccess::open(test_dir.path_join("tool_test.gd"), FileAccess::WRITE);
		REQUIRE(file.is_valid());
		file->store_string("func _ready():\n\tprint(\"hello\")\n\tprint(\"world\")\n");
	}

	Dictionary list_args;
	list_args["path"] = test_dir;
	String list_result = registry.execute_tool("list_directory", list_args);
	CHECK(list_result.contains("tool_test.gd"));

	Dictionary read_args;
	read_args["path"] = test_dir.path_join("tool_test.gd");
	String read_result = registry.execute_tool("read_file", read_args);
	CHECK(read_result.contains("print(\"hello\")"));

	Dictionary grep_args;
	grep_args["pattern"] = "world";
	grep_args["directory"] = test_dir;
	String grep_result = registry.execute_tool("grep_files", grep_args);
	CHECK(grep_result.contains("tool_test.gd:3:"));

	Dictionary search_args;
	search_args["query"] = "hello";
	search_args["directory"] = test_dir;
	search_args["extension"] = "gd";
	String search_result = registry.execute_tool("search_files", search_args);
	CHECK(search_result.contains("tool_test.gd:2:"));
}

TEST_CASE("[AIAgentSession] Tool aliases resolve to grep_files during execution") {
	_ensure_test_classes_registered();

	PackedStringArray aliases;
	aliases.push_back("rg");
	aliases.push_back("grep");
	aliases.push_back("ripgrep");

	for (int i = 0; i < aliases.size(); i++) {
		AIToolRegistry registry;
		_TestAIToolHandler *handler = memnew(_TestAIToolHandler);
		registry.register_tool("grep_files", "Search files", Dictionary(),
				callable_mp(handler, &_TestAIToolHandler::run), false, AIToolRegistry::EXECUTION_READ_ONLY, true);

		AIAgentSession session;
		Ref<AIAgentConfig> config;
		config.instantiate();
		session.config = config;

		Ref<_TestAIProvider> provider;
		provider.instantiate();
		session.provider = provider;
		session.messages.push_back(AIMessage::create_user("Search the project"));

		TypedArray<Dictionary> tool_calls;
		Dictionary tool_call;
		tool_call["id"] = "call_alias_" + itos(i);
		tool_call["type"] = "function";

		Dictionary function;
		function["name"] = aliases[i];
		function["arguments"] = "{\"value\":\"pattern\"}";
		tool_call["function"] = function;
		tool_calls.push_back(tool_call);

		session._process_tool_calls(AIMessage::create_assistant("", tool_calls));

		CHECK(provider->send_count == 1);
		REQUIRE(session.messages.size() >= 2);
		CHECK(session.messages[1]->get_role() == AIMessage::ROLE_TOOL);
		CHECK(session.messages[1]->get_content().contains("approved:pattern"));
		CHECK((String)session.messages[1]->get_metadata().get("tool_name", "") == "grep_files");

		memdelete(handler);
	}
}

TEST_CASE("[AIAgentConfig] Provider defaults reset the model when provider changes") {
	Ref<AIAgentConfig> config;
	config.instantiate();

	config->set_model_name("custom-model");
	config->set_provider_type(AIAgentConfig::PROVIDER_ANTHROPIC);
	config->apply_provider_defaults(true, true);

	CHECK(config->get_model_name() == "claude-sonnet-4-5-20250929");
	CHECK(config->get_base_url().is_empty());
}

TEST_CASE("[AIAgentConfig] Approval policy defaults to ask") {
	Ref<AIAgentConfig> config;
	config.instantiate();

	CHECK(config->get_approval_policy() == AIAgentConfig::APPROVAL_ASK);
}

TEST_CASE("[AISettingsPanel] Approval policy persists through editor settings") {
	EditorSettings *settings = EditorSettings::get_singleton();
	REQUIRE(settings != nullptr);

	settings->set("_ai_agent/approval_policy", (int)AIAgentConfig::APPROVAL_ASK);

	AISettingsPanel first_panel;
	first_panel._load_config();
	REQUIRE(first_panel.get_config().is_valid());
	first_panel.get_config()->set_approval_policy(AIAgentConfig::APPROVAL_ALWAYS_ALLOW);
	first_panel.persist_config();

	AISettingsPanel second_panel;
	second_panel._load_config();
	REQUIRE(second_panel.get_config().is_valid());
	CHECK(second_panel.get_config()->get_approval_policy() == AIAgentConfig::APPROVAL_ALWAYS_ALLOW);

	settings->set("_ai_agent/approval_policy", (int)AIAgentConfig::APPROVAL_ASK);
}

TEST_CASE("[AIAgentSession] Resolved run config applies mode tool policy and provider budgets") {
	PackedStringArray tools;
	tools.push_back("inspect_node");
	tools.push_back("get_class_reference");
	tools.push_back("get_script_reference");
	tools.push_back("read_file");
	tools.push_back("write_file");
	tools.push_back("grep_files");
	tools.push_back("search_files");

	Ref<AIAgentConfig> config;
	config.instantiate();
	config->set_provider_type(AIAgentConfig::PROVIDER_OPENAI);
	config->apply_provider_defaults(true, true);

	ResolvedAgentRunConfig ask_run = ai_agent_resolve_run_config(config, AI_AGENT_MODE_ASK, tools);
	CHECK(ask_run.allowed_tools.has("inspect_node"));
	CHECK(ask_run.allowed_tools.has("get_class_reference"));
	CHECK(ask_run.allowed_tools.has("get_script_reference"));
	CHECK(ask_run.allowed_tools.has("read_file"));
	CHECK(ask_run.allowed_tools.has("grep_files"));
	CHECK(ask_run.allowed_tools.has("search_files"));
	CHECK_FALSE(ask_run.allowed_tools.has("write_file"));
	CHECK_FALSE(ask_run.use_temperature);
	CHECK(ask_run.use_max_output_tokens);
	CHECK(ask_run.max_output_tokens == 4096);

	ResolvedAgentRunConfig edit_run = ai_agent_resolve_run_config(config, AI_AGENT_MODE_EDIT, tools);
	CHECK(edit_run.allowed_tools.has("write_file"));
	CHECK(edit_run.allowed_tools.size() == tools.size());
	CHECK(edit_run.max_output_tokens == 6144);
}

TEST_CASE("[AIAgentSession] Custom provider uses the OpenAI-compatible implementation") {
	AIAgentSession session;
	Ref<AIAgentConfig> config;
	config.instantiate();
	config->set_provider_type(AIAgentConfig::PROVIDER_CUSTOM);
	config->set_model_name("custom-model");
	config->set_base_url("https://example.invalid/v1");

	session.set_config(config);

	CHECK(session.provider.is_valid());
	CHECK(session.provider->get_model_name() == "custom-model");
	CHECK(session.provider->get_base_url() == "https://example.invalid/v1");
}

TEST_CASE("[MiniMaxProvider] Merges multiple system messages into one request entry") {
	MiniMaxProvider provider;

	TypedArray<Ref<AIMessage>> messages;
	messages.push_back(AIMessage::create_system("Harness prompt"));
	messages.push_back(AIMessage::create_system("Execution settings"));
	messages.push_back(AIMessage::create_user("Hello"));

	Dictionary request = provider.format_request(messages, TypedArray<Dictionary>());
	Array formatted_messages = request["messages"];

	CHECK(formatted_messages.size() == 2);

	Dictionary system_message = formatted_messages[0];
	CHECK(system_message["role"] == "system");
	CHECK(((String)system_message["content"]).contains("Harness prompt"));
	CHECK(((String)system_message["content"]).contains("Execution settings"));

	Dictionary user_message = formatted_messages[1];
	CHECK(user_message["role"] == "user");
	CHECK(user_message["content"] == "Hello");
}

TEST_CASE("[AIAgentSession] Debug mode profile has diagnostic tools and correct properties") {
	AIAgentModeProfile profile = ai_agent_get_mode_profile(AI_AGENT_MODE_DEBUG);

	CHECK(profile.title == "Debug");
	CHECK(profile.temperature == 0.0f);
	CHECK(profile.preferred_max_output_tokens == 6144);
	CHECK(profile.allowed_tools.has("get_console_output"));
	CHECK(profile.allowed_tools.has("get_performance_metrics"));
	CHECK(profile.allowed_tools.has("inspect_node"));
	CHECK(profile.allowed_tools.has("get_class_reference"));
	CHECK(profile.allowed_tools.has("get_script_reference"));
	CHECK(profile.allowed_tools.has("read_file"));
	CHECK(profile.allowed_tools.has("get_script_content"));
	CHECK(profile.allowed_tools.has("grep_files"));
	CHECK(profile.allowed_tools.has("search_files"));
	CHECK(!profile.harness_prompt.is_empty());
	CHECK(profile.harness_prompt.contains("Debug"));
	CHECK(profile.harness_prompt.contains("grep_files"));
	CHECK(profile.harness_prompt.contains("inspect_node"));
}

TEST_CASE("[AIAgentSession] Debug mode run config resolves diagnostic tool subset") {
	PackedStringArray tools;
	tools.push_back("inspect_node");
	tools.push_back("get_class_reference");
	tools.push_back("get_script_reference");
	tools.push_back("read_file");
	tools.push_back("write_file");
	tools.push_back("get_console_output");
	tools.push_back("grep_files");
	tools.push_back("search_files");

	Ref<AIAgentConfig> config;
	config.instantiate();
	config->set_provider_type(AIAgentConfig::PROVIDER_OPENAI);
	config->apply_provider_defaults(true, true);

	ResolvedAgentRunConfig debug_run = ai_agent_resolve_run_config(config, AI_AGENT_MODE_DEBUG, tools);
	CHECK(debug_run.allowed_tools.has("inspect_node"));
	CHECK(debug_run.allowed_tools.has("get_class_reference"));
	CHECK(debug_run.allowed_tools.has("get_script_reference"));
	CHECK(debug_run.allowed_tools.has("read_file"));
	CHECK(debug_run.allowed_tools.has("get_console_output"));
	CHECK(debug_run.allowed_tools.has("grep_files"));
	CHECK(debug_run.allowed_tools.has("search_files"));
	CHECK_FALSE(debug_run.allowed_tools.has("write_file"));
	CHECK(debug_run.max_output_tokens == 6144);
}

TEST_CASE("[AIAgentConfig] Per-mode model override takes priority in resolved config") {
	Ref<AIAgentConfig> config;
	config.instantiate();
	config->set_provider_type(AIAgentConfig::PROVIDER_OPENAI);
	config->apply_provider_defaults(true, true);

	CHECK_FALSE(config->has_mode_model_override((int)AI_AGENT_MODE_PLAN));

	config->set_mode_model_override((int)AI_AGENT_MODE_PLAN, "gpt-5");

	CHECK(config->has_mode_model_override((int)AI_AGENT_MODE_PLAN));
	CHECK(config->get_mode_model_override((int)AI_AGENT_MODE_PLAN) == "gpt-5");

	PackedStringArray tools;
	ResolvedAgentRunConfig plan_run = ai_agent_resolve_run_config(config, AI_AGENT_MODE_PLAN, tools);
	CHECK(plan_run.model_name == "gpt-5");

	// Ask mode should still use the global model (no override set).
	ResolvedAgentRunConfig ask_run = ai_agent_resolve_run_config(config, AI_AGENT_MODE_ASK, tools);
	CHECK(ask_run.model_name == "gpt-5-mini");

	// Clear the override.
	config->clear_mode_model_override((int)AI_AGENT_MODE_PLAN);
	CHECK_FALSE(config->has_mode_model_override((int)AI_AGENT_MODE_PLAN));
}

TEST_CASE("[AIAgentSession] Orchestrate mode profile and tool schema are exposed") {
	AIAgentModeProfile profile = ai_agent_get_mode_profile(AI_AGENT_MODE_ORCHESTRATE);
	CHECK(profile.title == "Orchestrate");
	CHECK(profile.icon_name == "AIAgentModeOrchestrate");
	CHECK(profile.allowed_tools.has("grep_files"));
	CHECK(profile.allowed_tools.has("inspect_node"));
	CHECK(profile.allowed_tools.has("get_class_reference"));
	CHECK(profile.harness_prompt.contains("grep_files"));
	CHECK(profile.harness_prompt.contains("inspect_node"));

	AIAgentSession session;
	session.mode = AI_AGENT_MODE_ORCHESTRATE;
	TypedArray<Dictionary> tool_schemas = session._build_orchestrator_tool_schemas();
	REQUIRE(tool_schemas.size() == 1);
	Dictionary function = ((Dictionary)tool_schemas[0])["function"];
	CHECK(function["name"] == "new_task");
}

TEST_CASE("[AIAgentSession] Resolved run config estimates context window from model") {
	PackedStringArray tools;
	Ref<AIAgentConfig> config;
	config.instantiate();
	config->set_provider_type(AIAgentConfig::PROVIDER_ANTHROPIC);
	config->apply_provider_defaults(true, true);

	ResolvedAgentRunConfig run = ai_agent_resolve_run_config(config, AI_AGENT_MODE_PLAN, tools);
	CHECK(run.estimated_context_window >= 128000);
}

TEST_CASE("[AIToolRegistry] Tool usage guide includes hints and ignores plain tools") {
	_ensure_test_classes_registered();

	AIToolRegistry registry;
	_TestAIToolHandler *handler = memnew(_TestAIToolHandler);
	registry.register_tool("plain_tool", "No hints", Dictionary(), callable_mp(handler, &_TestAIToolHandler::run));
	registry.register_tool("hinted_tool", "With hints", Dictionary(), callable_mp(handler, &_TestAIToolHandler::run), false, AIToolRegistry::EXECUTION_READ_ONLY, true,
			"Use when you need a guided tool selection example.", "a structured example payload");

	String usage_guide = registry.get_tool_usage_guide();
	CHECK(usage_guide.contains("hinted_tool"));
	CHECK(usage_guide.contains("Returns a structured example payload."));
	CHECK_FALSE(usage_guide.contains("plain_tool"));

	memdelete(handler);
}

TEST_CASE("[AIAgentSession] Effective system prompt includes tool usage guide and reference rule") {
	_ensure_test_classes_registered();

	AIToolRegistry registry;
	_TestAIToolHandler *handler = memnew(_TestAIToolHandler);
	registry.register_tool("inspect_node", "Inspect node", Dictionary(), callable_mp(handler, &_TestAIToolHandler::run), false, AIToolRegistry::EXECUTION_READ_ONLY, true,
			"Use before mutating unfamiliar nodes.", "a node snapshot");

	AIAgentSession session;
	Ref<AIAgentConfig> config;
	config.instantiate();
	config->set_provider_type(AIAgentConfig::PROVIDER_OPENAI);
	config->apply_provider_defaults(true, true);
	session.config = config;
	session.mode = AI_AGENT_MODE_ASK;

	PackedStringArray tools;
	tools.push_back("inspect_node");
	ResolvedAgentRunConfig run_config = ai_agent_resolve_run_config(config, AI_AGENT_MODE_ASK, tools);
	String prompt = session._build_effective_system_prompt(run_config);
	CHECK(prompt.contains("Tool usage guide"));
	CHECK(prompt.contains("inspect_node"));
	CHECK(prompt.contains("Reference rule"));

	memdelete(handler);
}

TEST_CASE("[AIToolRegistry] Native reference and latent scene tools are registered") {
	AIToolRegistry registry;
	SceneTools::register_tools();
	ScriptTools::register_tools();
	ReferenceTools::register_tools();

	CHECK(registry.has_tool("reparent_node"));
	CHECK(registry.has_tool("duplicate_node"));
	CHECK(registry.has_tool("connect_signal"));
	CHECK(registry.has_tool("disconnect_signal"));
	CHECK(registry.has_tool("add_to_group"));
	CHECK(registry.has_tool("instantiate_scene"));
	CHECK(registry.has_tool("detach_script"));
	CHECK(registry.has_tool("get_project_info"));
	CHECK(registry.has_tool("get_godot_version"));
	CHECK(registry.has_tool("inspect_node"));
	CHECK(registry.has_tool("get_class_reference"));
	CHECK(registry.has_tool("get_script_reference"));
}

TEST_CASE("[ReferenceTools] Project info, engine version, script metadata, and class reference are available") {
	const Variant project_info_variant = ReferenceTools::tool_get_project_info(Dictionary());
	REQUIRE(project_info_variant.get_type() == Variant::DICTIONARY);
	Dictionary project_info = project_info_variant;
	CHECK(project_info.has("project"));

	const Variant version_variant = ReferenceTools::tool_get_godot_version(Dictionary());
	REQUIRE(version_variant.get_type() == Variant::DICTIONARY);
	Dictionary version_info = version_variant;
	CHECK(version_info.has("major"));

	const String script_path = vformat("user://ai_agent_reference_fixture_%d_%d.gd",
			OS::get_singleton()->get_process_id(),
			OS::get_singleton()->get_ticks_usec());
	{
		Ref<FileAccess> file = FileAccess::open(script_path, FileAccess::WRITE);
		REQUIRE(file.is_valid());
		file->store_string("func ping() -> void:\n\tpass\n");
	}

	Dictionary script_args;
	script_args["path"] = script_path;
	const Variant script_variant = ReferenceTools::tool_get_script_reference(script_args);
	REQUIRE(script_variant.get_type() == Variant::DICTIONARY);
	Dictionary script_info = script_variant;
	CHECK(script_info["path"] == script_path);
	CHECK_FALSE(script_info.has("error"));
	TypedArray<Dictionary> script_methods = script_info.get("methods", TypedArray<Dictionary>());
	bool found_ping = false;
	for (int i = 0; i < script_methods.size(); i++) {
		if (((Dictionary)script_methods[i]).get("name", "") == "ping") {
			found_ping = true;
			break;
		}
	}
	CHECK(found_ping);

	Dictionary class_args;
	class_args["class_name"] = "Node2D";
	const Variant class_variant = ReferenceTools::tool_get_class_reference(class_args);
	REQUIRE(class_variant.get_type() == Variant::DICTIONARY);
	Dictionary class_info = class_variant;
	CHECK(class_info["class_name"] == "Node2D");
	CHECK(class_info.has("inherits"));
	CHECK(class_info.has("methods"));
}

TEST_CASE("[AIAgentSession] Large tool results are written to artifact files") {
	AIAgentSession session;
	String long_text;
	for (int i = 0; i < 9000; i++) {
		long_text += "x";
	}

	Dictionary metadata = session._write_tool_result_artifact("tool_call_large", long_text);
	REQUIRE(metadata.has("artifact_path"));
	const String artifact_path = metadata["artifact_path"];
	CHECK(FileAccess::exists(artifact_path));
}

TEST_CASE("[ResourceTools] grep_files supports literal and compatibility search") {
	const String test_dir = "user://ai_agent_search_fixture";
	DirAccess::make_dir_recursive_absolute(test_dir);

	{
		Ref<FileAccess> file = FileAccess::open(test_dir.path_join("player.gd"), FileAccess::WRITE);
		REQUIRE(file.is_valid());
		file->store_string("func _ready():\n\tprint(\"foo\")\n\tprint(\"bar\")\n");
	}
	{
		Ref<FileAccess> file = FileAccess::open(test_dir.path_join("notes.txt"), FileAccess::WRITE);
		REQUIRE(file.is_valid());
		file->store_string("foo\nfoo\nfoo\nfoo\n");
	}

	Dictionary grep_args;
	grep_args["pattern"] = "foo";
	grep_args["directory"] = test_dir;
	grep_args["glob"] = "*.gd";
	String grep_result = ResourceTools::tool_grep_files(grep_args);
	CHECK(grep_result.contains("player.gd:2:"));
	CHECK_FALSE(grep_result.contains("notes.txt"));

	Dictionary search_args;
	search_args["query"] = "bar";
	search_args["directory"] = test_dir;
	search_args["extension"] = "gd";
	String compatibility_result = ResourceTools::tool_search_files(search_args);
	CHECK(compatibility_result.contains("player.gd:3:"));
}

TEST_CASE("[ResourceTools] grep_files supports regex and truncation") {
	const String test_dir = "user://ai_agent_search_fixture_regex";
	DirAccess::make_dir_recursive_absolute(test_dir);

	{
		Ref<FileAccess> file = FileAccess::open(test_dir.path_join("enemy.gd"), FileAccess::WRITE);
		REQUIRE(file.is_valid());
		file->store_string("foo(1)\nfoo(2)\nfoo(3)\n");
	}

	Dictionary regex_args;
	regex_args["pattern"] = "foo\\([0-9]+\\)";
	regex_args["directory"] = test_dir;
	regex_args["use_regex"] = true;
	regex_args["max_results"] = 2;
	regex_args["context_lines"] = 1;
	String regex_result = ResourceTools::tool_grep_files(regex_args);
	CHECK(regex_result.contains("enemy.gd:1:"));
	CHECK(regex_result.contains("enemy.gd:2:"));
	CHECK(regex_result.contains("truncated"));
	CHECK(regex_result.contains("2- foo(2)"));
}

TEST_CASE("[SceneTools] AI node name sanitization produces valid non-empty names") {
	const String whitespace_name = SceneTools::sanitize_ai_node_name("   ", "Node2D");
	CHECK_FALSE(whitespace_name.is_empty());
	CHECK(whitespace_name == whitespace_name.validate_node_name());

	const String punctuation_name = SceneTools::sanitize_ai_node_name("!!!", "Node2D");
	CHECK_FALSE(punctuation_name.is_empty());
	CHECK(punctuation_name == punctuation_name.validate_node_name());

	Node *parent = memnew(Node);
	parent->set_name("Root");
	Node *existing = memnew(Node);
	existing->set_name("Node2D");
	parent->add_child(existing);

	Node *candidate = memnew(Node);
	const String resolved_name = SceneTools::resolve_ai_node_name(parent, candidate, "!!!", "Node2D");
	CHECK_FALSE(resolved_name.is_empty());
	CHECK(resolved_name == resolved_name.validate_node_name());
	candidate->set_name(resolved_name);
	CHECK_FALSE(String(candidate->get_name()).is_empty());

	parent->add_child(candidate);
	memdelete(parent);
}

TEST_CASE("[OS] Path normalization reuses existing directory case for user data paths") {
	const String data_root = OS::get_singleton()->get_data_path();
	REQUIRE_FALSE(data_root.is_empty());

	const String actual_path = data_root.path_join("godoty").path_join("app_userdata").path_join("Testing").path_join("ai_sessions");
	DirAccess::make_dir_recursive_absolute(actual_path);

	const String requested_path = data_root.path_join("Godoty").path_join("app_userdata").path_join("Testing").path_join("ai_sessions");
	CHECK(OS::normalize_existing_path_case(requested_path) == actual_path);
}

TEST_CASE("[AIAgentSession] Session persistence restores most recent idle session") {
	DirAccess::make_dir_recursive_absolute("user://ai_sessions");
	Ref<DirAccess> dir = DirAccess::open("user://ai_sessions");
	if (dir.is_valid()) {
		dir->list_dir_begin();
		String item = dir->get_next();
		while (!item.is_empty()) {
			if (!dir->current_is_dir()) {
				dir->remove("user://ai_sessions/" + item);
			}
			item = dir->get_next();
		}
		dir->list_dir_end();
	}

	AIAgentSession writer;
	writer.messages.push_back(AIMessage::create_system("Persisted system"));
	writer.messages.push_back(AIMessage::create_user("Hello restore"));
	writer.state = AIAgentSession::STATE_IDLE;
	writer._autosave_session();
	const String save_path = ProjectSettings::get_singleton()->globalize_path(writer._get_session_save_path());
	CHECK(FileAccess::exists(save_path));
	CHECK(OS::normalize_existing_path_case(save_path) == save_path);

	AIAgentSession reader;
	CHECK(reader.restore_last_saved_session());
	CHECK(reader.get_message_count() >= 2);
	CHECK(reader.get_mode() == writer.get_mode());
}

TEST_CASE("[AIAgentSession] Undo all restores every snapshot batch in the session") {
	const String test_dir = "user://ai_agent_undo_fixture";
	DirAccess::make_dir_recursive_absolute(test_dir);
	const String first_path = test_dir.path_join("first.txt");
	const String second_path = test_dir.path_join("second.txt");

	{
		Ref<FileAccess> file = FileAccess::open(first_path, FileAccess::WRITE);
		REQUIRE(file.is_valid());
		file->store_string("changed-first");
	}
	{
		Ref<FileAccess> file = FileAccess::open(second_path, FileAccess::WRITE);
		REQUIRE(file.is_valid());
		file->store_string("changed-second");
	}

	AIAgentSession session;
	AIAgentSession::SessionSnapshotBatch first_batch;
	Array first_entries;
	Dictionary first_entry;
	first_entry["path"] = first_path;
	first_entry["existed"] = true;
	first_entry["content"] = "original-first";
	first_entries.push_back(first_entry);
	first_batch.data["kind"] = "files";
	first_batch.data["entries"] = first_entries;

	AIAgentSession::SessionSnapshotBatch second_batch;
	Array second_entries;
	Dictionary second_entry;
	second_entry["path"] = second_path;
	second_entry["existed"] = true;
	second_entry["content"] = "original-second";
	second_entries.push_back(second_entry);
	second_batch.data["kind"] = "files";
	second_batch.data["entries"] = second_entries;

	session.snapshot_batches.push_back(first_batch);
	session.snapshot_batches.push_back(second_batch);

	CHECK(session.has_ai_edit_snapshots());
	CHECK(session.undo_all_ai_edits());
	CHECK_FALSE(session.has_ai_edit_snapshots());
	CHECK(session.snapshot_batches.is_empty());

	Ref<FileAccess> restored_first = FileAccess::open(first_path, FileAccess::READ);
	REQUIRE(restored_first.is_valid());
	CHECK(restored_first->get_as_text() == "original-first");

	Ref<FileAccess> restored_second = FileAccess::open(second_path, FileAccess::READ);
	REQUIRE(restored_second.is_valid());
	CHECK(restored_second->get_as_text() == "original-second");
}

TEST_CASE("[AIAgentSession] Summarization preserves the last four non-system messages") {
	AIAgentSession session;
	Ref<AIAgentConfig> config;
	config.instantiate();
	session.set_config(config);
	session.messages.push_back(AIMessage::create_system("Harness"));
	for (int i = 0; i < 6; i++) {
		String content;
		for (int j = 0; j < 12000; j++) {
			content += String::chr('a' + (i % 5));
		}
		session.messages.push_back(i % 2 == 0 ? AIMessage::create_user(content) : AIMessage::create_assistant(content));
	}

	session._maybe_summarize_history();

	REQUIRE(session.messages.size() >= 5);
	CHECK(session.messages[1]->get_role() == AIMessage::ROLE_SYSTEM);
	CHECK(session.messages[1]->get_content().contains("Previous context summary"));
	int non_system_count = 0;
	for (int i = session.messages.size() - 1; i >= 0; i--) {
		if (session.messages[i]->get_role() != AIMessage::ROLE_SYSTEM) {
			non_system_count++;
		}
	}
	CHECK(non_system_count >= 4);
}

} // namespace TestAIAgentSession
