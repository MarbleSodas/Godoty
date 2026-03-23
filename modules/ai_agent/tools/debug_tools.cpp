/**************************************************************************/
/*  debug_tools.cpp                                                       */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "debug_tools.h"

#include "main/performance.h"
#include "modules/ai_agent/ai_tool_registry.h"

#ifdef TOOLS_ENABLED
#include "editor/debugger/editor_debugger_node.h"
#include "editor/debugger/script_editor_debugger.h"
#include "editor/docks/editor_dock_manager.h"
#include "editor/editor_node.h"
#include "editor/editor_log.h"
#endif

namespace {

#ifdef TOOLS_ENABLED
Dictionary _make_debugger_result_base(EditorDebuggerNode *p_debugger_node, int p_requested_session, int p_resolved_session) {
	Dictionary result;
	result["requested_session_index"] = p_requested_session;
	result["selected_session_index"] = p_debugger_node ? p_debugger_node->get_current_debugger_index() : -1;
	result["resolved_session_index"] = p_resolved_session;
	result["session_count"] = p_debugger_node ? p_debugger_node->get_debugger_count() : 0;
	return result;
}

Dictionary _make_debugger_error_result(const String &p_message, EditorDebuggerNode *p_debugger_node, int p_requested_session, int p_resolved_session = -1) {
	Dictionary result = _make_debugger_result_base(p_debugger_node, p_requested_session, p_resolved_session);
	result["ok"] = false;
	result["message"] = p_message;
	return result;
}

bool _resolve_debugger_session(const Dictionary &p_args, EditorDebuggerNode *&r_debugger_node, ScriptEditorDebugger *&r_debugger, int &r_requested_session, int &r_resolved_session, Dictionary &r_error_result) {
	r_requested_session = (int)p_args.get("session_index", -1);
	r_resolved_session = -1;
	r_debugger_node = EditorDebuggerNode::get_singleton();
	r_debugger = nullptr;

	if (!r_debugger_node) {
		r_error_result = _make_debugger_error_result("Debugger panel is not available.", nullptr, r_requested_session);
		return false;
	}

	const int debugger_count = r_debugger_node->get_debugger_count();
	if (debugger_count <= 0) {
		r_error_result = _make_debugger_error_result("No debugger sessions are available.", r_debugger_node, r_requested_session);
		return false;
	}

	r_resolved_session = r_requested_session >= 0 ? r_requested_session : r_debugger_node->get_current_debugger_index();
	if (r_resolved_session < 0 || r_resolved_session >= debugger_count) {
		r_error_result = _make_debugger_error_result(vformat("Invalid session_index %d. Expected 0 to %d.", r_resolved_session, debugger_count - 1), r_debugger_node, r_requested_session);
		return false;
	}

	r_debugger = r_debugger_node->get_debugger(r_resolved_session);
	if (!r_debugger) {
		r_error_result = _make_debugger_error_result(vformat("Debugger session %d is unavailable.", r_resolved_session), r_debugger_node, r_requested_session, r_resolved_session);
		return false;
	}

	return true;
}
#endif

} // namespace

void DebugTools::_bind_methods() {
	ClassDB::bind_static_method("DebugTools", D_METHOD("register_tools"), &DebugTools::register_tools);
}

