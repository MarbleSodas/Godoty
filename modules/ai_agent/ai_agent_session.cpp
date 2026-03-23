/**************************************************************************/
/*  ai_agent_session.cpp                                                  */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "ai_agent_session.h"
#include "context/ai_context_manager.h"
#include "core/io/dir_access.h"
#include "core/io/file_access.h"
#include "core/io/json.h"
#include "core/os/os.h"
#include "core/os/time.h"
#include "core/os/thread.h"
#include "providers/anthropic_provider.h"
#include "providers/local_provider.h"
#include "providers/minimax_provider.h"
#include "providers/openai_provider.h"

#ifdef TOOLS_ENABLED
#include "editor/editor_interface.h"
#include "editor/editor_node.h"
#include "editor/editor_undo_redo_manager.h"
#include "editor/file_system/editor_file_system.h"
#include "scene/resources/packed_scene.h"
#endif

namespace {

const String THINK_OPEN_TAG = "<think>";
const String THINK_CLOSE_TAG = "</think>";
const int MAX_INLINE_RESULT_CHARS = 8000;
const int MAX_CHILD_TASK_DEPTH = 3;
const int MAX_CHILD_TASKS_PER_TURN = 4;

struct ParallelToolExecutionData {
	AIToolRegistry *registry = nullptr;
	String tool_name;
	Dictionary arguments;
	Variant result;
};

String _sanitize_session_component(const String &p_value) {
	return p_value.replace(":", "_").replace("/", "_").replace("\\", "_");
}

String _build_session_id(uint64_t p_unix_time, ObjectID p_instance_id) {
	return String("session_") + itos((int64_t)p_unix_time) + "_" + itos((int64_t)p_instance_id);
}

String _resolve_tool_name_alias(const String &p_tool_name) {
	const String normalized = p_tool_name.strip_edges().to_lower();
	if (normalized == "grep" || normalized == "rg" || normalized == "ripgrep" || normalized == "search_code" || normalized == "search_project") {
		return "grep_files";
	}
	return p_tool_name;
}

void _execute_parallel_tool_task(void *p_userdata) {
	ParallelToolExecutionData *data = (ParallelToolExecutionData *)p_userdata;
	if (!data || !data->registry) {
		return;
	}
	data->result = data->registry->execute_tool(data->tool_name, data->arguments);
}

} // namespace

void AIAgentSession::_bind_methods() {
	ClassDB::bind_method(D_METHOD("set_config", "config"), &AIAgentSession::set_config);
	ClassDB::bind_method(D_METHOD("get_config"), &AIAgentSession::get_config);
	ClassDB::bind_method(D_METHOD("set_mode", "mode"), &AIAgentSession::set_mode);
	ClassDB::bind_method(D_METHOD("get_mode"), &AIAgentSession::get_mode);
	ClassDB::bind_method(D_METHOD("get_state"), &AIAgentSession::get_state);
	ClassDB::bind_method(D_METHOD("is_busy"), &AIAgentSession::is_busy);
	ClassDB::bind_method(D_METHOD("send_message", "content"), &AIAgentSession::send_message);
	ClassDB::bind_method(D_METHOD("send_message_with_context", "content", "context"), &AIAgentSession::send_message_with_context);
	ClassDB::bind_method(D_METHOD("add_system_message", "content"), &AIAgentSession::add_system_message);
	ClassDB::bind_method(D_METHOD("clear_history"), &AIAgentSession::clear_history);
	ClassDB::bind_method(D_METHOD("get_history"), &AIAgentSession::get_history);
	ClassDB::bind_method(D_METHOD("get_message_count"), &AIAgentSession::get_message_count);
	ClassDB::bind_method(D_METHOD("get_session_id"), &AIAgentSession::get_session_id);
	ClassDB::bind_method(D_METHOD("restore_last_saved_session"), &AIAgentSession::restore_last_saved_session);
	ClassDB::bind_method(D_METHOD("has_ai_edit_snapshots"), &AIAgentSession::has_ai_edit_snapshots);
	ClassDB::bind_method(D_METHOD("undo_last_ai_edit"), &AIAgentSession::undo_last_ai_edit);
	ClassDB::bind_method(D_METHOD("undo_all_ai_edits"), &AIAgentSession::undo_all_ai_edits);
	ClassDB::bind_method(D_METHOD("cancel"), &AIAgentSession::cancel);
	ClassDB::bind_method(D_METHOD("approve_tool_call", "tool_call_id"), &AIAgentSession::approve_tool_call);
	ClassDB::bind_method(D_METHOD("deny_tool_call", "tool_call_id", "reason"), &AIAgentSession::deny_tool_call, DEFVAL(""));
	ClassDB::bind_method(D_METHOD("set_max_tool_iterations", "max"), &AIAgentSession::set_max_tool_iterations);
	ClassDB::bind_method(D_METHOD("get_max_tool_iterations"), &AIAgentSession::get_max_tool_iterations);
	ClassDB::bind_method(D_METHOD("set_orchestration_depth", "depth"), &AIAgentSession::set_orchestration_depth);
	ClassDB::bind_method(D_METHOD("get_orchestration_depth"), &AIAgentSession::get_orchestration_depth);

	ADD_PROPERTY(PropertyInfo(Variant::OBJECT, "config", PROPERTY_HINT_RESOURCE_TYPE, "AIAgentConfig"), "set_config", "get_config");
	ADD_PROPERTY(PropertyInfo(Variant::INT, "mode", PROPERTY_HINT_ENUM, "Ask,Edit,Plan,Debug,Orchestrate"), "set_mode", "get_mode");
	ADD_PROPERTY(PropertyInfo(Variant::INT, "state", PROPERTY_HINT_NONE, "", PROPERTY_USAGE_NO_EDITOR), "", "get_state");
	ADD_PROPERTY(PropertyInfo(Variant::INT, "max_tool_iterations"), "set_max_tool_iterations", "get_max_tool_iterations");
	ADD_PROPERTY(PropertyInfo(Variant::INT, "orchestration_depth", PROPERTY_HINT_NONE, "", PROPERTY_USAGE_NO_EDITOR), "set_orchestration_depth", "get_orchestration_depth");

	// Signals for UI integration.
	ADD_SIGNAL(MethodInfo("message_received",
			PropertyInfo(Variant::OBJECT, "message", PROPERTY_HINT_RESOURCE_TYPE, "AIMessage")));
	ADD_SIGNAL(MethodInfo("stream_chunk",
			PropertyInfo(Variant::OBJECT, "message", PROPERTY_HINT_RESOURCE_TYPE, "AIMessage")));
	ADD_SIGNAL(MethodInfo("thinking_state_changed",
			PropertyInfo(Variant::BOOL, "active")));
	ADD_SIGNAL(MethodInfo("tool_call_requested",
			PropertyInfo(Variant::STRING, "tool_name"),
			PropertyInfo(Variant::DICTIONARY, "arguments"),
			PropertyInfo(Variant::STRING, "tool_call_id")));
	ADD_SIGNAL(MethodInfo("tool_call_completed",
			PropertyInfo(Variant::STRING, "tool_name"),
			PropertyInfo(Variant::NIL, "result"),
			PropertyInfo(Variant::STRING, "tool_call_id")));
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
	(void)_ensure_session_id();
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
	_autosave_session();
}

Ref<AIAgentConfig> AIAgentSession::get_config() const {
	return config;
}

void AIAgentSession::set_mode(AIAgentModeId p_mode) {
	mode = p_mode;
	_autosave_session();
}

AIAgentModeId AIAgentSession::get_mode() const {
	return mode;
}

