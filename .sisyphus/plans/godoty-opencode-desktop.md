# Godoty - OpenCode Desktop Clone

## TL;DR

> **Quick Summary**: Build "Godoty" - a Tauri 2 desktop app that clones OpenCode's architecture with @opencode-ai/app UI, bundled opencode-cli sidecar, and pre-configured oh-my-opencode + opencode-antigravity-auth plugins at @latest. Replace the existing Godoty codebase entirely.
> 
> **Deliverables**:
> - Complete Tauri 2 + SolidJS desktop application
> - Bundled opencode-cli sidecar (multi-platform)
> - Pre-configured plugins (oh-my-opencode, opencode-antigravity-auth)
> - Isolated config at ~/.config/godoty/
> - Auto-updater via GitHub releases
> - Multi-platform builds (macOS, Windows, Linux)
> 
> **Estimated Effort**: Large (8-12 development days)
> **Parallel Execution**: YES - 3 waves
> **Critical Path**: Task 1 (Cleanup) -> Task 2 (Scaffold) -> Task 4 (Sidecar) -> Task 7 (Plugin Config) -> Task 9 (Build CI)

---

## Context

### Original Request
Build a Tauri application called Godoty which clones the OpenCode desktop implementation, automatically loading oh-my-opencode and opencode-antigravity-auth plugins with @latest versioning so plugins and OpenCode are always at the latest version.

### Interview Summary
**Key Discussions**:
- **Architecture**: Embed @opencode-ai/app UI + bundle opencode-cli as sidecar (not in-process embedding)
- **Frontend**: SolidJS + Kobalte + Tailwind (matching OpenCode exactly)
- **Plugins**: oh-my-opencode@latest and opencode-antigravity-auth@latest in bundled opencode.json
- **Config Isolation**: Use ~/.config/godoty/ to avoid conflicts with regular OpenCode
- **Auth Flow**: OAuth handling within the app (like OpenCode does)
- **Godot Integration**: Remove entirely - this becomes a pure OpenCode clone
- **Existing Code**: Replace all of it (Vue frontend, Python brain, Godot plugin)

**Research Findings**:
- OpenCode desktop uses Tauri 2 + SolidJS with @opencode-ai/app and @opencode-ai/ui packages
- The CLI sidecar handles LLM orchestration; @opencode-ai/app is the frontend only
- oh-my-opencode provides multi-agent orchestration (Sisyphus, Planner, Observer, Ralph Loop)
- opencode-antigravity-auth requires disabling built-in google_auth to avoid conflicts
- Plugins auto-install at @latest on startup via bun

### Metis Review
**Identified Gaps** (addressed):
- Sidecar misunderstanding: Clarified - bundling opencode-cli, not embedding logic
- Auth flow: Will use OpenCode's native OAuth flow in app
- Config conflict: Isolated to ~/.config/godoty/
- Plugin conflicts: Will disable built-in google_auth in config
- Windows sidecar updates: Will implement kill logic before updates

---

## Work Objectives

### Core Objective
Clone the OpenCode desktop application architecture with custom branding ("Godoty"), pre-configured plugins, and isolated configuration, replacing the existing Godoty codebase entirely.

### Concrete Deliverables
- `/src-tauri/` - Tauri 2 Rust backend with sidecar management
- `/src/` - SolidJS frontend using @opencode-ai/app and @opencode-ai/ui
- `/sidecars/` - Platform-specific opencode-cli binaries
- `/resources/opencode.json` - Default config with pre-loaded plugins
- `/.github/workflows/` - CI/CD for multi-platform builds and releases
- Test suites (Vitest unit, Playwright e2e)

### Definition of Done
- [ ] `bun run tauri dev` launches the app successfully
- [ ] Sidecar health check returns OK: `curl http://localhost:${PORT}/health`
- [ ] Both plugins appear in loaded plugins list
- [ ] Auth flow completes via OAuth in app (not terminal)
- [ ] Config stored in ~/.config/godoty/ (not ~/.config/opencode/)
- [ ] GitHub releases produce .dmg, .msi, .AppImage
- [ ] Auto-updater downloads and installs update

### Must Have
- Bundled opencode-cli sidecar for all platforms
- Pre-configured oh-my-opencode@latest and opencode-antigravity-auth@latest
- Isolated config directory
- GitHub releases auto-update
- OAuth flow in app

