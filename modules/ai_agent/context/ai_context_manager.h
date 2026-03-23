/**************************************************************************/
/*  ai_context_manager.h                                                  */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "core/object/class_db.h"
#include "core/object/object.h"
#include "core/variant/dictionary.h"

class AIContextManager : public Object {
	GDCLASS(AIContextManager, Object);

	static AIContextManager *singleton;

public:
	enum ContextFlags {
		CONTEXT_SCENE = 1 << 0,
		CONTEXT_SCRIPTS = 1 << 1,
		CONTEXT_ASSETS = 1 << 2,
		CONTEXT_EDITOR_STATE = 1 << 3,
		CONTEXT_RUNTIME = 1 << 4,
		CONTEXT_PROJECT = 1 << 5,
		CONTEXT_REFERENCE = 1 << 6,
		CONTEXT_ALL = CONTEXT_SCENE | CONTEXT_SCRIPTS | CONTEXT_ASSETS | CONTEXT_EDITOR_STATE | CONTEXT_RUNTIME | CONTEXT_PROJECT | CONTEXT_REFERENCE,
	};

protected:
	static void _bind_methods();

private:
	// Cached context data with invalidation timestamps.
	Dictionary cached_context;
	uint64_t cache_timestamp = 0;
	int cache_flags = 0;
	uint64_t cache_ttl_ms = 2000; // 2 second cache TTL.
	int max_token_budget = 8000;

	bool _is_cache_valid() const;
	void _invalidate_cache();

public:
	static AIContextManager *get_singleton();

	// Collect context based on flags bitmask.
	Dictionary collect_context(int p_flags = CONTEXT_ALL);

	// Collect with a token budget estimate.
	Dictionary collect_context_budgeted(int p_flags, int p_max_tokens);

	// Individual context accessors.
	Dictionary get_scene_context();
	Dictionary get_script_context();
	Dictionary get_asset_context();
	Dictionary get_editor_context();
	Dictionary get_runtime_context();
	Dictionary get_project_context();
	Dictionary get_reference_context();

	// Cache management.
	void invalidate_cache();
	void set_cache_ttl_ms(uint64_t p_ttl);
	uint64_t get_cache_ttl_ms() const;

	// Token budget.
	void set_max_token_budget(int p_budget);
	int get_max_token_budget() const;

	// Utility — estimate token count of a Dictionary.
	static int estimate_tokens(const Dictionary &p_dict);

	AIContextManager();
	~AIContextManager();
};

VARIANT_ENUM_CAST(AIContextManager::ContextFlags);
