# Draft: Deep Analysis of Tauri Production Build Failure

## Current Status
- **Dev Mode**: Works fine.
- **Build Mode**: "Doesn't work properly" (previous state was black screen, current state needs verification).
- **Recent Fixes**: Non-blocking sidecar, Tauri 2 CSP updates, Vite target `es2021`, relative paths in `index.html`.

## Potential Root Causes (Post-Ultimate-Fix)
1. **Tauri 2 Capabilities**: If permissions are missing in `src-tauri/capabilities/`, commands will fail in production despite CSP.
2. **Sidecar Pathing**: Production path resolution for the sidecar might be failing if `resolve_resource` logic is flawed.
3. **Environment Variables**: Production `process.env` vs Vite `import.meta.env` discrepancies.
4. **JS Chunk Loading**: If chunks are huge or MIME types are wrong on the protocol.
5. **Rust Panic**: If `setup` fails later or a plugin panics during production initialization.

## Research Plan
- **Explore**: `src-tauri/capabilities/` and `src-tauri/conf.json` for permission sets.
- **Explore**: `src-tauri/src/setup.rs` and `sidecar.rs` for resource resolution logic.
- **Explore**: Frontend for any remaining `localStorage` or `window` dependencies that might be blocked.
- **Librarian**: Tauri 2 "capabilities" migration and common production-only bugs.
