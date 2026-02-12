# Fix Report: Production Resource Resolution

## Problem
The production build "worked" but was broken (black screen or missing features) because:
1. Resources like `opencode.json` and Godot docs were missing from the configuration directory.
2. `setup.rs` failed silently (logged a message but continued) when resources were missing.
3. Path resolution for the Godot docs directory failed in the bundle because directories added via glob patterns aren't directly resolvable in Tauri v2 resources.

## Solutions Applied

### 1. Loud Failures
Modified `src-tauri/src/setup.rs` to return `Err` immediately if a resource cannot be found or copied.
- **Impact**: The application will now crash with a visible error during startup if the installation is corrupt, rather than running in a broken zombie state.

### 2. Robust Path Resolution
Updated `copy_godot_docs` to resolve a known file (`@GlobalScope.xml`) instead of the parent directory.
- **Impact**: This correctly locates the physical path of the resources on disk, even inside a macOS App Bundle or Linux AppImage where directory structures are flattened or virtualized.

## Verification
- **Code Review**: `setup.rs` now uses `return Err(...)` for all failure paths.
- **Git**: Changes committed with message `fix(tauri): fail loudly on missing resources and fix glob path resolution`.

## Next Steps
- Rebuild the application: `bun run tauri build`
- Run the executable.
- **Expected Outcome**:
    - If resources are missing: The app will crash immediately (good!).
    - If resources are present: The app will initialize correctly, the sidecar will find its config, and the UI will load.
