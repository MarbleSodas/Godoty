# Draft: Fix Tauri Dev Build (Missing Sidecar)

## Initial Observation
User is getting a build error: `resource path opencode-cli-x86_64-pc-windows-msvc.exe doesn't exist`.
This indicates a missing Tauri sidecar binary for the Windows target.

## Findings
- **Config**: `src-tauri/tauri.conf.json` defines `opencode-cli` as an `externalBin`.
- **Binaries**: Found in `src-tauri/binaries/`:
  - `opencode-cli-x86_64-pc-windows-msvc.exe`
  - `opencode-cli-x86_64-apple-darwin`
  - `opencode-cli-x86_64-unknown-linux-gnu`
  - `opencode-cli-aarch64-apple-darwin`
- **Issue**: Tauri expects external binaries to be in a specific location (conventionally `src-tauri/bin/` in v1, but strict path rules apply). The build script isn't finding them in `src-tauri/binaries/`.

## Selected Solution: Automated Download Script (Clean)
We will automate the binary management instead of checking large files into git.

### Plan
1.  **Remove** `src-tauri/binaries/` from git (but keep locally for now or re-download).
2.  **Create Script**: `scripts/setup-sidecar.ts` (or .mjs)
    -   Detect current platform (OS + Arch).
    -   Download correct binary from GitHub Releases (User/Repo TBD).
    -   Place in `src-tauri/bin/` with correct target triple suffix.
    -   Set execute permissions (chmod +x).
3.  **Update package.json**: Add `predev` and `prebuild` hooks to run this script.
4.  **Update .gitignore**: Ignore `src-tauri/bin/`.

## Open Questions
- What is the GitHub repository URL for `opencode-cli` releases? (Need to ask user or assume placeholder).
- Do we have a token for private repo access if needed?

## Scope
- IN: Fix build error, implement download script, cleanup git.
- OUT: Modifying the sidecar code itself.