AIAgentSession::SessionState AIAgentSession::get_state() const {
	return state;
}

bool AIAgentSession::is_busy() const {
	return state != STATE_IDLE && state != STATE_ERROR;
}

AIAgentSession::ParsedAssistantContent AIAgentSession::_parse_assistant_content(const String &p_raw_content) const {
	ParsedAssistantContent parsed;
	bool in_thinking_block = false;
	bool skipping_post_think_leading_whitespace = false;
	bool has_visible_content = false;
	int cursor = 0;

	while (cursor < p_raw_content.length()) {
		String remaining = p_raw_content.substr(cursor);

		if (!in_thinking_block && remaining.begins_with(THINK_OPEN_TAG)) {
			in_thinking_block = true;
			cursor += THINK_OPEN_TAG.length();
			continue;
		}

		if (in_thinking_block && remaining.begins_with(THINK_CLOSE_TAG)) {
			in_thinking_block = false;
			skipping_post_think_leading_whitespace = !has_visible_content;
			cursor += THINK_CLOSE_TAG.length();
			continue;
		}

		// When a stream chunk ends mid-tag, withhold the ambiguous tail until the next chunk arrives.
		if (THINK_OPEN_TAG.begins_with(remaining) || THINK_CLOSE_TAG.begins_with(remaining)) {
			break;
		}

		if (!in_thinking_block && remaining.begins_with(THINK_CLOSE_TAG)) {
			cursor += THINK_CLOSE_TAG.length();
			continue;
		}
		if (in_thinking_block && remaining.begins_with(THINK_OPEN_TAG)) {
			cursor += THINK_OPEN_TAG.length();
			continue;
		}

		const String next_char = p_raw_content.substr(cursor, 1);
		if (in_thinking_block) {
			parsed.thinking_content += next_char;
		} else {
			if (skipping_post_think_leading_whitespace) {
				if (next_char == " " || next_char == "\t" || next_char == "\n" || next_char == "\r") {
					cursor++;
					continue;
				}
				skipping_post_think_leading_whitespace = false;
			}
			parsed.visible_content += next_char;
			has_visible_content = true;
		}
		cursor++;
	}

	parsed.thinking_active = in_thinking_block;
	return parsed;
}

Ref<AIMessage> AIAgentSession::_sanitize_assistant_message(const Ref<AIMessage> &p_message) const {
	if (p_message.is_null() || p_message->get_role() != AIMessage::ROLE_ASSISTANT) {
		return p_message;
	}

	const ParsedAssistantContent parsed = _parse_assistant_content(p_message->get_content());
	const String merged_thinking = p_message->get_thinking_content() + parsed.thinking_content;
	const bool content_changed = parsed.visible_content != p_message->get_content();
	const bool thinking_changed = merged_thinking != p_message->get_thinking_content();
	if (!content_changed && !thinking_changed) {
		return p_message;
	}

	Ref<AIMessage> sanitized = AIMessage::create_assistant(parsed.visible_content, p_message->get_tool_calls(), merged_thinking);
	sanitized->set_metadata(p_message->get_metadata());
	return sanitized;
}

void AIAgentSession::_reset_streaming_accumulator() {
	streaming_raw_content = "";
	streaming_visible_content = "";
	streaming_thinking_content = "";
	_set_streaming_thinking_active(false);
}

void AIAgentSession::_set_streaming_thinking_active(bool p_active) {
	if (streaming_thinking_active == p_active) {
		return;
	}

	streaming_thinking_active = p_active;
	emit_signal("thinking_state_changed", streaming_thinking_active);
}

String AIAgentSession::_ensure_session_id() {
	if (session_id.is_empty()) {
		session_id = _build_session_id(Time::get_singleton()->get_unix_time_from_system(), get_instance_id());
	}
	return session_id;
}

String AIAgentSession::_get_sessions_dir_path() const {
	return "user://ai_sessions";
}

String AIAgentSession::_get_session_save_path() const {
	return _get_sessions_dir_path().path_join(_sanitize_session_component(session_id) + ".json");
}

String AIAgentSession::_get_tool_results_dir_path() const {
	return String("user://ai_tool_results").path_join(_sanitize_session_component(session_id));
}

String AIAgentSession::_get_snapshot_root_dir_path() const {
	return String("user://ai_snapshots").path_join(_sanitize_session_component(session_id));
}

void AIAgentSession::_autosave_session() const {
	if (session_id.is_empty()) {
		return;
	}

	DirAccess::make_dir_recursive_absolute(_get_sessions_dir_path());
	Dictionary data;
	data["session_id"] = session_id;
	data["mode"] = (int)mode;
	data["state"] = (int)state;
	data["persisted_summary"] = persisted_summary;
	data["orchestration_depth"] = orchestration_depth;

	TypedArray<Dictionary> message_dicts;
	for (int i = 0; i < messages.size(); i++) {
		if (messages[i].is_valid()) {
			message_dicts.push_back(messages[i]->to_dict());
		}
	}
	data["messages"] = message_dicts;

	TypedArray<Dictionary> snapshot_dicts;
	for (int i = 0; i < snapshot_batches.size(); i++) {
		snapshot_dicts.push_back(snapshot_batches[i].data);
	}
	data["snapshot_batches"] = snapshot_dicts;

	Ref<FileAccess> file = FileAccess::open(_get_session_save_path(), FileAccess::WRITE);
	if (file.is_null()) {
		return;
	}
	file->store_string(JSON::stringify(data, "  "));
	file->flush();
}

bool AIAgentSession::_restore_session_from_path(const String &p_path) {
	Ref<FileAccess> file = FileAccess::open(p_path, FileAccess::READ);
	if (file.is_null()) {
		return false;
	}

	JSON json;
	if (json.parse(file->get_as_text()) != OK || json.get_data().get_type() != Variant::DICTIONARY) {
		return false;
	}

	Dictionary data = json.get_data();
	session_id = data.get("session_id", "");
	mode = (AIAgentModeId)(int)data.get("mode", (int)AI_AGENT_MODE_ASK);
	state = STATE_IDLE;
	persisted_summary = data.get("persisted_summary", "");
	orchestration_depth = (int)data.get("orchestration_depth", 0);

	messages.clear();
	TypedArray<Dictionary> message_dicts = data.get("messages", TypedArray<Dictionary>());
	for (int i = 0; i < message_dicts.size(); i++) {
		messages.push_back(AIMessage::from_dict(message_dicts[i]));
	}

	snapshot_batches.clear();
	TypedArray<Dictionary> snapshot_dicts = data.get("snapshot_batches", TypedArray<Dictionary>());
	for (int i = 0; i < snapshot_dicts.size(); i++) {
		SessionSnapshotBatch batch;
		batch.data = snapshot_dicts[i];
		snapshot_batches.push_back(batch);
	}

	return true;
}

int AIAgentSession::_estimate_message_tokens(const Ref<AIMessage> &p_message) const {
	if (p_message.is_null()) {
		return 0;
	}
	return MAX(1, JSON::stringify(p_message->to_dict()).length() / 4);
}

int AIAgentSession::_estimate_history_tokens() const {
	int total = 0;
	for (int i = 0; i < messages.size(); i++) {
		total += _estimate_message_tokens(messages[i]);
	}
	return total;
}

