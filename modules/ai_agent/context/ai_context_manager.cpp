/**************************************************************************/
/*  ai_context_manager.cpp                                                */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "ai_context_manager.h"
#include "asset_context.h"
#include "editor_context.h"
#include "project_context.h"
#include "runtime_context.h"
#include "scene_context.h"
#include "script_context.h"

#include "core/io/json.h"
#include "core/os/os.h"

AIContextManager *AIContextManager::singleton = nullptr;

void AIContextManager::_bind_methods() {
	ClassDB::bind_method(D_METHOD("collect_context", "flags"), &AIContextManager::collect_context, DEFVAL(CONTEXT_ALL));
	ClassDB::bind_method(D_METHOD("collect_context_budgeted", "flags", "max_tokens"), &AIContextManager::collect_context_budgeted);
	ClassDB::bind_method(D_METHOD("get_scene_context"), &AIContextManager::get_scene_context);
	ClassDB::bind_method(D_METHOD("get_script_context"), &AIContextManager::get_script_context);
	ClassDB::bind_method(D_METHOD("get_asset_context"), &AIContextManager::get_asset_context);
	ClassDB::bind_method(D_METHOD("get_editor_context"), &AIContextManager::get_editor_context);
	ClassDB::bind_method(D_METHOD("get_runtime_context"), &AIContextManager::get_runtime_context);
	ClassDB::bind_method(D_METHOD("get_project_context"), &AIContextManager::get_project_context);
	ClassDB::bind_method(D_METHOD("invalidate_cache"), &AIContextManager::invalidate_cache);
	ClassDB::bind_method(D_METHOD("set_cache_ttl_ms", "ttl"), &AIContextManager::set_cache_ttl_ms);
	ClassDB::bind_method(D_METHOD("get_cache_ttl_ms"), &AIContextManager::get_cache_ttl_ms);
	ClassDB::bind_method(D_METHOD("set_max_token_budget", "budget"), &AIContextManager::set_max_token_budget);
	ClassDB::bind_method(D_METHOD("get_max_token_budget"), &AIContextManager::get_max_token_budget);
	ClassDB::bind_static_method("AIContextManager", D_METHOD("estimate_tokens", "dict"), &AIContextManager::estimate_tokens);

	ADD_PROPERTY(PropertyInfo(Variant::INT, "cache_ttl_ms"), "set_cache_ttl_ms", "get_cache_ttl_ms");
	ADD_PROPERTY(PropertyInfo(Variant::INT, "max_token_budget"), "set_max_token_budget", "get_max_token_budget");

	ADD_SIGNAL(MethodInfo("context_invalidated"));

	BIND_ENUM_CONSTANT(CONTEXT_SCENE);
	BIND_ENUM_CONSTANT(CONTEXT_SCRIPTS);
	BIND_ENUM_CONSTANT(CONTEXT_ASSETS);
	BIND_ENUM_CONSTANT(CONTEXT_EDITOR_STATE);
	BIND_ENUM_CONSTANT(CONTEXT_RUNTIME);
	BIND_ENUM_CONSTANT(CONTEXT_PROJECT);
	BIND_ENUM_CONSTANT(CONTEXT_ALL);
}

AIContextManager::AIContextManager() {
	singleton = this;
}

AIContextManager::~AIContextManager() {
	singleton = nullptr;
}

AIContextManager *AIContextManager::get_singleton() {
	return singleton;
}

bool AIContextManager::_is_cache_valid() const {
	if (cached_context.is_empty()) {
		return false;
	}
	uint64_t now = OS::get_singleton()->get_ticks_msec();
	return (now - cache_timestamp) < cache_ttl_ms;
}

void AIContextManager::_invalidate_cache() {
	cached_context.clear();
	cache_timestamp = 0;
	emit_signal("context_invalidated");
}

Dictionary AIContextManager::collect_context(int p_flags) {
	Dictionary context;

	if (p_flags & CONTEXT_SCENE) {
		context["scene"] = get_scene_context();
	}
	if (p_flags & CONTEXT_SCRIPTS) {
		context["scripts"] = get_script_context();
	}
	if (p_flags & CONTEXT_ASSETS) {
		context["assets"] = get_asset_context();
	}
	if (p_flags & CONTEXT_EDITOR_STATE) {
		context["editor"] = get_editor_context();
	}
	if (p_flags & CONTEXT_RUNTIME) {
		context["runtime"] = get_runtime_context();
	}
	if (p_flags & CONTEXT_PROJECT) {
		context["project"] = get_project_context();
	}

	cached_context = context;
	cache_timestamp = OS::get_singleton()->get_ticks_msec();
	return context;
}

Dictionary AIContextManager::collect_context_budgeted(int p_flags, int p_max_tokens) {
	// Collect all requested context first, then trim if over budget.
	Dictionary full_context = collect_context(p_flags);
	int estimated = estimate_tokens(full_context);

	if (estimated <= p_max_tokens) {
		return full_context;
	}

	// Priority order for trimming: runtime > assets > editor > scripts > scene > project.
	// Remove lowest-priority sections until within budget.
	Dictionary trimmed = full_context.duplicate(true);
	PackedStringArray trim_order;
	trim_order.push_back("runtime");
	trim_order.push_back("assets");
	trim_order.push_back("editor");

	for (int i = 0; i < trim_order.size() && estimate_tokens(trimmed) > p_max_tokens; i++) {
		if (trimmed.has(trim_order[i])) {
			trimmed.erase(trim_order[i]);
		}
	}

	return trimmed;
}

Dictionary AIContextManager::get_scene_context() {
	return SceneContext::collect();
}

Dictionary AIContextManager::get_script_context() {
	return ScriptContext::collect();
}

Dictionary AIContextManager::get_asset_context() {
	return AssetContext::collect();
}

Dictionary AIContextManager::get_editor_context() {
	return EditorContext::collect();
}

Dictionary AIContextManager::get_runtime_context() {
	return RuntimeContext::collect();
}

Dictionary AIContextManager::get_project_context() {
	return ProjectContext::collect();
}

void AIContextManager::invalidate_cache() {
	_invalidate_cache();
}

void AIContextManager::set_cache_ttl_ms(uint64_t p_ttl) {
	cache_ttl_ms = p_ttl;
}

uint64_t AIContextManager::get_cache_ttl_ms() const {
	return cache_ttl_ms;
}

void AIContextManager::set_max_token_budget(int p_budget) {
	max_token_budget = MAX(100, p_budget);
}

int AIContextManager::get_max_token_budget() const {
	return max_token_budget;
}

int AIContextManager::estimate_tokens(const Dictionary &p_dict) {
	// Rough estimate: ~4 chars per token for JSON-serialized content.
	String json = JSON::stringify(p_dict);
	return json.length() / 4;
}
