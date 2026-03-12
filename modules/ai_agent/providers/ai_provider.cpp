/**************************************************************************/
/*  ai_provider.cpp                                                       */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "ai_provider.h"

void AIProvider::_bind_methods() {
	ClassDB::bind_method(D_METHOD("set_api_key", "key"), &AIProvider::set_api_key);
	ClassDB::bind_method(D_METHOD("get_api_key"), &AIProvider::get_api_key);
	ClassDB::bind_method(D_METHOD("set_base_url", "url"), &AIProvider::set_base_url);
	ClassDB::bind_method(D_METHOD("get_base_url"), &AIProvider::get_base_url);
	ClassDB::bind_method(D_METHOD("set_model_name", "name"), &AIProvider::set_model_name);
	ClassDB::bind_method(D_METHOD("get_model_name"), &AIProvider::get_model_name);
	ClassDB::bind_method(D_METHOD("get_is_busy"), &AIProvider::get_is_busy);

	ADD_PROPERTY(PropertyInfo(Variant::STRING, "api_key"), "set_api_key", "get_api_key");
	ADD_PROPERTY(PropertyInfo(Variant::STRING, "base_url"), "set_base_url", "get_base_url");
	ADD_PROPERTY(PropertyInfo(Variant::STRING, "model_name"), "set_model_name", "get_model_name");
	ADD_PROPERTY(PropertyInfo(Variant::BOOL, "is_busy"), "", "get_is_busy");
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

bool AIProvider::get_is_busy() const {
	return is_busy;
}