void DebugTools::register_tools() {
	AIToolRegistry *reg = AIToolRegistry::get_singleton();
	ERR_FAIL_NULL(reg);

	// get_console_output
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary lines_prop;
		lines_prop["type"] = "integer";
		lines_prop["description"] = "Number of recent lines to retrieve (default: 50)";
		props["lines"] = lines_prop;
		params["properties"] = props;
		reg->register_tool("get_console_output", "Get recent console output/log messages", params, callable_mp_static(&DebugTools::tool_get_console_output), false, AIToolRegistry::EXECUTION_READ_ONLY, true,
				"Use first in debug workflows to inspect current runtime errors, warnings, and log output.",
				"recent editor log lines as plain text");
	}

	// pause_game
	{
		Dictionary params;
		params["type"] = "object";
		params["properties"] = Dictionary();
		reg->register_tool("pause_game", "Pause the running game", params, callable_mp_static(&DebugTools::tool_pause_game), false, AIToolRegistry::EXECUTION_MUTATING_EDITOR);
	}

	// resume_game
	{
		Dictionary params;
		params["type"] = "object";
		params["properties"] = Dictionary();
		reg->register_tool("resume_game", "Resume the paused game", params, callable_mp_static(&DebugTools::tool_resume_game), false, AIToolRegistry::EXECUTION_MUTATING_EDITOR);
	}

	// get_performance_metrics
	{
		Dictionary params;
		params["type"] = "object";
		params["properties"] = Dictionary();
		reg->register_tool("get_performance_metrics", "Get current performance metrics (FPS, memory, draw calls)", params, callable_mp_static(&DebugTools::tool_get_performance_metrics), false, AIToolRegistry::EXECUTION_READ_ONLY, true,
				"Use when diagnosing performance or runtime-state issues in the running game.",
				"a readable performance summary with FPS, timings, memory, node count, and draw calls");
	}

	// show_debugger_panel
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary session_prop;
		session_prop["type"] = "integer";
		session_prop["description"] = "Optional debugger session index to focus.";
		props["session_index"] = session_prop;
		params["properties"] = props;
		reg->register_tool("show_debugger_panel", "Open and focus the editor Debugger panel", params, callable_mp_static(&DebugTools::tool_show_debugger_panel), false, AIToolRegistry::EXECUTION_MUTATING_EDITOR, false,
				"Use when you want the editor to surface the existing Debugger dock for the current or specified session.",
				"a short confirmation describing which debugger session was focused");
	}

	// get_debugger_state
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary session_prop;
		session_prop["type"] = "integer";
		session_prop["description"] = "Optional debugger session index to inspect.";
		props["session_index"] = session_prop;
		params["properties"] = props;
		reg->register_tool("get_debugger_state", "Get a structured snapshot of the current debugger session", params, callable_mp_static(&DebugTools::tool_get_debugger_state), false, AIToolRegistry::EXECUTION_READ_ONLY, true,
				"Use before guessing about runtime failures so you can confirm whether a debug session is active, paused, and where it stopped.",
				"a structured debugger summary with session state, counts, and current stack location when available");
	}

	// get_debugger_stack
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary session_prop;
		session_prop["type"] = "integer";
		session_prop["description"] = "Optional debugger session index to inspect.";
		props["session_index"] = session_prop;
		Dictionary frames_prop;
		frames_prop["type"] = "integer";
		frames_prop["description"] = "Maximum number of stack frames to return (default: 20, max: 200).";
		props["max_frames"] = frames_prop;
		params["properties"] = props;
		reg->register_tool("get_debugger_stack", "Get the current paused stack trace from the editor debugger", params, callable_mp_static(&DebugTools::tool_get_debugger_stack), false, AIToolRegistry::EXECUTION_READ_ONLY, true,
				"Use after a pause or runtime error to inspect the current stack frames and selected frame.",
				"a structured stack snapshot with capped frames and selected frame metadata");
	}

	// get_debugger_errors
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary session_prop;
		session_prop["type"] = "integer";
		session_prop["description"] = "Optional debugger session index to inspect.";
		props["session_index"] = session_prop;
		Dictionary items_prop;
		items_prop["type"] = "integer";
		items_prop["description"] = "Maximum number of debugger errors or warnings to return (default: 20, max: 200).";
		props["max_items"] = items_prop;
		params["properties"] = props;
		reg->register_tool("get_debugger_errors", "Get structured errors and warnings from the editor debugger", params, callable_mp_static(&DebugTools::tool_get_debugger_errors), false, AIToolRegistry::EXECUTION_READ_ONLY, true,
				"Use when console output is not enough and you need the debugger's structured error list with source and stack summaries.",
				"a capped list of debugger errors and warnings with source locations and stack trace summaries");
	}

	// get_debugger_remote_scene
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary session_prop;
		session_prop["type"] = "integer";
		session_prop["description"] = "Optional debugger session index to inspect.";
		props["session_index"] = session_prop;
		Dictionary nodes_prop;
		nodes_prop["type"] = "integer";
		nodes_prop["description"] = "Maximum number of remote scene nodes to return (default: 100, max: 500).";
		props["max_nodes"] = nodes_prop;
		params["properties"] = props;
		reg->register_tool("get_debugger_remote_scene", "Get a structured snapshot of the debugger's cached remote scene tree", params, callable_mp_static(&DebugTools::tool_get_debugger_remote_scene), false, AIToolRegistry::EXECUTION_READ_ONLY, true,
				"Use when diagnosing runtime scene issues and you need the debugger's remote tree plus current remote selection.",
				"a capped remote-scene snapshot with nodes and any available selected object ids");
	}
}