### Must NOT Have (Guardrails)
- NO: Port any Python brain code (complete replacement)
- NO: Maintain backward compatibility with existing Godoty protocol
- NO: Build custom LLM orchestration (use OpenCode's via sidecar)
- NO: Implement custom plugin loading (use OpenCode's native system)
- NO: Fork @opencode-ai/* packages (use as npm dependencies)
- NO: Supabase integration
- NO: Godot Editor integration
- NO: Custom theming (use OpenCode default)

---

## Verification Strategy (MANDATORY)

### Test Decision
- **Infrastructure exists**: NO (starting fresh)
- **User wants tests**: TDD (tests first)
- **Framework**: Vitest (unit) + Playwright (e2e)

### Test Infrastructure Setup (Task 3)

Before any implementation, set up:
```bash
# Unit tests
bun add -d vitest @testing-library/jest-dom

# E2E tests  
bun add -d @playwright/test
bunx playwright install
```

**TDD Workflow for Each Task:**
1. **RED**: Write failing test for the feature
2. **GREEN**: Implement minimum code to pass
3. **REFACTOR**: Clean up while keeping tests green

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately):
├── Task 1: Clean up existing codebase
├── Task 2: Scaffold Tauri 2 + SolidJS project
└── Task 3: Setup test infrastructure

Wave 2 (After Wave 1):
├── Task 4: Integrate sidecar management
├── Task 5: Integrate @opencode-ai/app UI
└── Task 6: Configure isolated config path

Wave 3 (After Wave 2):
├── Task 7: Bundle plugin configuration
├── Task 8: Implement auto-updater
└── Task 9: Setup CI/CD for multi-platform builds

Wave 4 (After Wave 3):
└── Task 10: E2E testing and polish

Critical Path: Task 1 → Task 2 → Task 4 → Task 7 → Task 9
Parallel Speedup: ~35% faster than sequential
```

### Dependency Matrix

| Task | Depends On | Blocks | Can Parallelize With |
|------|------------|--------|---------------------|
| 1 | None | 2, 3 | None |
| 2 | 1 | 4, 5, 6 | 3 |
| 3 | 1 | 10 | 2 |
| 4 | 2 | 7, 8 | 5, 6 |
| 5 | 2 | 10 | 4, 6 |
| 6 | 2 | 7, 8 | 4, 5 |
| 7 | 4, 6 | 10 | 8 |
| 8 | 4, 6 | 10 | 7 |
| 9 | 4 | 10 | 7, 8 |
| 10 | 3, 5, 7, 8, 9 | None | None (final) |

### Agent Dispatch Summary

| Wave | Tasks | Recommended Dispatch |
|------|-------|---------------------|
| 1 | 1, 2, 3 | Run Task 1 first (blocks), then 2+3 in parallel |
| 2 | 4, 5, 6 | All three in parallel after Wave 1 |
| 3 | 7, 8, 9 | All three in parallel after Wave 2 |
| 4 | 10 | Sequential final integration |

---

## TODOs

### Task 1: Clean Up Existing Codebase

- [x] **1. Remove existing Godoty code and prepare fresh project structure**

  **What to do**:
  - Archive or delete all existing directories: `brain/`, `desktop/src/`, `godot/`, `scripts/`
  - Keep only: `.git/`, `.gitignore`, `README.md`, `LICENSE`, `.sisyphus/`
  - Remove all Python, Vue, and Godot-related configuration files
  - Update .gitignore for new Tauri + SolidJS + Bun stack

  **Must NOT do**:
  - Delete .git history (preserve commit history)
  - Delete .sisyphus/ (contains this plan)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: File deletion and cleanup is straightforward, low complexity
  - **Skills**: [`git-master`]
    - `git-master`: Need to preserve git history while removing files

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 1 (sequential first)
  - **Blocks**: Tasks 2, 3
  - **Blocked By**: None (can start immediately)

  **References**:
  - `desktop/` - Vue frontend to remove
  - `brain/` - Python sidecar to remove
  - `godot/` - Godot plugin to remove
  - `scripts/` - Build scripts to remove

  **Acceptance Criteria**:
  ```bash
  # Verify directories removed
  ls -la | grep -E "(brain|godot|scripts)"
  # Assert: No output (directories don't exist)
  
  # Verify desktop/src removed (but src-tauri structure can remain as reference)
  ls desktop/src 2>/dev/null
  # Assert: "No such file or directory"
  
  # Verify git history preserved
  git log --oneline | head -5
  # Assert: Shows recent commits
  ```

  **Commit**: YES
  - Message: `chore: remove existing Godoty codebase for OpenCode clone rebuild`
  - Files: `brain/`, `desktop/src/`, `godot/`, `scripts/`
  - Pre-commit: None (no tests yet)

---

### Task 2: Scaffold Tauri 2 + SolidJS Project

- [x] **2. Initialize new Tauri 2 + SolidJS project structure**

  **What to do**:
  - Initialize Tauri 2 project with SolidJS template: `bunx create-tauri-app --template solidjs-ts`
  - Configure package.json with @opencode-ai/app and @opencode-ai/ui dependencies
  - Setup Tailwind CSS matching OpenCode's configuration
  - Configure Tauri identifier as `com.godoty.app`
  - Setup project structure mirroring OpenCode desktop

  **Must NOT do**:
  - Use React or Vue (must be SolidJS)
  - Fork @opencode-ai/* packages (use as npm dependencies)
  - Configure plugins yet (that's Task 7)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Project scaffolding requires careful configuration and verification
  - **Skills**: [`frontend-ui-ux`]
    - `frontend-ui-ux`: SolidJS and Tailwind configuration

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 3)
  - **Blocks**: Tasks 4, 5, 6
  - **Blocked By**: Task 1

  **References**:
  - External: https://v2.tauri.app/start/create-project/ - Tauri 2 project creation
  - External: https://github.com/anomalyco/opencode/tree/dev/packages/desktop - OpenCode desktop structure reference
  - External: https://github.com/anomalyco/opencode/blob/dev/packages/desktop/package.json - OpenCode dependencies

  **Acceptance Criteria**:
  ```bash
  # Project structure exists
  ls src-tauri/Cargo.toml src/App.tsx package.json
  # Assert: All files exist
  
  # Dependencies installed
  bun pm ls | grep -E "@opencode-ai/(app|ui)"
  # Assert: Both packages listed
  
  # Tailwind configured
  grep -l "tailwindcss" package.json
  # Assert: Found
  
  # Tauri identifier set
  grep "com.godoty.app" src-tauri/tauri.conf.json
  # Assert: Found
  
  # Dev server starts (basic smoke test)
  timeout 30 bun run tauri dev &
  sleep 15 && curl -s http://localhost:1420 | head -1
  # Assert: Returns HTML content
  ```

  **Commit**: YES
  - Message: `feat: scaffold Tauri 2 + SolidJS project with OpenCode dependencies`
  - Files: `src/`, `src-tauri/`, `package.json`, `tailwind.config.js`, etc.
  - Pre-commit: `bun run build` (verify compiles)

---

### Task 3: Setup Test Infrastructure

- [x] **3. Configure Vitest and Playwright for TDD workflow**

  **What to do**:
  - Install Vitest and configure for SolidJS component testing
  - Install Playwright and configure for Tauri e2e testing
  - Create test directories: `src/__tests__/`, `e2e/`
  - Write example unit test and e2e test to verify setup
  - Add test scripts to package.json

  **Must NOT do**:
  - Write actual feature tests (those come with each task)
  - Configure coverage thresholds yet

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Test tooling setup is well-documented, straightforward
  - **Skills**: []
    - No special skills needed for test config

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 2)
  - **Blocks**: Task 10
  - **Blocked By**: Task 1

  **References**:
  - External: https://vitest.dev/guide/ - Vitest setup
  - External: https://playwright.dev/docs/intro - Playwright setup
  - External: https://v2.tauri.app/develop/tests/ - Tauri testing guide

  **Acceptance Criteria**:
  ```bash
  # Vitest configured
  bun run test -- --run
  # Assert: "1 passed" (example test passes)
  
  # Playwright configured
  bunx playwright test --list
  # Assert: Shows test files
  
  # Test directories exist
  ls src/__tests__/ e2e/
  # Assert: Directories exist
  ```

  **Commit**: YES
  - Message: `test: setup Vitest and Playwright test infrastructure`
  - Files: `vitest.config.ts`, `playwright.config.ts`, `src/__tests__/`, `e2e/`
  - Pre-commit: `bun run test`

---

### Task 4: Integrate Sidecar Management

- [x] **4. Bundle and manage opencode-cli sidecar with lifecycle controls**

  **What to do**:
  - Create sidecar download/bundle script for multi-platform binaries
  - Configure `externalBin` in tauri.conf.json for sidecar
  - Implement Rust sidecar manager in src-tauri/src/sidecar.rs
  - Add health check endpoint polling
  - Implement graceful shutdown (especially for Windows file locking)
  - Configure capabilities for shell:allow-execute

  **Must NOT do**:
  - Build custom LLM orchestration (use OpenCode's)
  - Hardcode sidecar paths (use Tauri's resource resolver)

  **Recommended Agent Profile**:
  - **Category**: `ultrabrain`
    - Reason: Sidecar lifecycle management is complex, especially cross-platform
  - **Skills**: []
    - No special skills, but requires Rust knowledge

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 5, 6)
  - **Blocks**: Tasks 7, 8, 9
  - **Blocked By**: Task 2

  **References**:
  - External: https://v2.tauri.app/develop/sidecar/ - Tauri sidecar documentation
  - External: https://github.com/anomalyco/opencode/blob/dev/packages/desktop/src-tauri/src/main.rs - OpenCode sidecar pattern
  - `desktop/src-tauri/src/sidecar.rs` (old, for reference patterns only)

  **Acceptance Criteria**:
  ```bash
  # TDD: Write test first
  bun run test src/__tests__/sidecar.test.ts
  # Assert: Initially FAILS (RED)
  
  # After implementation:
  # Sidecar binary exists for current platform
  ls src-tauri/sidecars/opencode-*
  # Assert: Platform-specific binary exists
  
  # Tauri config has sidecar
  grep -A 5 "externalBin" src-tauri/tauri.conf.json
  # Assert: Shows sidecar path
  
  # Capabilities allow execution
  grep "shell:allow-execute" src-tauri/capabilities/*.json
  # Assert: Found
  
  # Health check works (requires app running)
  # Will be verified in e2e tests
  ```

  **Commit**: YES
  - Message: `feat: integrate opencode-cli sidecar with lifecycle management`
  - Files: `src-tauri/src/sidecar.rs`, `src-tauri/tauri.conf.json`, `src-tauri/capabilities/`
  - Pre-commit: `cargo build --manifest-path src-tauri/Cargo.toml`

---

### Task 5: Integrate @opencode-ai/app UI

- [x] **5. Wire up @opencode-ai/app SolidJS components as the main interface**

  **What to do**:
  - Import and render @opencode-ai/app main component
  - Configure SolidJS router for app navigation
  - Wire up Tauri IPC to OpenCode app context
  - Apply OpenCode's default theme via @opencode-ai/ui
  - Connect frontend to sidecar WebSocket endpoint

  **Must NOT do**:
  - Custom theming (use OpenCode default)
  - Modify @opencode-ai/app source (use as-is)
  - Implement Godot-specific features

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: Frontend integration with SolidJS components
  - **Skills**: [`frontend-ui-ux`]
    - `frontend-ui-ux`: SolidJS and UI component integration

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 6)
  - **Blocks**: Task 10
  - **Blocked By**: Task 2

  **References**:
  - External: https://github.com/anomalyco/opencode/tree/dev/packages/app - OpenCode app package
  - External: https://github.com/anomalyco/opencode/tree/dev/packages/ui - OpenCode UI package
  - External: https://github.com/anomalyco/opencode/blob/dev/packages/desktop/src/main.tsx - OpenCode desktop entry

  **Acceptance Criteria**:
  **TDD (RED first):**
  ```typescript
  // src/__tests__/App.test.tsx
  test('renders main chat interface', async () => {
    render(() => <App />);
    expect(screen.getByTestId('chat-input')).toBeInTheDocument();
  });
  // Assert: Initially FAILS
  ```

  **After implementation:**
  ```bash
  # Unit tests pass
  bun run test src/__tests__/App.test.tsx
  # Assert: PASS
  
  # App compiles
  bun run build
  # Assert: Exit code 0
  ```

  **Playwright verification:**
  ```typescript
  // e2e/app.spec.ts
  test('main window opens with chat interface', async ({ page }) => {
    await expect(page.locator('[data-testid="chat-input"]')).toBeVisible();
    await expect(page.locator('[data-testid="message-list"]')).toBeVisible();
  });
  ```

  **Commit**: YES
  - Message: `feat: integrate @opencode-ai/app UI components`
  - Files: `src/App.tsx`, `src/main.tsx`, `src/routes/`
  - Pre-commit: `bun run test && bun run build`

---

### Task 6: Configure Isolated Config Path

- [x] **6. Set up ~/.config/godoty/ as the isolated configuration directory**

  **What to do**:
  - Configure OpenCode to use ~/.config/godoty/ instead of ~/.config/opencode/
  - Set XDG_CONFIG_HOME override for the app process
  - Create initial config structure on first launch
  - Ensure config path works on all platforms (macOS, Windows, Linux)

  **Must NOT do**:
  - Use ~/.config/opencode/ (conflicts with regular OpenCode)
  - Hardcode paths (use platform-appropriate methods)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Config path redirection is straightforward
  - **Skills**: []
    - No special skills needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 5)
  - **Blocks**: Tasks 7, 8
  - **Blocked By**: Task 2

  **References**:
  - External: https://crates.io/crates/dirs - Rust dirs crate for platform paths
  - External: https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/app/app.ts - OpenCode config handling

  **Acceptance Criteria**:
  ```bash
  # TDD: Write test first for config path resolution
  bun run test src/__tests__/config.test.ts
  # Assert: Initially FAILS
  
  # After implementation:
  # Config directory created on launch
  ls -la ~/.config/godoty/
  # Assert: Directory exists with opencode.json
  
  # NOT using opencode path
  cat ~/.config/godoty/opencode.json | head -5
  # Assert: Shows Godoty-specific config
  ```

  **Commit**: YES
  - Message: `feat: configure isolated config path at ~/.config/godoty/`
  - Files: `src-tauri/src/config.rs`, `src/lib/config.ts`
  - Pre-commit: `bun run test`

---

### Task 7: Bundle Plugin Configuration

- [x] **7. Pre-configure oh-my-opencode and opencode-antigravity-auth plugins**

  **What to do**:
  - Create default opencode.json with both plugins at @latest
  - Bundle as Tauri resource at resources/opencode.json
  - Copy to ~/.config/godoty/ on first launch if not exists
  - Configure antigravity.json with google_auth disabled (avoid conflicts)
  - Ensure plugin config is user-editable post-install

  **Must NOT do**:
  - Hardcode plugin versions (use @latest)
  - Prevent users from modifying config
  - Add plugins beyond the two specified

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Config file creation is straightforward
  - **Skills**: []
    - No special skills needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 8, 9)
  - **Blocks**: Task 10
  - **Blocked By**: Tasks 4, 6

  **References**:
  - External: https://opencode.ai/docs/plugins/ - OpenCode plugin documentation
  - External: https://github.com/NoeFabris/opencode-antigravity-auth#readme - Antigravity auth setup
  - External: https://github.com/code-yeongyu/oh-my-opencode - oh-my-opencode setup

  **Acceptance Criteria**:
  ```bash
  # Resource file bundled
  cat src-tauri/resources/opencode.json | jq '.plugin'
  # Assert: ["oh-my-opencode@latest", "opencode-antigravity-auth@latest"]
  
  # After first launch, config copied to user dir
  cat ~/.config/godoty/opencode.json | jq '.plugin'
  # Assert: Same plugin array
  
  # Antigravity config disables built-in auth
  cat ~/.config/godoty/antigravity.json | jq '.disable_builtin_auth'
  # Assert: true (or equivalent config)
  ```

  **Commit**: YES
  - Message: `feat: bundle pre-configured plugin settings for oh-my-opencode and antigravity-auth`
  - Files: `src-tauri/resources/opencode.json`, `src-tauri/resources/antigravity.json`
  - Pre-commit: `jq . src-tauri/resources/opencode.json` (validate JSON)

---

### Task 8: Implement Auto-Updater

- [x] **8. Configure tauri-plugin-updater with GitHub releases**

  **What to do**:
  - Add tauri-plugin-updater to Cargo.toml and initialize in main.rs
  - Configure update endpoint pointing to GitHub releases
  - Implement update check on app startup
  - Add update notification UI component
  - Handle Windows sidecar kill before update (file locking)
  - Generate update manifest (latest.json) in release workflow

  **Must NOT do**:
  - Force updates without user consent
  - Skip sidecar shutdown on Windows

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Auto-updater requires careful cross-platform handling
  - **Skills**: []
    - No special skills needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 7, 9)
  - **Blocks**: Task 10
  - **Blocked By**: Tasks 4, 6

  **References**:
  - External: https://v2.tauri.app/plugin/updater/ - Tauri updater plugin
  - External: https://github.com/anomalyco/opencode/blob/dev/packages/desktop/src-tauri/Cargo.toml - OpenCode updater config

  **Acceptance Criteria**:
  ```bash
  # Updater plugin in Cargo.toml
  grep "tauri-plugin-updater" src-tauri/Cargo.toml
  # Assert: Found
  
  # Updater initialized in main.rs
  grep "tauri_plugin_updater" src-tauri/src/main.rs
  # Assert: Found
  
  # Update endpoint configured in tauri.conf.json
  grep -A 3 "updater" src-tauri/tauri.conf.json
  # Assert: Shows GitHub releases URL
  ```

  **E2E Verification (mock):**
  ```typescript
  test('shows update notification when available', async ({ page }) => {
    // Mock GitHub releases to return newer version
    await page.route('**/latest.json', route => route.fulfill({
      body: JSON.stringify({ version: '999.0.0' })
    }));
    await page.reload();
    await expect(page.locator('[data-testid="update-banner"]')).toBeVisible();
  });
  ```

  **Commit**: YES
  - Message: `feat: implement auto-updater with GitHub releases`
  - Files: `src-tauri/Cargo.toml`, `src-tauri/src/main.rs`, `src-tauri/tauri.conf.json`, `src/components/UpdateBanner.tsx`
  - Pre-commit: `cargo build --manifest-path src-tauri/Cargo.toml`

---

### Task 9: Setup CI/CD for Multi-Platform Builds

- [x] **9. Configure GitHub Actions for macOS, Windows, and Linux builds with releases**

  **What to do**:
  - Create `.github/workflows/release.yml` for tagged releases
  - Configure build matrix: macOS (x64, arm64), Windows (x64), Linux (x64)
  - Generate signed installers (.dmg, .msi, .AppImage, .deb)
  - Generate latest.json manifest for auto-updater
  - Upload artifacts to GitHub releases
  - Setup code signing (optional, can be deferred)

  **Must NOT do**:
  - Build on every push (only on tags/releases)
  - Skip any of the three platforms

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: CI/CD with multi-platform builds is complex
  - **Skills**: [`git-master`]
    - `git-master`: GitHub Actions and release workflows

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 7, 8)
  - **Blocks**: Task 10
  - **Blocked By**: Task 4

  **References**:
  - External: https://v2.tauri.app/distribute/ci/ - Tauri CI guide
  - External: https://github.com/tauri-apps/tauri-action - Tauri GitHub Action
  - External: https://github.com/anomalyco/opencode/blob/dev/.github/workflows/ - OpenCode CI reference

  **Acceptance Criteria**:
  ```bash
  # Workflow file exists
  cat .github/workflows/release.yml | head -20
  # Assert: Shows workflow with Tauri build steps
  
  # Build matrix includes all platforms
  grep -A 10 "matrix:" .github/workflows/release.yml
  # Assert: Contains macos, windows, ubuntu
  
  # Sidecar binaries for all platforms
  grep -A 5 "externalBin" src-tauri/tauri.conf.json
  # Assert: Contains platform-agnostic path
  ```

  **Commit**: YES
  - Message: `ci: setup multi-platform release workflow with GitHub Actions`
  - Files: `.github/workflows/release.yml`
  - Pre-commit: `yamllint .github/workflows/release.yml` (if available)

---

### Task 10: E2E Testing and Polish

- [ ] **10. Comprehensive end-to-end testing and final integration verification**

  **What to do**:
  - Write Playwright e2e tests for complete user flows
  - Test sidecar startup and health
  - Test plugin loading verification
  - Test auth flow (OAuth in app)
  - Test config isolation
  - Test update notification
  - Fix any integration issues discovered

  **Must NOT do**:
  - Add new features (this is verification only)
  - Skip any major user flow

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Comprehensive testing requires attention to detail
  - **Skills**: [`playwright`]
    - `playwright`: E2E browser automation for desktop app

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (sequential, final)
  - **Blocks**: None (final task)
  - **Blocked By**: Tasks 3, 5, 7, 8, 9

  **References**:
  - `e2e/` - Test directory from Task 3
  - External: https://playwright.dev/docs/api/class-electron - Playwright Electron support (similar to Tauri)

  **Acceptance Criteria**:
  
  **Playwright E2E Tests:**
  ```typescript
  // e2e/full-flow.spec.ts
  
  test('app launches and sidecar starts', async ({ page }) => {
    // App window visible
    await expect(page.locator('[data-testid="main-window"]')).toBeVisible();
    
    // Sidecar healthy (check status indicator)
    await expect(page.locator('[data-testid="sidecar-status"]')).toHaveText('connected');
  });
  
  test('plugins are loaded', async ({ page }) => {
    // Navigate to settings/plugins
    await page.click('[data-testid="settings-button"]');
    await page.click('[data-testid="plugins-tab"]');
    
    // Both plugins visible
    await expect(page.locator('text=oh-my-opencode')).toBeVisible();
    await expect(page.locator('text=opencode-antigravity-auth')).toBeVisible();
  });
  
  test('config uses isolated path', async () => {
    // Verify via filesystem
    const configPath = path.join(os.homedir(), '.config', 'godoty', 'opencode.json');
    expect(fs.existsSync(configPath)).toBe(true);
    
    const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
    expect(config.plugin).toContain('oh-my-opencode@latest');
  });
  ```
  
  ```bash
  # All e2e tests pass
  bunx playwright test
  # Assert: All tests pass
  
  # Build succeeds for release
  bun run tauri build
  # Assert: Exit code 0, produces installer
  ```

  **Commit**: YES
  - Message: `test: add comprehensive e2e tests for all major user flows`
  - Files: `e2e/*.spec.ts`
  - Pre-commit: `bunx playwright test`

---

## Commit Strategy

| After Task | Message | Files | Verification |
|------------|---------|-------|--------------|
| 1 | `chore: remove existing Godoty codebase for OpenCode clone rebuild` | brain/, desktop/src/, godot/, scripts/ | git status |
| 2 | `feat: scaffold Tauri 2 + SolidJS project with OpenCode dependencies` | src/, src-tauri/, package.json | bun run build |
| 3 | `test: setup Vitest and Playwright test infrastructure` | vitest.config.ts, playwright.config.ts | bun run test |
| 4 | `feat: integrate opencode-cli sidecar with lifecycle management` | src-tauri/src/sidecar.rs | cargo build |
| 5 | `feat: integrate @opencode-ai/app UI components` | src/App.tsx, src/routes/ | bun run build |
| 6 | `feat: configure isolated config path at ~/.config/godoty/` | src-tauri/src/config.rs | bun run test |
| 7 | `feat: bundle pre-configured plugin settings` | src-tauri/resources/ | jq . resources/opencode.json |
| 8 | `feat: implement auto-updater with GitHub releases` | src-tauri/Cargo.toml, tauri.conf.json | cargo build |
| 9 | `ci: setup multi-platform release workflow` | .github/workflows/release.yml | yamllint |
| 10 | `test: add comprehensive e2e tests` | e2e/*.spec.ts | bunx playwright test |

---

## Success Criteria

### Verification Commands
```bash
# App builds successfully
bun run tauri build
# Expected: Exit code 0, creates installer in target/release/bundle/

# All unit tests pass
bun run test
# Expected: All tests pass

# All e2e tests pass  
bunx playwright test
# Expected: All tests pass

# Sidecar health check
curl http://localhost:${SIDECAR_PORT}/health
# Expected: {"status": "ok"} or equivalent

# Config in correct location
cat ~/.config/godoty/opencode.json | jq '.plugin'
# Expected: ["oh-my-opencode@latest", "opencode-antigravity-auth@latest"]

# Installer exists for current platform
ls -la src-tauri/target/release/bundle/
# Expected: Platform-appropriate installer (.dmg, .msi, or .AppImage)
```

### Final Checklist
- [ ] App launches on macOS, Windows, Linux
- [ ] Sidecar starts and passes health check
- [ ] Both plugins appear as loaded
- [ ] Config stored in ~/.config/godoty/ (not ~/.config/opencode/)
- [ ] OAuth flow works in-app (not terminal)
- [ ] Auto-updater detects new versions
- [ ] All tests pass (unit + e2e)
- [ ] No Godot-related code remains
- [ ] No Python/brain code remains
