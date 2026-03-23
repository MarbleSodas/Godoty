/**************************************************************************/
/*  ai_agent_mode.cpp                                                     */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "ai_agent_mode.h"

namespace {

PackedStringArray _make_array(std::initializer_list<const char *> p_items) {
	PackedStringArray items;
	for (const char *item : p_items) {
		items.push_back(String(item));
	}
	return items;
}

PackedStringArray _resolve_allowed_tools(const PackedStringArray &p_available_tools, const PackedStringArray &p_preferred_tools) {
	if (p_preferred_tools.is_empty()) {
		return p_available_tools;
	}

	PackedStringArray allowed;
	for (int i = 0; i < p_preferred_tools.size(); i++) {
		if (p_available_tools.has(p_preferred_tools[i])) {
			allowed.push_back(p_preferred_tools[i]);
		}
	}
	return allowed;
}

} // namespace

String ai_agent_mode_get_name(AIAgentModeId p_mode) {
	switch (p_mode) {
		case AI_AGENT_MODE_ASK:
			return "Ask";
		case AI_AGENT_MODE_EDIT:
			return "Edit";
		case AI_AGENT_MODE_PLAN:
			return "Plan";
		case AI_AGENT_MODE_DEBUG:
			return "Debug";
		case AI_AGENT_MODE_ORCHESTRATE:
			return "Orchestrate";
	}

	return "Ask";
}

AIProviderDescriptor ai_agent_get_provider_descriptor(AIAgentConfig::ProviderType p_provider) {
	AIProviderDescriptor descriptor;
	descriptor.provider_type = p_provider;

	switch (p_provider) {
		case AIAgentConfig::PROVIDER_OPENAI:
			descriptor.name = "OpenAI";
			descriptor.description = "Fast default for editor help and general coding tasks, aligned with current Copilot guidance. Uses your own OpenAI API key, not GitHub Copilot auth.";
			descriptor.icon_name = "AIAgentProviderOpenAI";
			descriptor.default_model = "gpt-5-mini";
			descriptor.default_base_url = "https://api.openai.com/v1";
			descriptor.api_key_placeholder = "sk-...";
			descriptor.recommended_models = _make_array({ "gpt-5-mini", "gpt-5", "gpt-4.1-mini" });
			descriptor.requires_api_key = true;
			descriptor.supports_temperature = false;
			descriptor.supports_max_output_tokens = true;
			descriptor.max_output_tokens_limit = 16384;
			descriptor.default_context_window = 128000;
			break;
		case AIAgentConfig::PROVIDER_ANTHROPIC:
			descriptor.name = "Anthropic";
			descriptor.description = "Strong for longer explanations, planning, and careful edits, matching current Copilot and OpenCode guidance for deeper reasoning.";
			descriptor.icon_name = "AIAgentProviderAnthropic";
			descriptor.default_model = "claude-sonnet-4-5-20250929";
			descriptor.default_base_url = "https://api.anthropic.com/v1";
			descriptor.api_key_placeholder = "sk-ant-...";
			descriptor.recommended_models = _make_array({ "claude-sonnet-4-5-20250929", "claude-3-7-sonnet-latest", "claude-3-5-haiku-latest" });
			descriptor.requires_api_key = true;
			descriptor.supports_temperature = false;
			descriptor.supports_max_output_tokens = true;
			descriptor.max_output_tokens_limit = 8192;
			descriptor.default_context_window = 200000;
			break;
		case AIAgentConfig::PROVIDER_MINIMAX:
			descriptor.name = "MiniMax";
			descriptor.description = "Default provider here. MiniMax M2.7 is the current flagship; M2.1 remains a solid coding-agent option highlighted by OpenCode.";
			descriptor.icon_name = "AIAgentProviderMiniMax";
			descriptor.default_model = "MiniMax-M2.7";
			descriptor.default_base_url = "https://api.minimax.io/v1";
			descriptor.api_key_placeholder = "Enter your MiniMax API key";
			descriptor.recommended_models = _make_array({ "MiniMax-M2.7", "MiniMax-M2.7-highspeed", "MiniMax-M2.5", "MiniMax-M2.1" });
			descriptor.requires_api_key = true;
			descriptor.supports_temperature = true;
			descriptor.supports_max_output_tokens = false;
			descriptor.max_output_tokens_limit = 4096;
			descriptor.default_context_window = 204800;
			break;
		case AIAgentConfig::PROVIDER_LOCAL:
			descriptor.name = "Local (Ollama)";
			descriptor.description = "Connect to a local Ollama or compatible server.";
			descriptor.icon_name = "AIAgentProviderLocal";
			descriptor.default_model = "llama3.1";
			descriptor.default_base_url = "http://localhost:11434";
			descriptor.api_key_placeholder = "Optional for authenticated local gateways";
			descriptor.recommended_models = _make_array({ "llama3.1", "qwen2.5-coder", "deepseek-coder-v2" });
			descriptor.requires_api_key = false;
			descriptor.supports_temperature = true;
			descriptor.supports_max_output_tokens = true;
			descriptor.max_output_tokens_limit = 8192;
			descriptor.default_context_window = 65536;
			break;
		case AIAgentConfig::PROVIDER_CUSTOM:
			descriptor.name = "Custom";
			descriptor.description = "Use an OpenAI-compatible provider or gateway such as OpenCode Zen. GitHub Copilot device-login providers are not supported in this panel.";
			descriptor.icon_name = "AIAgentProviderCustom";
			descriptor.default_model = "gpt-4.1-mini";
			descriptor.default_base_url = "";
			descriptor.api_key_placeholder = "Enter your provider API key";
			descriptor.recommended_models = _make_array({ "gpt-4.1-mini", "gpt-5-mini" });
			descriptor.requires_api_key = true;
			descriptor.supports_temperature = false;
			descriptor.supports_max_output_tokens = true;
			descriptor.max_output_tokens_limit = 8192;
			descriptor.default_context_window = 128000;
			break;
	}

	return descriptor;
}

