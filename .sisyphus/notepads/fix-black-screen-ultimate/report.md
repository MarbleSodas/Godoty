# Fix Report: Ultimate Black Screen Fix

## Problem
The production build was showing a black screen due to three critical issues:
1. **Startup Block**: The Rust backend blocked the main thread for 30 seconds waiting for the sidecar, preventing the window from showing.
2. **CSP Violation**: The `ipc:` protocol was blocked, preventing Tauri plugins from working.
3. **JS Crash**: `esnext` build target caused silent crashes on some webviews.

## Solutions Applied

### 1. Unblocked Main Thread
In `src-tauri/src/sidecar.rs`, we wrapped the `wait_for_healthy` call in an async task:
```rust
tauri::async_runtime::spawn(async move {
    Self::wait_for_healthy(&port_clone);
});
```
This allows the `setup` hook to return immediately, so the window can render while the backend initializes in the background.

### 2. Updated Content Security Policy
In `src-tauri/tauri.conf.json`, we added the required Tauri 2 protocols:
```json
"connect-src": "'self' ... ipc: http://ipc.localhost tauri://localhost"
```
This ensures internal Tauri messages (for window management, shell, etc.) are allowed.

### 3. Improved JS Compatibility
In `packages/app/vite.config.ts`, we downgraded the target:
```typescript
target: "es2021"
```
This ensures the JS bundle is compatible with a wider range of WebView versions.

### 4. Added Startup Error Logging
In `packages/app/src/entry.tsx`, we wrapped the main render in a `try-catch` to log any remaining startup errors to the console.

## Verification
- **Code Review**: All changes verified against the plan.
- **Git**: Changes committed with message `fix(tauri): unblock main thread, update CSP, and compat build`.

## Next Steps
- Rebuild the application: `bun run tauri build`
- Run the executable.
- **Expected Outcome**: The app window should appear immediately. It may show "Loading App..." briefly while the sidecar starts, then load the full UI.