String AIAgentSession::_summarize_messages(const Vector<Ref<AIMessage>> &p_messages) const {
	PackedStringArray goal_lines;
	PackedStringArray decision_lines;
	PackedStringArray tool_lines;
	PackedStringArray open_lines;

	for (int i = 0; i < p_messages.size(); i++) {
		const Ref<AIMessage> &msg = p_messages[i];
		if (msg.is_null()) {
			continue;
		}

		String snippet = msg->get_content().replace("\n", " ").strip_edges();
		if (snippet.length() > 160) {
			snippet = snippet.substr(0, 160) + "...";
		}
		if (snippet.is_empty()) {
			snippet = "[no visible content]";
		}

		switch (msg->get_role()) {
			case AIMessage::ROLE_USER:
				goal_lines.push_back("- " + snippet);
				break;
			case AIMessage::ROLE_ASSISTANT:
				decision_lines.push_back("- " + snippet);
				break;
			case AIMessage::ROLE_TOOL: {
				const Dictionary metadata = msg->get_metadata();
				const String tool_name = metadata.get("tool_name", "tool");
				const String artifact_path = metadata.get("artifact_path", "");
				String tool_line = vformat("- %s: %s", tool_name, snippet);
				if (!artifact_path.is_empty()) {
					tool_line += " (" + artifact_path + ")";
				}
				tool_lines.push_back(tool_line);
			} break;
			case AIMessage::ROLE_SYSTEM:
				if (snippet.findn("TODO") != -1 || snippet.findn("open question") != -1) {
					open_lines.push_back("- " + snippet);
				}
				break;
		}
	}

	String summary = "User goal:\n";
	summary += goal_lines.is_empty() ? "- No earlier user messages were preserved.\n" : String("\n").join(goal_lines) + "\n";
	summary += "\nKey decisions:\n";
	summary += decision_lines.is_empty() ? "- No earlier assistant decisions were preserved.\n" : String("\n").join(decision_lines) + "\n";
	summary += "\nTool outcomes and changed files/scenes:\n";
	summary += tool_lines.is_empty() ? "- No earlier tool results were preserved.\n" : String("\n").join(tool_lines) + "\n";
	summary += "\nOpen questions:\n";
	summary += open_lines.is_empty() ? "- None captured in the summarized portion.\n" : String("\n").join(open_lines) + "\n";
	return summary.strip_edges();
}

void AIAgentSession::_fallback_trim_history() {
	if (messages.size() <= 6) {
		return;
	}

	const int target = (int)(MAX(1, _resolve_run_config().estimated_context_window) * 0.6);
	for (int i = 1; i < messages.size() - 4 && _estimate_history_tokens() > target; ) {
		if (messages[i].is_valid() && messages[i]->get_role() == AIMessage::ROLE_TOOL) {
			messages.remove_at(i);
			continue;
		}
		i++;
	}

	Ref<AIMessage> note = AIMessage::create_system("Previous tool results were trimmed after summarization could not reduce the conversation enough.");
	if (messages.size() > 1 && messages[1].is_valid() && messages[1]->get_role() == AIMessage::ROLE_SYSTEM) {
		messages.write[1] = note;
	} else {
		messages.insert(1, note);
	}
}

void AIAgentSession::_maybe_summarize_history() {
	if (messages.size() < 8) {
		return;
	}

	const int threshold = (int)(MAX(1, _resolve_run_config().estimated_context_window) * 0.6);
	if (_estimate_history_tokens() <= threshold) {
		return;
	}

	int preserved_non_system = 0;
	int keep_from = messages.size();
	for (int i = messages.size() - 1; i >= 0; i--) {
		if (messages[i].is_valid() && messages[i]->get_role() != AIMessage::ROLE_SYSTEM) {
			preserved_non_system++;
			if (preserved_non_system >= 4) {
				keep_from = i;
				break;
			}
		}
	}

	if (keep_from <= 1 || keep_from >= messages.size()) {
		return;
	}

	Vector<Ref<AIMessage>> to_summarize;
	for (int i = 1; i < keep_from; i++) {
		if (messages[i].is_valid()) {
			to_summarize.push_back(messages[i]);
		}
	}

	const String summary = _summarize_messages(to_summarize);
	if (summary.is_empty()) {
		_fallback_trim_history();
		return;
	}

	Vector<Ref<AIMessage>> compacted;
	if (!messages.is_empty() && messages[0].is_valid()) {
		compacted.push_back(messages[0]);
	}
	compacted.push_back(AIMessage::create_system("Previous context summary:\n" + summary));
	for (int i = keep_from; i < messages.size(); i++) {
		compacted.push_back(messages[i]);
	}

	messages = compacted;
	persisted_summary = summary;

	if (_estimate_history_tokens() > threshold) {
		_fallback_trim_history();
	}
}

void AIAgentSession::_append_message(const Ref<AIMessage> &p_message) {
	if (p_message.is_null()) {
		return;
	}
	messages.push_back(p_message);
	_maybe_summarize_history();
	_autosave_session();
}

String AIAgentSession::_read_project_rules() const {
	const String rules_path = "res://.godoty/rules.md";
	Ref<FileAccess> file = FileAccess::open(rules_path, FileAccess::READ);
	if (file.is_null()) {
		return "";
	}

	String rules = file->get_as_text().strip_edges();
	if (rules.length() > 4000) {
		rules = rules.substr(0, 4000) + "\n...[truncated project rules]";
	}
	return rules;
}

String AIAgentSession::_build_environment_notes(const ResolvedAgentRunConfig &p_run_config) const {
	String notes;
	notes += "Current mode: " + p_run_config.mode.title + ".";
	notes += "\nModel: " + p_run_config.model_name + ".";
	notes += "\nEstimated context window: " + itos(p_run_config.estimated_context_window) + " tokens.";
	notes += "\nStreaming: " + String(p_run_config.stream_responses ? "enabled" : "disabled") + ".";
	notes += "\nSession ID: " + session_id + ".";
	if (!persisted_summary.is_empty()) {
		notes += "\nConversation summary is active for older turns.";
	}
	return notes;
}

Dictionary AIAgentSession::_write_tool_result_artifact(const String &p_tool_call_id, const Variant &p_result) const {
	Dictionary metadata;
	String result_str = p_result.get_type() == Variant::STRING ? String(p_result) : JSON::stringify(p_result, "  ");
	if (result_str.length() <= MAX_INLINE_RESULT_CHARS) {
		return metadata;
	}

	DirAccess::make_dir_recursive_absolute(_get_tool_results_dir_path());
	const bool is_plain_text = p_result.get_type() == Variant::STRING;
	const String artifact_path = _get_tool_results_dir_path().path_join(_sanitize_session_component(p_tool_call_id) + (is_plain_text ? ".txt" : ".json"));
	Ref<FileAccess> file = FileAccess::open(artifact_path, FileAccess::WRITE);
	if (file.is_null()) {
		return metadata;
	}
	file->store_string(result_str);
	file->flush();
	metadata["artifact_path"] = artifact_path;
	return metadata;
}

