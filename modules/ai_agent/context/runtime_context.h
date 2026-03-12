/**************************************************************************/
/*  runtime_context.h                                                     */
/**************************************************************************/
/*                         This file is part of:                          */
/*                              GODOTY                                    */
/**************************************************************************/

#pragma once

#include "core/variant/dictionary.h"

class RuntimeContext {
public:
	// Collect runtime/debug context — console output, debug state, performance.
	static Dictionary collect();
};