Variant DebugTools::tool_get_console_output(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	int lines = CLAMP((int)p_args.get("lines", 50), 1, 200);
	EditorLog *log = EditorNode::get_log();
	if (!log) {
		return "Error: Editor log is not available.";
	}

	PackedStringArray recent = log->get_recent_messages(lines);
	if (recent.is_empty()) {
		return "No editor log output is currently available.";
	}

	String output = "Recent editor log output:\n";
	for (int i = 0; i < recent.size(); i++) {
		output += recent[i] + "\n";
	}

	return output.strip_edges();
#else
	return "Error: only available in editor builds.";
#endif
}

Variant DebugTools::tool_pause_game(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	EditorDebuggerNode *debugger_node = EditorDebuggerNode::get_singleton();
	if (!debugger_node) {
		return "Error: No debug session available.";
	}
	ScriptEditorDebugger *debugger = debugger_node->get_default_debugger();
	if (!debugger || !debugger->is_session_active()) {
		return "Error: No active debug session. Is the game running?";
	}
	debugger->debug_break();
	return "Game pause command sent.";
#else
	return "Error: only available in editor builds.";
#endif
}

Variant DebugTools::tool_resume_game(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	EditorDebuggerNode *debugger_node = EditorDebuggerNode::get_singleton();
	if (!debugger_node) {
		return "Error: No debug session available.";
	}
	ScriptEditorDebugger *debugger = debugger_node->get_default_debugger();
	if (!debugger || !debugger->is_session_active()) {
		return "Error: No active debug session. Is the game running?";
	}
	debugger->debug_continue();
	return "Game resume command sent.";
#else
	return "Error: only available in editor builds.";
#endif
}

Variant DebugTools::tool_get_performance_metrics(const Dictionary &p_args) {
	Performance *perf = Performance::get_singleton();
	if (!perf) {
		return "Error: Performance singleton not available.";
	}

	Dictionary metrics;
	metrics["fps"] = perf->get_monitor(Performance::TIME_FPS);
	metrics["process_time_ms"] = perf->get_monitor(Performance::TIME_PROCESS) * 1000.0;
	metrics["physics_time_ms"] = perf->get_monitor(Performance::TIME_PHYSICS_PROCESS) * 1000.0;
	metrics["memory_static_mb"] = perf->get_monitor(Performance::MEMORY_STATIC) / (1024 * 1024);
	metrics["object_count"] = perf->get_monitor(Performance::OBJECT_COUNT);
	metrics["node_count"] = perf->get_monitor(Performance::OBJECT_NODE_COUNT);
	metrics["resource_count"] = perf->get_monitor(Performance::OBJECT_RESOURCE_COUNT);
	metrics["draw_calls"] = perf->get_monitor(Performance::RENDER_TOTAL_DRAW_CALLS_IN_FRAME);

	// Format as readable string.
	String result = "Performance Metrics:\n";
	result += "  FPS: " + String::num(metrics["fps"]) + "\n";
	result += "  Process: " + String::num(metrics["process_time_ms"], 2) + "ms\n";
	result += "  Physics: " + String::num(metrics["physics_time_ms"], 2) + "ms\n";
	result += "  Memory: " + String::num(metrics["memory_static_mb"], 1) + " MB\n";
	result += "  Objects: " + itos((int)(double)metrics["object_count"]) + "\n";
	result += "  Nodes: " + itos((int)(double)metrics["node_count"]) + "\n";
	result += "  Draw Calls: " + itos((int)(double)metrics["draw_calls"]) + "\n";
	return result;
}