Dictionary AIAgentSession::_capture_snapshot_batch(const PendingToolCall &p_pending) const {
	Dictionary batch;
	AIToolRegistry *registry = AIToolRegistry::get_singleton();
	if (!registry) {
		return batch;
	}

	batch["tool_name"] = p_pending.tool_name;
	batch["tool_call_id"] = p_pending.tool_call_id;
	batch["timestamp"] = (int64_t)Time::get_singleton()->get_unix_time_from_system();

	const AIToolRegistry::ExecutionPolicy policy = registry->get_tool_execution_policy(p_pending.tool_name);
	if (policy == AIToolRegistry::EXECUTION_MUTATING_SCENE) {
		batch["kind"] = "editor_undo";
#ifdef TOOLS_ENABLED
		if (p_pending.tool_name == "create_scene") {
			Node *root = EditorInterface::get_singleton()->get_edited_scene_root();
			if (root) {
				const String scene_path = root->get_scene_file_path();
				if (!scene_path.is_empty()) {
					batch["previous_scene_path"] = scene_path;
				}
			}
		}
#endif
		return batch;
	}

	if (policy != AIToolRegistry::EXECUTION_MUTATING_FILE) {
		return batch;
	}

	Array snapshot_entries;
	const auto add_path = [&](const String &p_path) {
		if (p_path.is_empty()) {
			return;
		}
		for (int i = 0; i < snapshot_entries.size(); i++) {
			Dictionary existing = snapshot_entries[i];
			if ((String)existing.get("path", "") == p_path) {
				return;
			}
		}
		Dictionary entry;
		entry["path"] = p_path;
		const bool existed = FileAccess::exists(p_path);
		entry["existed"] = existed;
		if (existed) {
			Ref<FileAccess> file = FileAccess::open(p_path, FileAccess::READ);
			entry["content"] = file.is_valid() ? file->get_as_text() : String();
		}
		snapshot_entries.push_back(entry);
	};

	if (p_pending.arguments.has("path")) {
		add_path(p_pending.arguments["path"]);
	}
	if (p_pending.arguments.has("from")) {
		add_path(p_pending.arguments["from"]);
	}
	if (p_pending.arguments.has("to")) {
		add_path(p_pending.arguments["to"]);
	}
#ifdef TOOLS_ENABLED
	if (p_pending.tool_name == "save_scene") {
		Node *root = EditorInterface::get_singleton()->get_edited_scene_root();
		if (root) {
			add_path((String)p_pending.arguments.get("path", root->get_scene_file_path()));
		}
	}
#endif

	if (snapshot_entries.is_empty()) {
		return batch;
	}

	batch["kind"] = "files";
	batch["entries"] = snapshot_entries;
	DirAccess::make_dir_recursive_absolute(_get_snapshot_root_dir_path());
	const String snapshot_file = _get_snapshot_root_dir_path().path_join(vformat("%s_%s.json",
			itos((int64_t)batch["timestamp"]),
			_sanitize_session_component(p_pending.tool_call_id)));
	Ref<FileAccess> file = FileAccess::open(snapshot_file, FileAccess::WRITE);
	if (file.is_valid()) {
		file->store_string(JSON::stringify(batch, "  "));
		file->flush();
		batch["snapshot_file"] = snapshot_file;
	}
	return batch;
}

bool AIAgentSession::_restore_snapshot_batch(const Dictionary &p_batch) {
	const String kind = p_batch.get("kind", "");
	if (kind == "editor_undo") {
#ifdef TOOLS_ENABLED
		EditorUndoRedoManager *undo_redo = EditorUndoRedoManager::get_singleton();
		if (undo_redo && undo_redo->has_undo()) {
			undo_redo->undo();
			return true;
		}
		const String previous_scene_path = p_batch.get("previous_scene_path", "");
		if (!previous_scene_path.is_empty()) {
			EditorInterface::get_singleton()->open_scene_from_path(previous_scene_path);
			return true;
		}
#endif
		return false;
	}

	if (kind != "files") {
		return false;
	}

	Array entries = p_batch.get("entries", Array());
	for (int i = 0; i < entries.size(); i++) {
		Dictionary entry = entries[i];
		const String path = entry.get("path", "");
		if (path.is_empty()) {
			continue;
		}
		if ((bool)entry.get("existed", false)) {
			DirAccess::make_dir_recursive_absolute(path.get_base_dir());
			Ref<FileAccess> file = FileAccess::open(path, FileAccess::WRITE);
			if (file.is_valid()) {
				file->store_string(entry.get("content", ""));
				file->flush();
			}
		} else if (FileAccess::exists(path)) {
			Ref<DirAccess> dir = DirAccess::open(path.get_base_dir());
			if (dir.is_valid()) {
				dir->remove(path.get_file());
			}
		}
	}

#ifdef TOOLS_ENABLED
	EditorFileSystem::get_singleton()->scan();
#endif
	return true;
}

void AIAgentSession::_finalize_tool_result(const PendingToolCall &p_pending, const Variant &p_result, const Dictionary &p_metadata) {
	Dictionary metadata = p_metadata.duplicate(true);
	metadata["tool_name"] = p_pending.tool_name;
	metadata["tool_call_id"] = p_pending.tool_call_id;

	String result_str = p_result.get_type() == Variant::STRING ? String(p_result) : JSON::stringify(p_result, "  ");
	Dictionary artifact_metadata = _write_tool_result_artifact(p_pending.tool_call_id, p_result);
	if (artifact_metadata.has("artifact_path")) {
		metadata.merge(artifact_metadata);
		result_str = result_str.substr(0, MAX_INLINE_RESULT_CHARS) +
				"\n\n[Full result saved to " + String(artifact_metadata["artifact_path"]) + ". Use read_file to inspect it.]";
	}

	emit_signal("tool_call_completed", p_pending.tool_name, p_result, p_pending.tool_call_id);
	Ref<AIMessage> tool_result = AIMessage::create_tool_result(p_pending.tool_call_id, result_str);
	tool_result->set_metadata(metadata);
	_append_message(tool_result);
}

TypedArray<Dictionary> AIAgentSession::_build_orchestrator_tool_schemas() const {
	TypedArray<Dictionary> tool_schemas;
	if (mode != AI_AGENT_MODE_ORCHESTRATE) {
		return tool_schemas;
	}

	Dictionary params;
	params["type"] = "object";
	Dictionary props;
	Dictionary mode_prop;
	mode_prop["type"] = "string";
	mode_prop["enum"] = PackedStringArray({ "ask", "edit", "plan", "debug" });
	mode_prop["description"] = "Child session mode.";
	props["mode"] = mode_prop;
	Dictionary prompt_prop;
	prompt_prop["type"] = "string";
	prompt_prop["description"] = "Concrete task for the child session.";
	props["prompt"] = prompt_prop;
	Dictionary context_prop;
	context_prop["type"] = "object";
	context_prop["description"] = "Optional caller-provided context passed only to the child.";
	props["context"] = context_prop;
	params["properties"] = props;
	params["required"] = PackedStringArray({ "mode", "prompt" });

	Dictionary func;
	func["name"] = "new_task";
	func["description"] = "Spawn a focused child AI session and return its summarized result.";
	func["parameters"] = params;

	Dictionary schema;
	schema["type"] = "function";
	schema["function"] = func;
	tool_schemas.push_back(schema);
	return tool_schemas;
}

bool AIAgentSession::_is_orchestrator_tool(const String &p_tool_name) const {
	return mode == AI_AGENT_MODE_ORCHESTRATE && p_tool_name == "new_task";
}

