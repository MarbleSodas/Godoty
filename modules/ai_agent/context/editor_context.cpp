/**************************************************************************/
/*  editor_context.cpp                                                    */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#include "editor_context.h"

#ifdef TOOLS_ENABLED
#include "editor/editor_interface.h"
#include "editor/editor_node.h"
#include "editor/editor_undo_redo_manager.h"
#include "editor/inspector/editor_inspector.h"
#include "scene/gui/box_container.h"
#endif

Dictionary EditorContext::collect() {
	Dictionary context;

#ifdef TOOLS_ENABLED
	EditorInterface *ei = EditorInterface::get_singleton();
	if (!ei) {
		context["error"] = "EditorInterface not available.";
		return context;
	}

	// Currently inspected object.
	Object *inspected = ei->get_inspector()->get_edited_object();
	if (inspected) {
		Dictionary inspector;
		inspector["class"] = inspected->get_class();
		Node *node = Object::cast_to<Node>(inspected);
		if (node) {
			inspector["node_path"] = String(node->get_path());
			inspector["node_name"] = node->get_name();
		}
		context["inspector"] = inspector;
	}

	// Editor feature profile / main screen.
	context["current_main_screen"] = ei->get_editor_main_screen()->get_name();

	// Distraction free mode.
	context["distraction_free"] = ei->is_distraction_free_mode_enabled();

	// Recent undo history.
	EditorUndoRedoManager *undo_redo = EditorUndoRedoManager::get_singleton();
	if (undo_redo) {
		Dictionary undo_info;
		undo_info["has_undo"] = undo_redo->has_undo();
		undo_info["has_redo"] = undo_redo->has_redo();
		context["undo_redo"] = undo_info;
	}

	// Editor scale.
	context["editor_scale"] = ei->get_editor_scale();
#else
	context["error"] = "Editor context is only available in editor builds.";
#endif

	return context;
}