AIAgentModeProfile ai_agent_get_mode_profile(AIAgentModeId p_mode) {
	AIAgentModeProfile profile;
	profile.id = p_mode;

	switch (p_mode) {
		case AI_AGENT_MODE_ASK:
			profile.title = "Ask";
			profile.description = "Read-first help for understanding the current project and editor state.";
			profile.icon_name = "AIAgentModeAsk";
			profile.harness_prompt =
					"You are Godoty's Ask mode. Act like a senior editor-side pair programmer focused on understanding before changing.\n"
					"- Prefer read-only tools and workspace inspection.\n"
					"- Use inspect_node for live scene state, get_class_reference for node and engine APIs, and get_script_reference for script surfaces before you guess.\n"
					"- When runtime issues are suspected, inspect debugger state with get_debugger_state, get_debugger_stack, get_debugger_errors, or get_debugger_remote_scene before drawing conclusions.\n"
					"- Use grep_files to locate relevant files or symbols, then read_file or get_script_content to inspect the matches.\n"
					"- Never claim you searched the project unless you actually called a search tool.\n"
					"- Explain findings clearly and only suggest edits unless the user explicitly asks you to make them.\n"
					"- When tool use is needed, inspect files, scenes, runtime data, and editor state before proposing changes.";
			profile.allowed_tools = _make_array({
					"select_nodes",
					"get_project_info",
					"get_godot_version",
					"inspect_node",
					"get_class_reference",
					"get_script_reference",
					"read_file",
					"list_directory",
					"grep_files",
					"search_files",
					"get_script_content",
					"open_script",
					"get_console_output",
					"get_performance_metrics",
					"get_debugger_state",
					"get_debugger_stack",
					"get_debugger_errors",
					"get_debugger_remote_scene",
					"show_debugger_panel",
					"get_node_property",
			});
			profile.temperature = 0.0f;
			profile.preferred_max_output_tokens = 4096;
			break;
		case AI_AGENT_MODE_EDIT:
			profile.title = "Edit";
			profile.description = "Make focused project and scene changes with the built-in harness.";
			profile.icon_name = "AIAgentModeEdit";
			profile.harness_prompt =
					"You are Godoty's Edit mode. Behave like a careful implementation agent inside the editor.\n"
					"- Inspect relevant project state before making changes.\n"
					"- When a node, property, signal, or script API is unfamiliar, consult inspect_node, get_class_reference, or get_script_reference before mutating anything.\n"
					"- When runtime issues are involved, inspect debugger state before changing code so the fix is grounded in actual runtime behavior.\n"
					"- Keep edits minimal, preserve user intent, and continue until the requested work is complete.\n"
					"- Use approval-gated tools when needed and summarize concrete results after changes.";
			profile.allowed_tools = PackedStringArray();
			profile.temperature = 0.1f;
			profile.preferred_max_output_tokens = 6144;
			break;
		case AI_AGENT_MODE_PLAN:
			profile.title = "Plan";
			profile.description = "Analyze broadly and produce a strong implementation plan without changing files.";
			profile.icon_name = "AIAgentModePlan";
			profile.harness_prompt =
					"You are Godoty's Plan mode. Build implementation plans grounded in the current project.\n"
					"- Inspect the relevant scripts, scenes, files, and editor state before planning.\n"
					"- Use inspect_node for live scene state, get_class_reference for node and engine APIs, and get_script_reference for script surfaces before you guess.\n"
					"- When planning around runtime failures, inspect debugger state with the dedicated debugger tools instead of inferring from logs alone.\n"
					"- Use grep_files to locate relevant files or symbols, then read_file or get_script_content to inspect the matches.\n"
					"- Never claim you searched the project unless you actually called a search tool.\n"
					"- Do not propose hidden magic; tie recommendations to the current codebase.\n"
					"- Prefer read-only tools and produce actionable, decision-complete guidance.";
			profile.allowed_tools = _make_array({
					"select_nodes",
					"get_project_info",
					"get_godot_version",
					"inspect_node",
					"get_class_reference",
					"get_script_reference",
					"read_file",
					"list_directory",
					"grep_files",
					"search_files",
					"get_script_content",
					"open_script",
					"get_console_output",
					"get_performance_metrics",
					"get_debugger_state",
					"get_debugger_stack",
					"get_debugger_errors",
					"get_debugger_remote_scene",
					"show_debugger_panel",
					"get_node_property",
			});
			profile.temperature = 0.0f;
			profile.preferred_max_output_tokens = 8192;
			break;
		case AI_AGENT_MODE_DEBUG:
			profile.title = "Debug";
			profile.description = "Diagnose bugs, trace errors, and suggest targeted fixes without modifying files.";
			profile.icon_name = "AIAgentModeDebug";
			profile.harness_prompt =
					"You are Godoty's Debug mode. Act as a methodical diagnostician inside the editor.\n"
					"- Start by reading debugger state with get_debugger_state, then inspect console output, debugger errors, stack data, and performance metrics.\n"
					"- Use inspect_node for live scene state, get_class_reference for node and engine APIs, and get_script_reference for script surfaces before you guess.\n"
					"- Use grep_files to locate relevant files or symbols, then read_file or get_script_content to inspect the matches.\n"
					"- Never claim you searched the project unless you actually called a search tool.\n"
					"- Inspect the relevant scripts and scene state to trace the root cause.\n"
					"- Explain the bug clearly, identify the root cause, and suggest a targeted fix.\n"
					"- Do not edit files directly; present your diagnosis and recommended changes.";
			profile.allowed_tools = _make_array({
					"get_project_info",
					"get_godot_version",
					"inspect_node",
					"get_class_reference",
					"get_script_reference",
					"get_console_output",
					"get_performance_metrics",
					"get_debugger_state",
					"get_debugger_stack",
					"get_debugger_errors",
					"get_debugger_remote_scene",
					"show_debugger_panel",
					"read_file",
					"get_script_content",
					"grep_files",
					"search_files",
					"get_node_property",
					"list_directory",
					"open_script",
					"select_nodes",
			});
			profile.temperature = 0.0f;
			profile.preferred_max_output_tokens = 6144;
			break;
		case AI_AGENT_MODE_ORCHESTRATE:
			profile.title = "Orchestrate";
			profile.description = "Break complex work into focused subtasks and coordinate their results.";
			profile.icon_name = "AIAgentModeOrchestrate";
			profile.harness_prompt =
					"You are Godoty's Orchestrate mode. Break larger requests into a small number of focused subtasks.\n"
					"- Inspect the current project before delegating work.\n"
					"- Use inspect_node for live scene state, get_class_reference for node and engine APIs, and get_script_reference for script surfaces before you guess.\n"
					"- When runtime bugs are part of the task, inspect debugger state first so child tasks start from the same grounded understanding.\n"
					"- Use grep_files to locate relevant files or symbols, then read_file or get_script_content to inspect the matches.\n"
					"- Never claim you searched the project unless you actually called a search tool.\n"
					"- Use read-only tools to understand the workspace, then call new_task only when decomposition materially helps.\n"
					"- Keep each child task specific, choose Ask/Edit/Plan/Debug deliberately, and summarize child results before continuing.";
			profile.allowed_tools = _make_array({
					"select_nodes",
					"get_project_info",
					"get_godot_version",
					"inspect_node",
					"get_class_reference",
					"get_script_reference",
					"read_file",
					"list_directory",
					"grep_files",
					"search_files",
					"get_script_content",
					"open_script",
					"get_console_output",
					"get_performance_metrics",
					"get_debugger_state",
					"get_debugger_stack",
					"get_debugger_errors",
					"get_debugger_remote_scene",
					"show_debugger_panel",
					"get_node_property",
			});
			profile.temperature = 0.0f;
			profile.preferred_max_output_tokens = 8192;
			break;
	}

	return profile;
}