void AIAgentSession::_start_child_task(const PendingToolCall &p_pending) {
	if (orchestration_depth >= MAX_CHILD_TASK_DEPTH) {
		_finalize_tool_result(p_pending, "Error: Maximum child task depth reached.");
		_continue_tool_processing();
		return;
	}
	if (child_tasks_spawned_this_turn >= MAX_CHILD_TASKS_PER_TURN) {
		_finalize_tool_result(p_pending, "Error: Maximum child task count reached for this turn.");
		_continue_tool_processing();
		return;
	}

	String mode_name = String(p_pending.arguments.get("mode", "")).to_lower().strip_edges();
	AIAgentModeId child_mode = AI_AGENT_MODE_ASK;
	if (mode_name == "ask") {
		child_mode = AI_AGENT_MODE_ASK;
	} else if (mode_name == "edit") {
		child_mode = AI_AGENT_MODE_EDIT;
	} else if (mode_name == "plan") {
		child_mode = AI_AGENT_MODE_PLAN;
	} else if (mode_name == "debug") {
		child_mode = AI_AGENT_MODE_DEBUG;
	} else {
		_finalize_tool_result(p_pending, "Error: Child mode must be one of ask, edit, plan, or debug.");
		_continue_tool_processing();
		return;
	}

	const String prompt = String(p_pending.arguments.get("prompt", "")).strip_edges();
	if (prompt.is_empty()) {
		_finalize_tool_result(p_pending, "Error: Child task prompt is required.");
		_continue_tool_processing();
		return;
	}

	active_child_session.instantiate();
	active_child_session->set_config(config);
	active_child_session->set_mode(child_mode);
	active_child_session->set_orchestration_depth(orchestration_depth + 1);
	active_child_session->connect("message_received", callable_mp(this, &AIAgentSession::_on_child_message_received));
	active_child_session->connect("approval_required", callable_mp(this, &AIAgentSession::_on_child_approval_required));
	active_child_session->connect("error_occurred", callable_mp(this, &AIAgentSession::_on_child_error));
	active_child_session->connect("session_completed", callable_mp(this, &AIAgentSession::_on_child_session_completed));

	child_task_active = true;
	active_child_task_call = p_pending;
	active_child_result_content = "";
	child_tasks_spawned_this_turn++;
	const Dictionary child_context = p_pending.arguments.get("context", Dictionary());
	active_child_session->send_message_with_context(prompt, child_context);
}

void AIAgentSession::_on_child_message_received(const Ref<AIMessage> &p_message) {
	if (p_message.is_valid() && p_message->get_role() == AIMessage::ROLE_ASSISTANT && !p_message->has_tool_calls() && !p_message->get_content().is_empty()) {
		active_child_result_content = p_message->get_content();
	}
}

void AIAgentSession::_on_child_approval_required(const String &p_tool_name, const Dictionary &p_args, const String &p_tool_call_id) {
	state = STATE_WAITING_FOR_APPROVAL;
	emit_signal("state_changed", (int)state);
	emit_signal("approval_required", p_tool_name, p_args, p_tool_call_id);
}

void AIAgentSession::_on_child_error(const String &p_error) {
	_finalize_tool_result(active_child_task_call, "Child task failed: " + p_error);
	child_task_active = false;
	active_child_session.unref();
	state = STATE_PROCESSING_TOOL_CALLS;
	emit_signal("state_changed", (int)state);
	_continue_tool_processing();
}

void AIAgentSession::_on_child_session_completed() {
	String content = active_child_result_content.strip_edges();
	if (content.is_empty()) {
		content = "Child task finished without an assistant summary.";
	}
	Dictionary metadata;
	metadata["child_mode"] = ai_agent_mode_get_name(active_child_session.is_valid() ? active_child_session->get_mode() : AI_AGENT_MODE_ASK);
	_finalize_tool_result(active_child_task_call, content, metadata);
	child_task_active = false;
	active_child_result_content = "";
	active_child_session.unref();
	state = STATE_PROCESSING_TOOL_CALLS;
	emit_signal("state_changed", (int)state);
	_continue_tool_processing();
}

bool AIAgentSession::_tool_requires_user_approval(const String &p_tool_name) const {
	AIToolRegistry *registry = AIToolRegistry::get_singleton();
	ERR_FAIL_NULL_V(registry, true);
	if (!registry->tool_requires_approval(p_tool_name)) {
		return false;
	}
	if (config.is_valid() && config->get_approval_policy() == AIAgentConfig::APPROVAL_ALWAYS_ALLOW) {
		return false;
	}
	return true;
}

void AIAgentSession::_execute_parallel_read_only_batch() {
	AIToolRegistry *registry = AIToolRegistry::get_singleton();
	ERR_FAIL_NULL(registry);

	Vector<PendingToolCall> batch;
	while (!pending_tool_calls.is_empty()) {
		const PendingToolCall &pending = pending_tool_calls[0];
		if (_tool_requires_user_approval(pending.tool_name) ||
				registry->get_tool_execution_policy(pending.tool_name) != AIToolRegistry::EXECUTION_READ_ONLY ||
				!registry->is_tool_parallel_safe(pending.tool_name) ||
				_is_orchestrator_tool(pending.tool_name)) {
			break;
		}
		batch.push_back(pending);
		pending_tool_calls.remove_at(0);
	}

	Vector<ParallelToolExecutionData> data;
	data.resize(batch.size());
	Vector<Thread *> threads;
	threads.resize(batch.size());

	for (int i = 0; i < batch.size(); i++) {
		emit_signal("tool_call_requested", batch[i].tool_name, batch[i].arguments, batch[i].tool_call_id);
		data.write[i].registry = registry;
		data.write[i].tool_name = batch[i].tool_name;
		data.write[i].arguments = batch[i].arguments;
		threads.write[i] = memnew(Thread);
		threads[i]->start(_execute_parallel_tool_task, &data.write[i]);
	}

	for (int i = 0; i < batch.size(); i++) {
		if (threads[i]) {
			threads[i]->wait_to_finish();
			memdelete(threads[i]);
		}
		_finalize_tool_result(batch[i], data[i].result);
	}
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
		case AIAgentConfig::PROVIDER_MINIMAX: {
			Ref<MiniMaxProvider> minimax;
			minimax.instantiate();
			p = minimax;
		} break;
		case AIAgentConfig::PROVIDER_LOCAL: {
			Ref<LocalLLMProvider> local;
			local.instantiate();
			p = local;
		} break;
		case AIAgentConfig::PROVIDER_CUSTOM: {
			Ref<OpenAIProvider> custom;
			custom.instantiate();
			p = custom;
		} break;
	}

	if (p.is_valid()) {
		p->set_api_key(config->get_api_key());
		p->set_base_url(config->get_effective_base_url());
		p->set_model_name(config->get_model_name());
	}

	return p;
}

ResolvedAgentRunConfig AIAgentSession::_resolve_run_config() const {
	AIToolRegistry *registry = AIToolRegistry::get_singleton();
	PackedStringArray available_tools;
	if (registry) {
		available_tools = registry->get_tool_names();
	}
	return ai_agent_resolve_run_config(config, mode, available_tools);
}

void AIAgentSession::_apply_run_config_to_provider(const ResolvedAgentRunConfig &p_run_config) {
	ERR_FAIL_COND(provider.is_null());

	if (config.is_valid()) {
		provider->set_api_key(config->get_api_key());
	}
	provider->set_base_url(p_run_config.base_url);
	provider->set_model_name(p_run_config.model_name);

	if (p_run_config.use_temperature) {
		provider->set_temperature(p_run_config.temperature);
	} else {
		provider->clear_temperature_override();
	}

	if (p_run_config.use_max_output_tokens) {
		provider->set_max_tokens(p_run_config.max_output_tokens);
	} else {
		provider->clear_max_tokens_override();
	}
}

