/**************************************************************************/
/*  ai_provider.cpp                                                       */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "ai_provider.h"

#include "core/io/http_client.h"
#include "core/io/json.h"
#include "scene/main/http_request.h"
#include "scene/main/scene_tree.h"
#include "scene/main/window.h"

void AIProvider::_bind_methods() {
	ClassDB::bind_method(D_METHOD("set_api_key", "key"), &AIProvider::set_api_key);
	ClassDB::bind_method(D_METHOD("get_api_key"), &AIProvider::get_api_key);
	ClassDB::bind_method(D_METHOD("set_base_url", "url"), &AIProvider::set_base_url);
	ClassDB::bind_method(D_METHOD("get_base_url"), &AIProvider::get_base_url);
	ClassDB::bind_method(D_METHOD("set_model_name", "name"), &AIProvider::set_model_name);
	ClassDB::bind_method(D_METHOD("get_model_name"), &AIProvider::get_model_name);
	ClassDB::bind_method(D_METHOD("set_temperature", "temperature"), &AIProvider::set_temperature);
	ClassDB::bind_method(D_METHOD("get_temperature"), &AIProvider::get_temperature);
	ClassDB::bind_method(D_METHOD("set_max_tokens", "max_tokens"), &AIProvider::set_max_tokens);
	ClassDB::bind_method(D_METHOD("get_max_tokens"), &AIProvider::get_max_tokens);
	ClassDB::bind_method(D_METHOD("get_is_busy"), &AIProvider::get_is_busy);
	ClassDB::bind_method(D_METHOD("supports_model_discovery"), &AIProvider::supports_model_discovery);
	ClassDB::bind_method(D_METHOD("request_available_models", "callback"), &AIProvider::request_available_models);

	ADD_PROPERTY(PropertyInfo(Variant::STRING, "api_key"), "set_api_key", "get_api_key");
	ADD_PROPERTY(PropertyInfo(Variant::STRING, "base_url"), "set_base_url", "get_base_url");
	ADD_PROPERTY(PropertyInfo(Variant::STRING, "model_name"), "set_model_name", "get_model_name");
	ADD_PROPERTY(PropertyInfo(Variant::FLOAT, "temperature", PROPERTY_HINT_RANGE, "0.0,2.0,0.01"), "set_temperature", "get_temperature");
	ADD_PROPERTY(PropertyInfo(Variant::INT, "max_tokens", PROPERTY_HINT_RANGE, "1,200000,1"), "set_max_tokens", "get_max_tokens");
	ADD_PROPERTY(PropertyInfo(Variant::BOOL, "is_busy"), "", "get_is_busy");
}

AIProvider::AIProvider() {}

AIProvider::~AIProvider() {
	_cleanup_model_discovery_request();
}

void AIProvider::set_api_key(const String &p_key) {
	api_key = p_key;
}

String AIProvider::get_api_key() const {
	return api_key;
}

void AIProvider::set_base_url(const String &p_url) {
	base_url = p_url;
}

String AIProvider::get_base_url() const {
	return base_url;
}

void AIProvider::set_model_name(const String &p_name) {
	model_name = p_name;
}

String AIProvider::get_model_name() const {
	return model_name;
}

void AIProvider::set_temperature(float p_temp) {
	temperature = CLAMP(p_temp, 0.0f, 2.0f);
	temperature_override_enabled = true;
}

float AIProvider::get_temperature() const {
	return temperature;
}

void AIProvider::clear_temperature_override() {
	temperature_override_enabled = false;
}

bool AIProvider::has_temperature_override() const {
	return temperature_override_enabled;
}

void AIProvider::set_max_tokens(int p_max) {
	max_tokens = MAX(1, p_max);
	max_tokens_override_enabled = true;
}

int AIProvider::get_max_tokens() const {
	return max_tokens;
}

void AIProvider::clear_max_tokens_override() {
	max_tokens_override_enabled = false;
}

bool AIProvider::has_max_tokens_override() const {
	return max_tokens_override_enabled;
}

bool AIProvider::get_is_busy() const {
	return is_busy;
}

bool AIProvider::supports_model_discovery() const {
	return false;
}

String AIProvider::_get_model_discovery_url() const {
	return "";
}

PackedStringArray AIProvider::_get_model_discovery_headers() const {
	return PackedStringArray();
}

PackedStringArray AIProvider::_parse_model_discovery_response(const Variant &p_response) const {
	PackedStringArray models;
	if (p_response.get_type() != Variant::DICTIONARY) {
		return models;
	}

	const Dictionary response = p_response;
	if (!response.has("data")) {
		return models;
	}

	const Array data = response["data"];
	for (int i = 0; i < data.size(); i++) {
		if (data[i].get_type() != Variant::DICTIONARY) {
			continue;
		}
		const Dictionary model = data[i];
		const String model_id = model.get("id", model.get("name", String()));
		if (model_id.is_empty() || models.has(model_id)) {
			continue;
		}
		models.push_back(model_id);
	}

	return models;
}

void AIProvider::_cleanup_model_discovery_request() {
	if (model_discovery_request) {
		HTTPRequest *request = model_discovery_request;
		model_discovery_request = nullptr;
		const Callable completed = callable_mp(this, &AIProvider::_on_model_discovery_request_completed);
		if (request->is_connected("request_completed", completed)) {
			request->disconnect("request_completed", completed);
		}
		request->cancel_request();
		if (request->is_inside_tree() || request->get_parent()) {
			request->queue_free();
		} else {
			memdelete(request);
		}
	}
}

void AIProvider::_on_model_discovery_request_completed(int p_result, int p_code, const PackedStringArray &p_headers, const PackedByteArray &p_body) {
	(void)p_headers;

	PackedStringArray models;
	String error_message;

	if (p_result != HTTPRequest::RESULT_SUCCESS) {
		error_message = "Unable to load models from the provider.";
	} else {
		const String response_text = String::utf8((const char *)p_body.ptr(), p_body.size());
		JSON json;
		Error parse_error = json.parse(response_text);
		if (p_code < 200 || p_code >= 300) {
			error_message = vformat("Provider returned HTTP %d while loading models.", p_code);
		} else if (parse_error != OK) {
			error_message = "Provider returned invalid model list JSON.";
		} else {
			models = _parse_model_discovery_response(json.get_data());
			if (models.is_empty()) {
				error_message = "Provider did not return any models.";
			}
		}
	}

	const Callable callback = pending_model_discovery_callback;
	pending_model_discovery_callback = Callable();
	_cleanup_model_discovery_request();
	if (callback.is_valid()) {
		callback.call(models, error_message);
	}
}

Error AIProvider::request_available_models(const Callable &p_callback) {
	if (!supports_model_discovery()) {
		return ERR_UNAVAILABLE;
	}

	const String url = _get_model_discovery_url();
	if (url.is_empty()) {
		return ERR_UNCONFIGURED;
	}

	SceneTree *tree = SceneTree::get_singleton();
	ERR_FAIL_NULL_V(tree, ERR_UNAVAILABLE);

	_cleanup_model_discovery_request();
	pending_model_discovery_callback = p_callback;
	model_discovery_request = memnew(HTTPRequest);
	model_discovery_request->set_use_threads(true);
	model_discovery_request->set_timeout(30.0);
	tree->get_root()->call_deferred("add_child", model_discovery_request);
	model_discovery_request->connect("request_completed", callable_mp(this, &AIProvider::_on_model_discovery_request_completed), CONNECT_DEFERRED);
	model_discovery_request->call_deferred("request", url, _get_model_discovery_headers(), HTTPClient::METHOD_GET, String());
	return OK;
}