int ai_agent_estimate_model_context_window(const AIProviderDescriptor &p_provider, const String &p_model_name) {
	String normalized = p_model_name.to_lower().strip_edges();
	if (normalized.is_empty()) {
		return p_provider.default_context_window;
	}

	if (normalized.contains("claude")) {
		return 200000;
	}
	if (normalized.contains("gpt-5") || normalized.contains("gpt-4.1")) {
		return 128000;
	}
	if (normalized.contains("minimax")) {
		return 128000;
	}
	if (normalized.contains("qwen2.5") || normalized.contains("qwen")) {
		return 32768;
	}
	if (normalized.contains("deepseek")) {
		return 65536;
	}
	if (normalized.contains("llama3.1") || normalized.contains("llama")) {
		return 128000;
	}

	return p_provider.default_context_window;
}

ResolvedAgentRunConfig ai_agent_resolve_run_config(const Ref<AIAgentConfig> &p_config, AIAgentModeId p_mode, const PackedStringArray &p_available_tools) {
	ResolvedAgentRunConfig resolved;

	AIAgentConfig::ProviderType provider_type = AIAgentConfig::PROVIDER_OPENAI;
	if (p_config.is_valid()) {
		provider_type = p_config->get_provider_type();
	}

	resolved.provider = ai_agent_get_provider_descriptor(provider_type);
	resolved.mode = ai_agent_get_mode_profile(p_mode);
	resolved.model_name = p_config.is_valid() ? p_config->get_model_name() : resolved.provider.default_model;
	if (resolved.model_name.is_empty()) {
		resolved.model_name = resolved.provider.default_model;
	}
	// Per-mode model override takes priority over the global model.
	if (p_config.is_valid() && p_config->has_mode_model_override((int)p_mode)) {
		resolved.model_name = p_config->get_mode_model_override((int)p_mode);
	}
	resolved.base_url = p_config.is_valid() ? p_config->get_effective_base_url() : resolved.provider.default_base_url;
	resolved.allowed_tools = _resolve_allowed_tools(p_available_tools, resolved.mode.allowed_tools);
	resolved.use_temperature = resolved.provider.supports_temperature;
	resolved.temperature = resolved.mode.temperature;
	resolved.use_max_output_tokens = resolved.provider.supports_max_output_tokens;
	resolved.max_output_tokens = MIN(resolved.mode.preferred_max_output_tokens, resolved.provider.max_output_tokens_limit);
	resolved.stream_responses = true;
	resolved.estimated_context_window = ai_agent_estimate_model_context_window(resolved.provider, resolved.model_name);

	return resolved;
}
