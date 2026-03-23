/**************************************************************************/
/*  runtime_context.cpp                                                   */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "runtime_context.h"

#include "core/config/engine.h"
#include "core/input/shortcut.h"
#include "core/os/os.h"
#include "main/performance.h"

#ifdef TOOLS_ENABLED
#include "editor/debugger/editor_debugger_node.h"
#include "editor/debugger/script_editor_debugger.h"
#include "editor/editor_interface.h"
#include "editor/editor_node.h"
#endif

Dictionary RuntimeContext::collect() {
	Dictionary context;

	// Performance metrics (always available).
	Dictionary perf;
	Performance *performance = Performance::get_singleton();
	if (performance) {
		perf["fps"] = performance->get_monitor(Performance::TIME_FPS);
		perf["process_time"] = performance->get_monitor(Performance::TIME_PROCESS);
		perf["physics_time"] = performance->get_monitor(Performance::TIME_PHYSICS_PROCESS);
		perf["memory_static"] = performance->get_monitor(Performance::MEMORY_STATIC);
		perf["memory_static_max"] = performance->get_monitor(Performance::MEMORY_STATIC_MAX);
		perf["object_count"] = performance->get_monitor(Performance::OBJECT_COUNT);
		perf["object_resource_count"] = performance->get_monitor(Performance::OBJECT_RESOURCE_COUNT);
		perf["object_node_count"] = performance->get_monitor(Performance::OBJECT_NODE_COUNT);
		perf["render_draw_calls"] = performance->get_monitor(Performance::RENDER_TOTAL_DRAW_CALLS_IN_FRAME);
	}
	context["performance"] = perf;

#ifdef TOOLS_ENABLED
	// Debugger state.
	EditorDebuggerNode *debugger_node = EditorDebuggerNode::get_singleton();
	if (debugger_node) {
		ScriptEditorDebugger *debugger = debugger_node->get_current_debugger();
		if (debugger) {
			Dictionary debug_state;
			debug_state["selected_session_index"] = debugger_node->get_current_debugger_index();
			debug_state["session_count"] = debugger_node->get_debugger_count();
			debug_state["is_session_active"] = debugger->is_session_active();
			debug_state["is_breaked"] = debugger->is_breaked();
			debug_state["is_debuggable"] = debugger->is_debuggable();
			debug_state["error_count"] = debugger->get_error_count();
			debug_state["warning_count"] = debugger->get_warning_count();
			debug_state["remote_pid"] = debugger->get_remote_pid();
			if (debugger->is_breaked()) {
				Dictionary stack_location;
				stack_location["frame"] = debugger->get_stack_script_frame();
				stack_location["file"] = debugger->get_stack_script_file();
				stack_location["line"] = debugger->get_stack_script_line();
				debug_state["current_stack_location"] = stack_location;
			}
			context["debugger"] = debug_state;
		}
	}

	// Check if game is running.
	EditorInterface *ei = EditorInterface::get_singleton();
	if (ei) {
		context["is_playing"] = ei->is_playing_scene();
	}
#endif

	// Engine info.
	Dictionary engine_info;
	engine_info["physics_ticks_per_second"] = Engine::get_singleton()->get_physics_ticks_per_second();
	engine_info["max_fps"] = Engine::get_singleton()->get_max_fps();
	context["engine"] = engine_info;

	return context;
}
