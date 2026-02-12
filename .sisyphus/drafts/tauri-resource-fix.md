# Draft: Production Resource Integrity Fix

## Context
- **Issue**: Production build fails/malfunctions while dev works.
- **Inference**: Silent failure in resource copying during app setup.
- **Key Findings**:
  1. `setup.rs` silently ignores missing resources.
  2. Resolving directories (like `godot_docs/classes`) fails in production because they are bundled as individual files via globs.
  3. Sidecar crashes if `opencode.json` isn't copied to the config dir.

## Proposed Fixes
1. **Error on Missing Resources**: Update `copy_resource` and `copy_opencode_config` to return an error if the source file is missing.
2. **Fix Glob Resolution**: In `copy_godot_docs`, resolve a specific file (e.g., `classes/Node.xml`) to find the resource directory instead of resolving the directory itself.
3. **Explicit Sidecar Resource**: Add `opencode.json` explicitly to `tauri.conf.json` (it's already there, but we should verify).
4. **App Setup Error Handling**: Ensure the `setup` closure in `lib.rs` returns an error that halts the app with a visible message if initialization fails.

## Verification
- Run build and inspect `config_dir` (e.g. `~/Library/Application Support/com.godoty.app`) to see if files are actually copied.