Variant DebugTools::tool_show_debugger_panel(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	EditorDebuggerNode *debugger_node = nullptr;
	ScriptEditorDebugger *debugger = nullptr;
	int requested_session = -1;
	int resolved_session = -1;
	Dictionary error_result;
	if (!_resolve_debugger_session(p_args, debugger_node, debugger, requested_session, resolved_session, error_result)) {
		if (debugger_node) {
			EditorDockManager::get_singleton()->focus_dock(debugger_node);
		}
		return error_result;
	}

	debugger_node->switch_to_debugger_session(resolved_session);
	EditorDockManager::get_singleton()->focus_dock(debugger_node);

	Dictionary result = _make_debugger_result_base(debugger_node, requested_session, resolved_session);
	result["ok"] = true;
	result["message"] = vformat("Focused Debugger panel on session %d.", resolved_session);
	return result;
#else
	return "Error: only available in editor builds.";
#endif
}

Variant DebugTools::tool_get_debugger_state(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	EditorDebuggerNode *debugger_node = nullptr;
	ScriptEditorDebugger *debugger = nullptr;
	int requested_session = -1;
	int resolved_session = -1;
	Dictionary error_result;
	if (!_resolve_debugger_session(p_args, debugger_node, debugger, requested_session, resolved_session, error_result)) {
		return error_result;
	}

	Dictionary result = _make_debugger_result_base(debugger_node, requested_session, resolved_session);
	result["ok"] = true;
	result["state"] = debugger->get_session_snapshot();
	return result;
#else
	return "Error: only available in editor builds.";
#endif
}

Variant DebugTools::tool_get_debugger_stack(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	EditorDebuggerNode *debugger_node = nullptr;
	ScriptEditorDebugger *debugger = nullptr;
	int requested_session = -1;
	int resolved_session = -1;
	Dictionary error_result;
	if (!_resolve_debugger_session(p_args, debugger_node, debugger, requested_session, resolved_session, error_result)) {
		return error_result;
	}

	Dictionary result = _make_debugger_result_base(debugger_node, requested_session, resolved_session);
	result["ok"] = true;
	result["stack"] = debugger->get_stack_snapshot((int)p_args.get("max_frames", 20));
	return result;
#else
	return "Error: only available in editor builds.";
#endif
}

Variant DebugTools::tool_get_debugger_errors(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	EditorDebuggerNode *debugger_node = nullptr;
	ScriptEditorDebugger *debugger = nullptr;
	int requested_session = -1;
	int resolved_session = -1;
	Dictionary error_result;
	if (!_resolve_debugger_session(p_args, debugger_node, debugger, requested_session, resolved_session, error_result)) {
		return error_result;
	}

	Dictionary result = _make_debugger_result_base(debugger_node, requested_session, resolved_session);
	result["ok"] = true;
	result["errors"] = debugger->get_error_snapshot((int)p_args.get("max_items", 20));
	return result;
#else
	return "Error: only available in editor builds.";
#endif
}

Variant DebugTools::tool_get_debugger_remote_scene(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	EditorDebuggerNode *debugger_node = nullptr;
	ScriptEditorDebugger *debugger = nullptr;
	int requested_session = -1;
	int resolved_session = -1;
	Dictionary error_result;
	if (!_resolve_debugger_session(p_args, debugger_node, debugger, requested_session, resolved_session, error_result)) {
		return error_result;
	}

	TypedArray<uint64_t> selected_ids;
	if (resolved_session == debugger_node->get_current_debugger_index()) {
		selected_ids = debugger_node->get_remote_tree_selection();
	}

	Dictionary result = _make_debugger_result_base(debugger_node, requested_session, resolved_session);
	result["ok"] = true;
	result["selection_reflects_current_session"] = resolved_session == debugger_node->get_current_debugger_index();
	result["remote_scene"] = debugger->get_remote_scene_snapshot((int)p_args.get("max_nodes", 100), selected_ids);
	return result;
#else
	return "Error: only available in editor builds.";
#endif
}