String AIAgentSession::_build_effective_system_prompt(const ResolvedAgentRunConfig &p_run_config) const {
	String prompt = p_run_config.mode.harness_prompt;
	AIToolRegistry *registry = AIToolRegistry::get_singleton();
	if (registry) {
		PackedStringArray listed_tools = p_run_config.allowed_tools;
		if (listed_tools.is_empty()) {
			listed_tools = registry->get_tool_names();
		}
		if (mode == AI_AGENT_MODE_ORCHESTRATE) {
			listed_tools.push_back("new_task");
		}
		if (!listed_tools.is_empty()) {
			prompt += "\n\nAvailable tools: " + String(", ").join(listed_tools) + ".";
		}

		String usage_guide = registry->get_tool_usage_guide(p_run_config.allowed_tools);
		if (mode == AI_AGENT_MODE_ORCHESTRATE) {
			if (!usage_guide.is_empty()) {
				usage_guide += "\n";
			}
			usage_guide += "- new_task: Spawn a focused child task only after inspecting the project and only when decomposition materially helps. Returns child findings you must integrate.";
		}
		if (!usage_guide.is_empty()) {
			prompt += "\n\nTool usage guide:\n" + usage_guide;
		}
	}
	prompt += "\n\nReference rule: if you are unsure about a node API, property name, signal, method, or script surface, call inspect_node, get_class_reference, or get_script_reference before mutating files or scenes.";
	prompt += "\n\n" + _build_environment_notes(p_run_config);
	const String project_rules = _read_project_rules();
	if (!project_rules.is_empty()) {
		prompt += "\n\nProject rules from res://.godoty/rules.md:\n" + project_rules;
	}

	return prompt;
}

bool AIAgentSession::_has_non_system_history() const {
	for (int i = 0; i < messages.size(); i++) {
		if (messages[i].is_valid() && messages[i]->get_role() != AIMessage::ROLE_SYSTEM) {
			return true;
		}
	}

	return false;
}

Dictionary AIAgentSession::_build_turn_context(const Dictionary &p_context) const {
	Dictionary context;
	int non_system_message_count = 0;

	if (!p_context.is_empty()) {
		context["caller_context"] = p_context;
	}

	for (int i = 0; i < messages.size(); i++) {
		if (messages[i].is_valid() && messages[i]->get_role() != AIMessage::ROLE_SYSTEM) {
			non_system_message_count++;
		}
	}

	AIContextManager *ctx_mgr = AIContextManager::get_singleton();
	if (!ctx_mgr) {
		return context;
	}

	// Dynamic context budgets: scale with the resolved model context window.
	ResolvedAgentRunConfig run_config = _resolve_run_config();
	int total_budget = MIN((int)(run_config.estimated_context_window * 0.15), 8000);
	total_budget = MAX(total_budget, 1200);
	int focus_budget = total_budget * 60 / 100;    // 60% for current focus.
	int workspace_budget = total_budget * 40 / 100; // 40% for workspace.

	Dictionary focus_context = ctx_mgr->collect_context_budgeted(
			AIContextManager::CONTEXT_SCENE |
					AIContextManager::CONTEXT_SCRIPTS |
					AIContextManager::CONTEXT_EDITOR_STATE |
					AIContextManager::CONTEXT_REFERENCE |
					AIContextManager::CONTEXT_RUNTIME,
			focus_budget);
	if (!focus_context.is_empty()) {
		context["focus"] = focus_context;
	}

	if (non_system_message_count <= 1) {
		Dictionary workspace_context = ctx_mgr->collect_context_budgeted(
				AIContextManager::CONTEXT_PROJECT |
						AIContextManager::CONTEXT_ASSETS,
				workspace_budget);
		if (!workspace_context.is_empty()) {
			context["workspace"] = workspace_context;
		}
	}

	return context;
}

void AIAgentSession::_append_context_message(TypedArray<Ref<AIMessage>> &r_messages, const String &p_title, const Dictionary &p_context) const {
	if (p_context.is_empty()) {
		return;
	}

	String context_str = p_title + ":\n" + JSON::stringify(p_context, "  ");
	r_messages.push_back(AIMessage::create_system(context_str));
}

void AIAgentSession::send_message(const String &p_content) {
	_send_user_message(p_content, Dictionary());
}

void AIAgentSession::send_message_with_context(const String &p_content, const Dictionary &p_context) {
	_send_user_message(p_content, p_context);
}

void AIAgentSession::_send_user_message(const String &p_content, const Dictionary &p_context) {
	if (is_busy()) {
		_on_error("The AI agent is already working. Cancel the current request or wait for it to finish.");
		return;
	}
	if (config.is_null()) {
		_on_error("No AI provider has been configured yet.");
		return;
	}
	if (provider.is_null()) {
		_on_error("No AI provider is available for the current configuration.");
		return;
	}
	if (p_content.strip_edges().is_empty()) {
		return;
	}

	// Per-turn system prompt rebuild: always refresh the system prompt.
	ResolvedAgentRunConfig run_config = _resolve_run_config();
	String system_prompt = _build_effective_system_prompt(run_config);
	if (!_has_non_system_history()) {
		// First message: insert the system prompt.
		_append_message(AIMessage::create_system(system_prompt));
	} else {
		// Subsequent messages: update the existing system prompt in place.
		for (int i = 0; i < messages.size(); i++) {
			if (messages[i].is_valid() && messages[i]->get_role() == AIMessage::ROLE_SYSTEM) {
				messages.write[i] = AIMessage::create_system(system_prompt);
				break;
			}
		}
	}

	// Add the user's message.
	Ref<AIMessage> user_msg = AIMessage::create_user(p_content);
	_append_message(user_msg);

	state = STATE_SENDING;
	current_tool_iteration = 0;
	child_tasks_spawned_this_turn = 0;
	emit_signal("state_changed", (int)state);

	pending_tool_calls.clear();
	_reset_streaming_accumulator();
	_dispatch_request(_build_request_messages(p_context));
}

TypedArray<Ref<AIMessage>> AIAgentSession::_build_request_messages(const Dictionary &p_context) const {
	TypedArray<Ref<AIMessage>> msgs;
	const int context_insert_index = MAX(0, messages.size() - 1);
	Dictionary turn_context = _build_turn_context(p_context);
	ResolvedAgentRunConfig run_config = _resolve_run_config();

	for (int i = 0; i < messages.size(); i++) {
		if (i == context_insert_index && !turn_context.is_empty()) {
			if (turn_context.has("workspace")) {
				_append_context_message(msgs, "Workspace snapshot", turn_context["workspace"]);
			}
			if (turn_context.has("focus")) {
				_append_context_message(msgs, "Current editor focus", turn_context["focus"]);
			}
			if (turn_context.has("caller_context")) {
				_append_context_message(msgs, "Caller-provided context", turn_context["caller_context"]);
			}
			if (config.is_valid()) {
				Dictionary execution_notes;
				execution_notes["provider"] = config->get_provider_name();
				execution_notes["model"] = run_config.model_name;
				execution_notes["mode"] = ai_agent_mode_get_name(mode);
				execution_notes["streaming"] = run_config.stream_responses;
				_append_context_message(msgs, "Execution settings", execution_notes);
			}
		}
		msgs.push_back(messages[i]);
	}

	return msgs;
}

TypedArray<Dictionary> AIAgentSession::_get_enabled_tool_schemas(const ResolvedAgentRunConfig &p_run_config) const {
	TypedArray<Dictionary> tool_schemas;
	AIToolRegistry *registry = AIToolRegistry::get_singleton();
	if (!registry || config.is_null()) {
		return tool_schemas;
	}

	if (p_run_config.allowed_tools.is_empty()) {
		return registry->get_tool_schemas();
	}

	for (int i = 0; i < p_run_config.allowed_tools.size(); i++) {
		if (registry->has_tool(p_run_config.allowed_tools[i])) {
			tool_schemas.push_back(registry->get_tool_schema(p_run_config.allowed_tools[i]));
		}
	}
	TypedArray<Dictionary> orchestrator_tools = _build_orchestrator_tool_schemas();
	for (int i = 0; i < orchestrator_tools.size(); i++) {
		tool_schemas.push_back(orchestrator_tools[i]);
	}

	return tool_schemas;
}

