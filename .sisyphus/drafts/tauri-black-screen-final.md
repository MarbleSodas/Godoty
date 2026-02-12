# Draft: Final Debugging of Tauri Production Black Screen

## Context
- **Status**: Production build shows black screen (JS not executing).
- **Hypothesis**:
  1. **Capabilities Mismatch**: Tauri 2 requires explicit permission files in `src-tauri/capabilities/`. If the `default.json` is missing or restrictive, the app won't load.
  2. **Initialization Crash**: The JS bundle crashes before the first render. Since we can't see the console, we need a visible crash reporter (alert).
  3. **Sidecar Interaction**: Even though we made the health check async, if the sidecar *crashes* or *exits* during startup, maybe it affects the Tauri process? (Unlikely for black screen).
  4. **Externalized Dependencies**: Verify if any `@tauri-apps/api` or plugins are being treated as external and missing from the bundle.

## Plan
- **Audit Capabilities**: Check `src-tauri/capabilities/` for any files. Tauri 2 needs these to allow window creation and plugin usage.
- **Visible Crash Reporter**: Inject a script into `index.html` (or `entry.tsx`) that catches all errors and displays them via `alert()`.
- **Plugin Log Verification**: Check if `tauri-plugin-log` is used and if it can write to a file we can inspect.
- **MIME/Protocol Check**: Use a script to verify if assets are actually loaded (e.g., check `window.document.readyState`).
