# Plan: Automate Tauri Sidecar Setup

## TL;DR

> **Quick Summary**: Create a `scripts/setup-sidecar.ts` script to automatically download the `opencode-cli` binary from GitHub Releases (v3.3.1) based on the user's platform, and hook it into the build process.
> 
> **Deliverables**:
> - `scripts/setup-sidecar.ts` (Download logic)
> - `package.json` updates (Scripts & Hooks)
> - `.gitignore` updates (Ignore downloaded binaries)
> - Git cleanup (Remove committed binaries)
> 
> **Estimated Effort**: Short (15-20 mins)
> **Parallel Execution**: Sequential

---

## Context

### Original Request
User encountered a `tauri dev` error: `resource path opencode-cli-x86_64-pc-windows-msvc.exe doesn't exist`. The sidecar binary is missing or not found.

### Selected Solution
**"Clean Solution"**: Instead of checking large binaries into git, we will automate their download.
- **Source**: `https://github.com/code-yeongyu/oh-my-opencode/releases/tag/v3.3.1`
- **Mechanism**: A TypeScript script running via `bun` to fetch the platform-specific binary and place it in `src-tauri/binaries/` with the correct Tauri target-triple name.

---

## Work Objectives

### Core Objective
Ensure `tauri dev` works by guaranteeing the presence of the correct `opencode-cli` sidecar binary for the current platform.

### Concrete Deliverables
- `scripts/setup-sidecar.ts`: Script to download `opencode-cli` v3.3.1.
- Updated `package.json`: Hook to run setup before dev/build.
- Updated `.gitignore`: Exclude `src-tauri/binaries/`.

### Must Have
- Support for Windows (`x86_64-pc-windows-msvc`), Linux (`x86_64-unknown-linux-gnu`), and macOS (`x86_64-apple-darwin`, `aarch64-apple-darwin`).
- **chmod +x** execution permissions on Unix-like systems.
- Robust error handling (fail if download fails).

### Must NOT Have
- Binaries committed to the repository (except `.gitkeep` if needed, but preferably ignored).

---

## Verification Strategy

> **UNIVERSAL RULE: ZERO HUMAN INTERVENTION**
> ALL tasks must be verified by the agent using tools (bash/bun).

### Agent-Executed QA Scenarios

**Scenario 1: Script Downloads Correct Binary**
- **Tool**: Bash
- **Steps**:
  1. `rm -rf src-tauri/binaries/opencode-cli*` (Clean state)
  2. `bun run scripts/setup-sidecar.ts`
  3. `ls src-tauri/binaries/opencode-cli-*` (Assert file exists)
  4. (If Linux/Mac) `test -x src-tauri/binaries/opencode-cli-*` (Assert executable)

**Scenario 2: Build Process Triggers Download**
- **Tool**: Bash
- **Steps**:
  1. `rm -rf src-tauri/binaries/opencode-cli*`
  2. `bun run dev --help` (Or dry-run of the dev command chain if possible, otherwise rely on manual verification of the hook logic via `cat package.json`)
  3. *Verification*: Check if `predev` or `prepare` script is correctly configured in `package.json`.

---

## TODOs

- [ ] 1. Create Download Script (`scripts/setup-sidecar.ts`)

  **What to do**:
  - Implement platform detection (node's `process.platform`, `process.arch`).
  - Map to Rust target triples:
    - `win32` + `x64` → `x86_64-pc-windows-msvc` (append `.exe`)
    - `linux` + `x64` → `x86_64-unknown-linux-gnu`
    - `darwin` + `x64` → `x86_64-apple-darwin`
    - `darwin` + `arm64` → `aarch64-apple-darwin`
  - Construct URL: `https://github.com/code-yeongyu/oh-my-opencode/releases/download/v3.3.1/opencode-cli-<target-triple>`
    - *Note*: GitHub Releases usually don't have the target triple in the filename if it's a single binary per asset, but often they do. 
    - **CRITICAL**: Check the actual asset names on the release page first.
    - *Assumption*: Assets are named `opencode-cli-<target-triple>` (or similar). If they are just `opencode-cli`, rename them after download.
  - Download using `fetch` and write to `src-tauri/binaries/`.
  - Apply `chmod +x` if not Windows.

  **Recommended Agent**: `quick` (Node.js/TS scripting)

  **Acceptance Criteria**:
  - [ ] Script runs without error on the current environment.
  - [ ] Binary appears in `src-tauri/binaries/`.
  - [ ] Binary has correct extension (`.exe` on Windows).

- [ ] 2. Clean Git & Update Ignore

  **What to do**:
  - `git rm -r --cached src-tauri/binaries/` (Remove from tracking but keep local for safety until script works).
  - Add `src-tauri/binaries/` to `.gitignore`.
  - Add `!src-tauri/binaries/.gitkeep` if we want to keep the folder structure (optional).

  **Recommended Agent**: `quick` (Git operations)

  **Acceptance Criteria**:
  - [ ] `git status` shows deleted files in `src-tauri/binaries/`.
  - [ ] `.gitignore` contains `src-tauri/binaries/`.

- [ ] 3. Update package.json Hooks

  **What to do**:
  - Add `"setup:sidecar": "bun run scripts/setup-sidecar.ts"` to `scripts`.
  - Add `"predev": "bun run setup:sidecar"` (or add to `prepare` if it should run on install).
  - *Recommendation*: Use `prepare` so it runs on `npm install`, ensuring binaries are there before any dev/build command.

  **Recommended Agent**: `quick` (JSON editing)

  **Acceptance Criteria**:
  - [ ] `package.json` contains `setup:sidecar` script.
  - [ ] `package.json` contains `prepare` (or `predev`) hook.

- [ ] 4. Verify & Finalize

  **What to do**:
  - Run the full setup flow.
  - Verify `tauri dev` gets past the "resource path doesn't exist" error (it might fail elsewhere, but this specific error should be gone).

  **Recommended Agent**: `quick` (Verification)

  **Acceptance Criteria**:
  - [ ] `bun run setup:sidecar` completes successfully.
  - [ ] `ls -l src-tauri/binaries/` shows the downloaded binary.

---

## Success Criteria
- [ ] `scripts/setup-sidecar.ts` exists and functions correctly.
- [ ] `src-tauri/binaries/` is ignored in git.
- [ ] `package.json` has the setup hook.