void AIAgentSession::_dispatch_request(const TypedArray<Ref<AIMessage>> &p_messages) {
	state = STATE_WAITING_FOR_RESPONSE;
	emit_signal("state_changed", (int)state);

	ResolvedAgentRunConfig run_config = _resolve_run_config();
	_apply_run_config_to_provider(run_config);

	TypedArray<Dictionary> tool_schemas = _get_enabled_tool_schemas(run_config);
	Error err;
	if (run_config.stream_responses) {
		err = provider->stream_message(p_messages, tool_schemas,
				callable_mp(this, &AIAgentSession::_on_stream_chunk),
				callable_mp(this, &AIAgentSession::_on_stream_complete));
	} else {
		err = provider->send_message(p_messages, tool_schemas,
				callable_mp(this, &AIAgentSession::_on_response_received));
	}

	if (err != OK) {
		_on_error(vformat("Failed to send message: error %d", err));
	}
}

void AIAgentSession::add_system_message(const String &p_content) {
	_append_message(AIMessage::create_system(p_content));
}

void AIAgentSession::clear_history() {
	messages.clear();
	pending_tool_calls.clear();
	snapshot_batches.clear();
	persisted_summary = "";
	child_task_active = false;
	active_child_result_content = "";
	active_child_session.unref();
	_reset_streaming_accumulator();
	state = STATE_IDLE;
	current_tool_iteration = 0;
	emit_signal("state_changed", (int)state);
	_autosave_session();
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

String AIAgentSession::get_session_id() const {
	return session_id;
}

bool AIAgentSession::restore_last_saved_session() {
	(void)_ensure_session_id();
	Ref<DirAccess> dir = DirAccess::open(_get_sessions_dir_path());
	if (dir.is_null()) {
		return false;
	}

	String latest_path;
	uint64_t latest_mtime = 0;
	dir->list_dir_begin();
	String item = dir->get_next();
	while (!item.is_empty()) {
		if (!dir->current_is_dir() && item.get_extension() == "json") {
			const String candidate = _get_sessions_dir_path().path_join(item);
			Ref<FileAccess> file = FileAccess::open(candidate, FileAccess::READ);
			if (file.is_valid()) {
				JSON json;
				if (json.parse(file->get_as_text()) == OK && json.get_data().get_type() == Variant::DICTIONARY) {
					Dictionary data = json.get_data();
					if ((int)data.get("state", (int)STATE_ERROR) == (int)STATE_IDLE) {
						const uint64_t mtime = FileAccess::get_modified_time(candidate);
						if (mtime >= latest_mtime) {
							latest_mtime = mtime;
							latest_path = candidate;
						}
					}
				}
			}
		}
		item = dir->get_next();
	}
	dir->list_dir_end();

	if (latest_path.is_empty()) {
		return false;
	}
	return _restore_session_from_path(latest_path);
}

bool AIAgentSession::has_ai_edit_snapshots() const {
	return !snapshot_batches.is_empty();
}

bool AIAgentSession::can_undo_last_ai_edit() const {
	return has_ai_edit_snapshots();
}

bool AIAgentSession::undo_all_ai_edits() {
	if (snapshot_batches.is_empty()) {
		return false;
	}

	for (int i = snapshot_batches.size() - 1; i >= 0; i--) {
		if (!_restore_snapshot_batch(snapshot_batches[i].data)) {
			return false;
		}
	}

	snapshot_batches.clear();
	_append_message(AIMessage::create_system("Undid all AI edits from this session."));
	_autosave_session();
	return true;
}

bool AIAgentSession::undo_last_ai_edit() {
	if (snapshot_batches.is_empty()) {
		return false;
	}

	const Dictionary batch = snapshot_batches[snapshot_batches.size() - 1].data;
	if (!_restore_snapshot_batch(batch)) {
		return false;
	}

	snapshot_batches.remove_at(snapshot_batches.size() - 1);
	_append_message(AIMessage::create_system("Undid the most recent AI edit."));
	_autosave_session();
	return true;
}

void AIAgentSession::cancel() {
	if (provider.is_valid()) {
		provider->cancel();
	}
	if (active_child_session.is_valid()) {
		active_child_session->cancel();
		active_child_session.unref();
		child_task_active = false;
		active_child_result_content = "";
	}
	pending_tool_calls.clear();
	_reset_streaming_accumulator();
	state = STATE_IDLE;
	emit_signal("state_changed", (int)state);
	_autosave_session();
}

void AIAgentSession::_on_response_received(const Ref<AIMessage> &p_response) {
	if (p_response.is_null()) {
		_on_error("Received null response from provider.");
		return;
	}

	Ref<AIMessage> sanitized_response = _sanitize_assistant_message(p_response);
	_reset_streaming_accumulator();

	if (!sanitized_response->has_tool_calls() && sanitized_response->get_content().begins_with("Error: ")) {
		_on_error(sanitized_response->get_content().trim_prefix("Error: ").strip_edges());
		return;
	}

	_append_message(sanitized_response);
	emit_signal("message_received", sanitized_response);

	if (sanitized_response->has_tool_calls()) {
		_process_tool_calls(sanitized_response);
	} else {
		state = STATE_IDLE;
		emit_signal("state_changed", (int)state);
		_autosave_session();
		emit_signal("session_completed");
	}
}

void AIAgentSession::_on_stream_chunk(const Ref<AIMessage> &p_chunk) {
	if (p_chunk.is_null()) {
		return;
	}

	streaming_raw_content += p_chunk->get_content();

	const ParsedAssistantContent parsed = _parse_assistant_content(streaming_raw_content);
	String next_visible_total = parsed.visible_content;
	String next_thinking_total = parsed.thinking_content;
	if (next_thinking_total.length() < streaming_thinking_content.length()) {
		next_thinking_total = streaming_thinking_content;
	}
	if (!p_chunk->get_thinking_content().is_empty()) {
		next_thinking_total += p_chunk->get_thinking_content();
	}

	String visible_delta;
	if (next_visible_total.length() > streaming_visible_content.length()) {
		visible_delta = next_visible_total.substr(streaming_visible_content.length());
	}

	String thinking_delta;
	if (next_thinking_total.length() > streaming_thinking_content.length()) {
		thinking_delta = next_thinking_total.substr(streaming_thinking_content.length());
	}

	streaming_visible_content = next_visible_total;
	streaming_thinking_content = next_thinking_total;
	_set_streaming_thinking_active(parsed.thinking_active);

	if (visible_delta.is_empty() && thinking_delta.is_empty() && !p_chunk->has_tool_calls()) {
		return;
	}

	emit_signal("stream_chunk", AIMessage::create_assistant(visible_delta, p_chunk->get_tool_calls(), thinking_delta));
}

void AIAgentSession::_on_stream_complete(const Ref<AIMessage> &p_full_response) {
	_on_response_received(p_full_response);
}

void AIAgentSession::_on_error(const String &p_error) {
	_reset_streaming_accumulator();
	state = STATE_ERROR;
	emit_signal("state_changed", (int)state);
	emit_signal("error_occurred", p_error);
	_autosave_session();
}

void AIAgentSession::_process_tool_calls(const Ref<AIMessage> &p_message) {
	current_tool_iteration++;
	if (current_tool_iteration > max_tool_iterations) {
		_on_error("Maximum tool call iterations exceeded. Possible infinite loop.");
		return;
	}
	child_tasks_spawned_this_turn = 0;

	state = STATE_PROCESSING_TOOL_CALLS;
	emit_signal("state_changed", (int)state);

	AIToolRegistry *registry = AIToolRegistry::get_singleton();
	ERR_FAIL_NULL_MSG(registry, "AIToolRegistry singleton not available.");

	TypedArray<Dictionary> tool_calls = p_message->get_tool_calls();
	pending_tool_calls.clear();
	for (int i = 0; i < tool_calls.size(); i++) {
		Dictionary tc = tool_calls[i];
		Dictionary function = tc.get("function", Dictionary());
		String args_str = function.get("arguments", "{}");

		PendingToolCall pending;
		pending.tool_call_id = tc.get("id", "");
		pending.tool_name = _resolve_tool_name_alias(function.get("name", ""));

		JSON json;
		if (json.parse(args_str) == OK && json.get_data().get_type() == Variant::DICTIONARY) {
			pending.arguments = json.get_data();
		} else {
			pending.arguments = Dictionary();
		}
		pending_tool_calls.push_back(pending);
	}

	_continue_tool_processing();
}

void AIAgentSession::_continue_tool_processing() {
	AIToolRegistry *registry = AIToolRegistry::get_singleton();
	ERR_FAIL_NULL_MSG(registry, "AIToolRegistry singleton not available.");

	while (!pending_tool_calls.is_empty()) {
		if (child_task_active) {
			return;
		}

		const PendingToolCall &next_pending = pending_tool_calls[0];
		if (!_tool_requires_user_approval(next_pending.tool_name) &&
				registry->get_tool_execution_policy(next_pending.tool_name) == AIToolRegistry::EXECUTION_READ_ONLY &&
				registry->is_tool_parallel_safe(next_pending.tool_name) &&
				!_is_orchestrator_tool(next_pending.tool_name)) {
			_execute_parallel_read_only_batch();
			continue;
		}

		PendingToolCall pending = pending_tool_calls[0];
		emit_signal("tool_call_requested", pending.tool_name, pending.arguments, pending.tool_call_id);

		if (_is_orchestrator_tool(pending.tool_name)) {
			pending_tool_calls.remove_at(0);
			_start_child_task(pending);
			return;
		}

		if (_tool_requires_user_approval(pending.tool_name)) {
			state = STATE_WAITING_FOR_APPROVAL;
			emit_signal("state_changed", (int)state);
			emit_signal("approval_required", pending.tool_name, pending.arguments, pending.tool_call_id);
			return;
		}

		if (registry->has_tool(pending.tool_name)) {
			Dictionary metadata;
			const AIToolRegistry::ExecutionPolicy policy = registry->get_tool_execution_policy(pending.tool_name);
			if (policy == AIToolRegistry::EXECUTION_MUTATING_FILE || policy == AIToolRegistry::EXECUTION_MUTATING_SCENE) {
				Dictionary batch = _capture_snapshot_batch(pending);
				if (!batch.is_empty()) {
					SessionSnapshotBatch snapshot_batch;
					snapshot_batch.data = batch;
					snapshot_batches.push_back(snapshot_batch);
					metadata["snapshot_timestamp"] = batch.get("timestamp", 0);
				}
			}
			Variant result = registry->execute_tool(pending.tool_name, pending.arguments);
			_finalize_tool_result(pending, result, metadata);
		} else {
			String error_msg = vformat("Tool '%s' not found. Available tools: %s",
					pending.tool_name, String(", ").join(registry->get_tool_names()));
			_finalize_tool_result(pending, error_msg);
		}

		pending_tool_calls.remove_at(0);
	}

	if (!child_task_active) {
		_dispatch_request(_build_request_messages());
	}
}

void AIAgentSession::approve_tool_call(const String &p_tool_call_id) {
	ERR_FAIL_COND_MSG(state != STATE_WAITING_FOR_APPROVAL, "Not waiting for approval.");

	if (child_task_active && active_child_session.is_valid() && active_child_session->get_state() == STATE_WAITING_FOR_APPROVAL) {
		active_child_session->approve_tool_call(p_tool_call_id);
		state = STATE_PROCESSING_TOOL_CALLS;
		emit_signal("state_changed", (int)state);
		return;
	}

	AIToolRegistry *registry = AIToolRegistry::get_singleton();
	ERR_FAIL_NULL(registry);
	ERR_FAIL_COND_MSG(pending_tool_calls.is_empty(), "No pending tool calls to approve.");

	PendingToolCall pending = pending_tool_calls[0];
	if (!p_tool_call_id.is_empty() && pending.tool_call_id != p_tool_call_id) {
		ERR_FAIL_MSG("Tool call ID does not match the current pending approval.");
	}

	pending_tool_calls.remove_at(0);

	Dictionary metadata;
	const AIToolRegistry::ExecutionPolicy policy = registry->get_tool_execution_policy(pending.tool_name);
	if (policy == AIToolRegistry::EXECUTION_MUTATING_FILE || policy == AIToolRegistry::EXECUTION_MUTATING_SCENE) {
		Dictionary batch = _capture_snapshot_batch(pending);
		if (!batch.is_empty()) {
			SessionSnapshotBatch snapshot_batch;
			snapshot_batch.data = batch;
			snapshot_batches.push_back(snapshot_batch);
			metadata["snapshot_timestamp"] = batch.get("timestamp", 0);
		}
	}

	Variant result = registry->has_tool(pending.tool_name) ? registry->execute_tool(pending.tool_name, pending.arguments) : Variant(vformat("Tool '%s' not found.", pending.tool_name));
	_finalize_tool_result(pending, result, metadata);

	_continue_tool_processing();
}

void AIAgentSession::deny_tool_call(const String &p_tool_call_id, const String &p_reason) {
	ERR_FAIL_COND_MSG(state != STATE_WAITING_FOR_APPROVAL, "Not waiting for approval.");

	if (child_task_active && active_child_session.is_valid() && active_child_session->get_state() == STATE_WAITING_FOR_APPROVAL) {
		active_child_session->deny_tool_call(p_tool_call_id, p_reason);
		state = STATE_PROCESSING_TOOL_CALLS;
		emit_signal("state_changed", (int)state);
		return;
	}
	ERR_FAIL_COND_MSG(pending_tool_calls.is_empty(), "No pending tool calls to deny.");

	PendingToolCall pending = pending_tool_calls[0];
	if (!p_tool_call_id.is_empty() && pending.tool_call_id != p_tool_call_id) {
		ERR_FAIL_MSG("Tool call ID does not match the current pending approval.");
	}

	pending_tool_calls.remove_at(0);

	String reason = p_reason.is_empty() ? "User denied the tool call." : p_reason;
	Ref<AIMessage> denial = AIMessage::create_tool_result(pending.tool_call_id, "DENIED: " + reason);
	Dictionary metadata;
	metadata["tool_name"] = pending.tool_name;
	metadata["tool_call_id"] = pending.tool_call_id;
	denial->set_metadata(metadata);
	_append_message(denial);

	_continue_tool_processing();
}

void AIAgentSession::set_max_tool_iterations(int p_max) {
	max_tool_iterations = MAX(1, p_max);
}

int AIAgentSession::get_max_tool_iterations() const {
	return max_tool_iterations;
}

void AIAgentSession::set_orchestration_depth(int p_depth) {
	orchestration_depth = MAX(0, p_depth);
	_autosave_session();
}

int AIAgentSession::get_orchestration_depth() const {
	return orchestration_depth;
}
