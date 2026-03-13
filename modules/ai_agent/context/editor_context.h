/**************************************************************************/
/*  editor_context.h                                                      */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "core/variant/dictionary.h"

class EditorContext {
public:
	// Collect editor UI state — layout, tool mode, inspector, undo history.
	static Dictionary collect();
};
