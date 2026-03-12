/**************************************************************************/
/*  register_types.cpp                                                    */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/*                     https://github.com/MarbleSodas/Godoty              */
/**************************************************************************/
/* Copyright (c) 2014-present Godot Engine contributors (see AUTHORS.md). */
/* Copyright (c) 2024-present Godoty contributors.                        */
/*                                                                        */
/* Permission is hereby granted, free of charge, to any person obtaining  */
/* a copy of this software and associated documentation files (the        */
/* "Software"), to deal in the Software without restriction, including    */
/* without limitation the rights to use, copy, modify, merge, publish,    */
/* distribute, sublicense, and/or sell copies of the Software, and to     */
/* permit persons to whom the Software is furnished to do so, subject to  */
/* the following conditions:                                              */
/*                                                                        */
/* The above copyright notice and this permission notice shall be         */
/* included in all copies or substantial portions of the Software.        */
/*                                                                        */
/* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,        */
/* EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF     */
/* MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. */
/* IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY   */
/* CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,   */
/* TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE      */
/* SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.                 */
/**************************************************************************/

#include "register_types.h"

#include "ai_agent_config.h"
#include "ai_agent_session.h"
#include "ai_message.h"
#include "ai_tool_registry.h"
#include "providers/ai_provider.h"
#include "providers/anthropic_provider.h"
#include "providers/local_provider.h"
#include "providers/minimax_provider.h"
#include "providers/openai_provider.h"

#include "core/config/engine.h"

static AIToolRegistry *ai_tool_registry_singleton = nullptr;

void initialize_ai_agent_module(ModuleInitializationLevel p_level) {
	if (p_level == MODULE_INITIALIZATION_LEVEL_CORE) {
		// Register core types first.
		GDREGISTER_CLASS(AIMessage);
	}

	if (p_level == MODULE_INITIALIZATION_LEVEL_SCENE) {
		// Register resource and provider types.
		GDREGISTER_CLASS(AIAgentConfig);
		GDREGISTER_ABSTRACT_CLASS(AIProvider);
		GDREGISTER_CLASS(OpenAIProvider);
		GDREGISTER_CLASS(AnthropicProvider);
		GDREGISTER_CLASS(MiniMaxProvider);
		GDREGISTER_CLASS(LocalLLMProvider);

		// Register the tool registry singleton.
		ai_tool_registry_singleton = memnew(AIToolRegistry);
		Engine::get_singleton()->add_singleton(
				Engine::Singleton("AIToolRegistry", AIToolRegistry::get_singleton()));
		GDREGISTER_CLASS(AIToolRegistry);

		// Register session management.
		GDREGISTER_CLASS(AIAgentSession);
	}
}

void uninitialize_ai_agent_module(ModuleInitializationLevel p_level) {
	if (p_level == MODULE_INITIALIZATION_LEVEL_SCENE) {
		if (ai_tool_registry_singleton) {
			Engine::get_singleton()->remove_singleton("AIToolRegistry");
			memdelete(ai_tool_registry_singleton);
			ai_tool_registry_singleton = nullptr;
		}
	}
}
