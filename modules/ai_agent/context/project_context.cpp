/**************************************************************************/
/*  project_context.cpp                                                   */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "project_context.h"

#include "core/config/project_settings.h"
#include "core/input/input_map.h"
#include "core/os/os.h"
#include "core/string/string_name.h"
#include "core/variant/dictionary.h"
#include "core/variant/typed_array.h"
#include "core/variant/variant.h"

Dictionary ProjectContext::collect() {
	Dictionary context;

	ProjectSettings *ps = ProjectSettings::get_singleton();
	if (!ps) {
		context["error"] = "ProjectSettings not available.";
		return context;
	}

	// Basic project info.
	Dictionary project_info;
	project_info["name"] = ps->get_setting("application/config/name", "");
	project_info["description"] = ps->get_setting("application/config/description", "");
	project_info["version"] = ps->get_setting("application/config/version", "");
	project_info["main_scene"] = ps->get_setting("application/run/main_scene", "");
	project_info["icon"] = ps->get_setting("application/config/icon", "");
	context["project"] = project_info;

	// Rendering settings.
	Dictionary rendering;
	rendering["renderer"] = ps->get_setting("rendering/renderer/rendering_method", "");
	rendering["vsync"] = ps->get_setting("display/window/vsync/vsync_mode", 0);
	rendering["window_width"] = ps->get_setting("display/window/size/viewport_width", 1152);
	rendering["window_height"] = ps->get_setting("display/window/size/viewport_height", 648);
	context["rendering"] = rendering;

	// Input map.
	InputMap *input_map = InputMap::get_singleton();
	if (input_map) {
		Dictionary inputs;
		TypedArray<StringName> actions = input_map->get_actions();
		for (int i = 0; i < actions.size(); i++) {
			StringName action = actions[i];
			// Skip built-in UI actions.
			if (String(action).begins_with("ui_")) {
				continue;
			}
			Array events;
			const List<Ref<InputEvent>> *action_events = input_map->action_get_events(action);
			if (action_events) {
				for (const Ref<InputEvent> &event : *action_events) {
					events.push_back(event->as_text());
				}
			}
			inputs[action] = events;
		}
		context["input_map"] = inputs;
	}

	// Autoloads.
	TypedArray<Dictionary> autoloads;
	List<PropertyInfo> props;
	ps->get_property_list(&props);
	for (const PropertyInfo &pi : props) {
		if (String(pi.name).begins_with("autoload/")) {
			Dictionary al;
			al["name"] = String(pi.name).get_slice("/", 1);
			al["path"] = ps->get_setting(pi.name, "");
			autoloads.push_back(al);
		}
	}
	context["autoloads"] = autoloads;

	// Physics settings.
	Dictionary physics;
	physics["2d_physics_engine"] = ps->get_setting("physics/2d/physics_engine", "");
	physics["3d_physics_engine"] = ps->get_setting("physics/3d/physics_engine", "");
	physics["default_gravity"] = ps->get_setting("physics/2d/default_gravity", 980.0);
	context["physics"] = physics;

	// Display settings.
	Dictionary display;
	display["window_width"] = ps->get_setting("display/window/size/viewport_width", 1152);
	display["window_height"] = ps->get_setting("display/window/size/viewport_height", 648);
	display["fullscreen"] = ps->get_setting("display/window/size/fullscreen", false);
	display["vsync"] = ps->get_setting("display/window/vsync/vsync_mode", 1);
	context["display"] = display;

	return context;
}
