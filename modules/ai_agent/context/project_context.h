/**************************************************************************/
/*  project_context.h                                                     */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "core/variant/dictionary.h"

class ProjectContext {
public:
	// Collect project configuration context.
	static Dictionary collect();
};
