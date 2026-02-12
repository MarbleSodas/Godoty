# Fix Report: Production Visibility and Configuration

## Problem
The production application was failing silently with a black screen. We suspected two causes:
1.  **Capability Mismatch**: Tauri 2 requires window labels to match capability definitions. The config was missing the `"main"` label.
2.  **Silent JS Crashes**: In production, JS errors are swallowed unless explicitly caught.

## Solutions Applied

### 1. Configuration Fixes
- **Action**: Updated `src-tauri/tauri.conf.json` to explicitly label the main window as `"main"`.
- **Impact**: This ensures the permissions defined in `src-tauri/capabilities/default.json` (which target `"main"`) are correctly applied to the window.

### 2. Setup Robustness
- **Action**: Updated `src-tauri/src/setup.rs` to fail loudly (crash the app with an error) if the Godot documentation directory is missing.
- **Impact**: Prevents the app from running in a broken state if resource copying fails.

### 3. Visual Error Reporting
- **Action**: Injected a global error handler into `packages/app/index.html`.
- **Impact**: Any JavaScript error during startup (e.g., dependency failure, syntax error) will now trigger a **visible red error banner** and an alert dialog, instead of a silent black screen.

### 4. Sidecar Verification
- **Action**: Verified that `opencode-cli-aarch64-apple-darwin` exists in `src-tauri/bin/` with correct permissions.

## Verification
- **Code**: `tauri.conf.json` has `label: "main"`. `index.html` has the error script.
- **Git**: Changes committed.

## Next Steps
- Rebuild the application: `bun run tauri build`
- Run the executable.
- **Expected Outcome**:
    - **Scenario A (Success)**: The app loads normally.
    - **Scenario B (Failure)**: A red error banner appears explaining *exactly* why it crashed (e.g., "ReferenceError: window.__TAURI__ is not defined").
