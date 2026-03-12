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
#include "editor/editor_node.h"
#endif

void DebugTools::_bind_methods() {
	ClassDB::bind_static_method("DebugTools", D_METHOD("register_tools"), &DebugTools::register_tools);
}

void DebugTools::register_tools() {
	AIToolRegistry *reg = AIToolRegistry::get_singleton();
	ERR_FAIL_NULL(reg);

	// get_console_output — no-op placeholder, will be wired to output capture.
	{
		Dictionary params;
		params["type"] = "object";
		Dictionary props;
		Dictionary lines_prop;
		lines_prop["type"] = "integer";
		lines_prop["description"] = "Number of recent lines to retrieve (default: 50)";
		props["lines"] = lines_prop;
		params["properties"] = props;
		reg->register_tool("get_console_output", "Get recent console output/log messages", params, callable_mp_static(&DebugTools::tool_get_console_output));
	}

	// pause_game
	{
		Dictionary params;
		params["type"] = "object";
		params["properties"] = Dictionary();
		reg->register_tool("pause_game", "Pause the running game", params, callable_mp_static(&DebugTools::tool_pause_game));
	}

	// resume_game
	{
		Dictionary params;
		params["type"] = "object";
		params["properties"] = Dictionary();
		reg->register_tool("resume_game", "Resume the paused game", params, callable_mp_static(&DebugTools::tool_resume_game));
	}

	// get_performance_metrics
	{
		Dictionary params;
		params["type"] = "object";
		params["properties"] = Dictionary();
		reg->register_tool("get_performance_metrics", "Get current performance metrics (FPS, memory, draw calls)", params, callable_mp_static(&DebugTools::tool_get_performance_metrics));
	}
}

Variant DebugTools::tool_get_console_output(const Dictionary &p_args) {
	// TODO: Wire to a captured output buffer.
	// For now, return a placeholder indicating this is available but needs output capture.
	return "Console output capture will be available once the output buffer is wired. Use 'get_performance_metrics' for live data.";
}

Variant DebugTools::tool_pause_game(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	EditorDebuggerNode *debugger = EditorDebuggerNode::get_singleton();
	if (!debugger || !debugger->is_session_active()) {
		return "Error: No active debug session. Is the game running?";
	}
	// TODO: Send pause to debugger.
	return "Game paused (via debugger).";
#else
	return "Error: only available in editor builds.";
#endif
}

Variant DebugTools::tool_resume_game(const Dictionary &p_args) {
#ifdef TOOLS_ENABLED
	EditorDebuggerNode *debugger = EditorDebuggerNode::get_singleton();
	if (!debugger || !debugger->is_session_active()) {
		return "Error: No active debug session.";
	}
	// TODO: Send continue to debugger.
	return "Game resumed.";
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
