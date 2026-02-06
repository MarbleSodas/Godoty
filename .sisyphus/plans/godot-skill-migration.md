# Godot MCP Skill Migration

## TL;DR

> **Quick Summary**: Migrate godot-mcp and godot-doc-mcp into a single OpenCode skill bundled in the Godoty repo, upgrade SDK to 1.18.x, and add a new viewport screenshot capability.
> 
> **Deliverables**:
> - `/skills/godot/` directory with complete skill implementation
> - `SKILL.md` defining two embedded MCP servers
> - Migrated TypeScript code (SDK 0.6→1.18 upgrade for godot-mcp)
> - New `capture_viewport` tool with GDScript EditorPlugin
> - ≥22 tests (12 ported + 10 new)
> 
> **Estimated Effort**: Medium-Large
> **Parallel Execution**: YES - 3 waves
> **Critical Path**: Task 1 → Task 2 → Task 4 → Task 5 → Task 7

---

## Context

### Original Request
Create a plan to migrate the godot MCP server to be a skills implementation and consider adding more tools to it like screenshotting the editor and debug when playing.

### Interview Summary
**Key Discussions**:
- **Migration scope**: Bundle BOTH godot-mcp and godot-doc-mcp into single skill
- **Screenshot**: Active viewport only (not individual panels), save to `.godot/screenshots/` as PNG
- **Debug capture**: Keep on-demand polling (current behavior)
- **Project detection**: Auto-detect `project.godot` in CWD
- **Location**: Bundled in Godoty repo at `/skills/godot/`
- **Migration strategy**: Full migration, deprecate original repos
- **Testing**: TDD with vitest

**Research Findings**:
- godot-mcp uses SDK 0.6.0 (OUTDATED); godot-doc-mcp uses 1.18.1
- godot-mcp has 14 tools, godot-doc-mcp has 4 tools
- godot-mcp has 0 tests; godot-doc-mcp has 12 test files
- Viewport capture: `EditorInterface.get_base_control().get_viewport().get_texture().get_image()`
- OpenCode skill format uses YAML frontmatter with `mcp:` section

### Metis Review
**Identified Gaps** (addressed):
- SDK version alignment: Plan includes SDK 0.6→1.18 upgrade in Task 4
- GDScript bundle location: Defined at `skills/godot/scripts/godot_operations.gd`
- EditorPlugin communication: Addressed in Task 5 via file-based protocol
- Process orphaning on auto-shutdown: Added cleanup handling in Task 4
- godot-doc-mcp requires `GODOT_DOC_DIR`: Keep as env var requirement

---

## Work Objectives

### Core Objective
Create a fully-functional OpenCode skill at `/skills/godot/` that bundles both Godot automation (14 tools + 1 new) and documentation lookup (4 tools), replacing the standalone MCP server configuration.

### Concrete Deliverables
- `/skills/godot/SKILL.md` - Skill definition with two MCP entries
- `/skills/godot/package.json` - Node package configuration
- `/skills/godot/src/server.ts` - Migrated godot-mcp (SDK 1.18)
- `/skills/godot/src/doc-server.ts` - Migrated godot-doc-mcp
- `/skills/godot/scripts/godot_operations.gd` - GDScript operations bundle
- `/skills/godot/scripts/viewport_capture.gd` - EditorPlugin for screenshots
- `/skills/godot/tests/*.test.ts` - ≥22 test files

### Definition of Done
- [ ] `/skills/godot` loads via OpenCode skill system: `skill(name="godot")` succeeds
- [ ] All 15 godot tools callable via `skill_mcp(mcp_name="godot", ...)`
- [ ] All 4 godot-doc tools callable via `skill_mcp(mcp_name="godot-doc", ...)`
- [ ] `capture_viewport` creates PNG in `.godot/screenshots/`
- [ ] `npm test` in skills/godot → ≥22 tests pass
- [ ] No SDK deprecation warnings in build output

### Must Have
- All 18 existing tools with identical parameter schemas
- SDK 1.18.x for both MCP servers
- `godot_operations.gd` bundled in dist output
- New `capture_viewport` tool
- TDD tests for all tool handlers

### Must NOT Have (Guardrails)
- Changed tool behavior during migration (pure code move)
- Dependencies beyond what original servers use
- New tools beyond the 15+4 defined (`capture_viewport` is the only addition)
- Refactored internal logic while migrating
- Bundled Godot documentation (require external `GODOT_DOC_DIR`)
- Config files (keep env vars as-is)
- Any "while here, let's also..." scope creep

---

## Verification Strategy (MANDATORY)

### Test Decision
- **Infrastructure exists**: YES (vitest in root package.json)
- **User wants tests**: TDD
- **Framework**: vitest

### If TDD Enabled

Each TODO follows RED-GREEN-REFACTOR where applicable. For migration tasks, tests verify existing behavior is preserved.

### Automated Verification (Agent-Executable)

**By Deliverable Type:**

| Type | Verification Tool | Automated Procedure |
|------|------------------|---------------------|
| **Skill Loading** | skill_mcp via Bash | Agent loads skill, calls tools, validates JSON responses |
| **Build Output** | Bash commands | Agent runs build, checks for files, greps for errors |
| **Tests** | vitest via Bash | Agent runs `npm test`, captures exit code and output |
| **MCP Tools** | curl/direct call | Agent invokes tools with test fixtures, validates schemas |

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately):
├── Task 1: Create skill scaffold and validate format
└── Task 3: Port godot-doc-mcp tests first

Wave 2 (After Wave 1):
├── Task 2: Migrate godot-doc-mcp (with its tests)
├── Task 4: Migrate godot-mcp with SDK upgrade
└── Task 6: Write tests for godot-mcp tools

Wave 3 (After Wave 2):
├── Task 5: Implement capture_viewport tool
└── Task 7: Integration testing

Critical Path: Task 1 → Task 2 → Task 4 → Task 5 → Task 7
Parallel Speedup: ~35% faster than sequential
```

### Dependency Matrix

| Task | Depends On | Blocks | Can Parallelize With |
|------|------------|--------|---------------------|
| 1 | None | 2, 4 | 3 |
| 2 | 1 | 5, 7 | 4, 6 |
| 3 | None | 2 | 1 |
| 4 | 1 | 5, 7 | 2, 6 |
| 5 | 2, 4 | 7 | None |
| 6 | None | 4 | 2, 3 |
| 7 | 2, 4, 5 | None | None (final) |

### Agent Dispatch Summary

| Wave | Tasks | Recommended Agents |
|------|-------|-------------------|
| 1 | 1, 3 | Two parallel `quick` agents |
| 2 | 2, 4, 6 | Two `unspecified-high` + one `quick` |
| 3 | 5, 7 | Sequential `unspecified-high` |

---

## TODOs

- [x] 1. Create skill scaffold and validate format

  **What to do**:
  - Create `/skills/godot/` directory structure
  - Create `SKILL.md` with YAML frontmatter defining two MCP entries:
    ```yaml
    ---
    name: godot
    description: "Godot game engine automation and documentation"
    mcp:
      godot:
        command: ["node", "./dist/server.js"]
        env:
          GODOT_PATH: "${GODOT_PATH}"
      godot-doc:
        command: ["node", "./dist/doc-server.js"]
        env:
          GODOT_DOC_DIR: "${GODOT_DOC_DIR}"
    allowed-tools: ["skill_mcp", "Read", "Write", "Bash"]
    ---
    
    # Godot Skill
    [Instructions for using the skill]
    ```
  - Create minimal `package.json` with vitest, typescript, @modelcontextprotocol/sdk@^1.18.0
  - Create stub `src/server.ts` and `src/doc-server.ts` that export empty MCP servers
  - Create `tsconfig.json` for TypeScript compilation
  - Verify skill loads via OpenCode

  **Must NOT do**:
  - Implement any actual tools yet
  - Add dependencies beyond SDK

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple scaffolding task with known structure
  - **Skills**: [`git-master`]
    - `git-master`: For creating initial commit if needed
  - **Skills Evaluated but Omitted**:
    - `frontend-ui-ux`: No frontend work

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 3)
  - **Blocks**: Tasks 2, 4
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `/Users/eugene/mcp-servers/godot-mcp/package.json` - Package structure to mirror
  - `/Users/eugene/mcp-servers/godot-doc-mcp/package.json` - Package structure reference

  **External References**:
  - OpenCode skill format: YAML frontmatter with `mcp:` section for embedded servers

  **WHY Each Reference Matters**:
  - Package.json files show exact dependencies and scripts structure to replicate

  **Acceptance Criteria**:

  **Automated Verification:**
  ```bash
  # AC1.1: Directory structure exists
  test -d skills/godot/src && test -f skills/godot/SKILL.md && test -f skills/godot/package.json
  # Assert: Exit code 0

  # AC1.2: Package.json has correct SDK version
  grep -q '"@modelcontextprotocol/sdk": "\^1.18' skills/godot/package.json
  # Assert: Exit code 0

  # AC1.3: TypeScript compiles without errors
  cd skills/godot && npm install && npm run build 2>&1 | grep -c "error"
  # Assert: Output is "0"

  # AC1.4: SKILL.md has both MCP entries
  grep -c "godot:" skills/godot/SKILL.md && grep -c "godot-doc:" skills/godot/SKILL.md
  # Assert: Both return "1"
  ```

  **Commit**: YES
  - Message: `feat(skills): create godot skill scaffold with dual MCP configuration`
  - Files: `skills/godot/*`
  - Pre-commit: `cd skills/godot && npm run build`

---

- [x] 2. Migrate godot-doc-mcp server

  **What to do**:
  - Copy all source files from `/Users/eugene/mcp-servers/godot-doc-mcp/server/src/` to `skills/godot/src/doc/`
  - Update import paths for new location
  - Create `src/doc-server.ts` as entry point
  - Ensure all 4 documentation tools work:
    - `godot_search` - Search documentation
    - `godot_get_class` - Get class documentation
    - `godot_list_classes` - List available classes
    - `godot_get_method` - Get method documentation
  - Bundle XML parser and search index dependencies
  - Test with sample GODOT_DOC_DIR

  **Must NOT do**:
  - Change tool names or parameter schemas
  - Modify internal logic
  - Bundle actual Godot documentation

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Migration with multiple files and dependency management
  - **Skills**: [`git-master`]
    - `git-master`: For atomic commits
  - **Skills Evaluated but Omitted**:
    - `playwright`: No browser automation

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 6)
  - **Blocks**: Tasks 5, 7
  - **Blocked By**: Task 1, Task 3

  **References**:

  **Pattern References**:
  - `/Users/eugene/mcp-servers/godot-doc-mcp/server/src/cli.ts` - Entry point pattern to follow
  - `/Users/eugene/mcp-servers/godot-doc-mcp/server/src/doc-parser.ts` - Documentation parser
  - `/Users/eugene/mcp-servers/godot-doc-mcp/server/src/search-index.ts` - Search implementation

  **Test References**:
  - `/Users/eugene/mcp-servers/godot-doc-mcp/server/test/` - All 12 test files to port (from Task 3)

  **WHY Each Reference Matters**:
  - cli.ts shows the MCP server initialization pattern for SDK 1.18
  - Test files validate correct behavior preservation

  **Acceptance Criteria**:

  **TDD:**
  - [ ] All 12 ported tests pass: `cd skills/godot && npm test -- --grep "godot-doc"`
  - [ ] Test command: `npm test` → PASS (12 doc-related tests)

  **Automated Verification:**
  ```bash
  # AC2.1: Doc server builds without errors
  cd skills/godot && npm run build 2>&1 | grep -c "error TS"
  # Assert: Output is "0"

  # AC2.2: Entry point exists
  test -f skills/godot/dist/doc-server.js
  # Assert: Exit code 0

  # AC2.3: Tools are registered (dry-run)
  cd skills/godot && node -e "
    import('./dist/doc-server.js').then(m => {
      console.log(m.server ? 'Server exported' : 'Missing export');
    });
  "
  # Assert: Output contains "Server exported"
  ```

  **Evidence to Capture:**
  - [ ] Test output showing 12 tests pass
  - [ ] Build output with no TypeScript errors

  **Commit**: YES
  - Message: `feat(skills/godot): migrate godot-doc-mcp with all 4 documentation tools`
  - Files: `skills/godot/src/doc/*`, `skills/godot/src/doc-server.ts`
  - Pre-commit: `cd skills/godot && npm test && npm run build`

---

- [x] 3. Port godot-doc-mcp test suite

  **What to do**:
  - Copy all test files from `/Users/eugene/mcp-servers/godot-doc-mcp/server/test/` to `skills/godot/tests/doc/`
  - Update import paths for new source locations
  - Configure vitest to find these tests
  - Ensure tests can run with sample/mock documentation directory
  - Create test fixtures directory with minimal Godot XML docs

  **Must NOT do**:
  - Modify test logic or assertions
  - Skip or disable any existing tests
  - Create new tests (that's Task 6)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Straightforward file copying and path updates
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `git-master`: No commits in this task

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 1)
  - **Blocks**: Task 2
  - **Blocked By**: None (can start immediately)

  **References**:

  **Test References**:
  - `/Users/eugene/mcp-servers/godot-doc-mcp/server/test/*.test.ts` - All 12 test files to port

  **Configuration References**:
  - `/Users/eugene/mcp-servers/godot-doc-mcp/vitest.config.ts` - Vitest configuration pattern

  **WHY Each Reference Matters**:
  - Test files must be ported exactly to ensure behavior preservation
  - vitest.config shows how tests were configured in original repo

  **Acceptance Criteria**:

  **Automated Verification:**
  ```bash
  # AC3.1: All test files copied
  ls -1 skills/godot/tests/doc/*.test.ts | wc -l
  # Assert: Output is "12" (or matches source count)

  # AC3.2: Tests discoverable by vitest
  cd skills/godot && npx vitest list 2>&1 | grep -c "doc/"
  # Assert: Output ≥ 12

  # AC3.3: Test fixtures exist
  test -d skills/godot/tests/fixtures/godot-docs
  # Assert: Exit code 0
  ```

  **Commit**: NO (groups with Task 2)

---

- [x] 4. Migrate godot-mcp with SDK upgrade

  **What to do**:
  - Copy `/Users/eugene/mcp-servers/godot-mcp/src/index.ts` to `skills/godot/src/server.ts`
  - **Upgrade from SDK 0.6.0 to 1.18.x** - This is a BREAKING change requiring:
    - Update import paths: `@modelcontextprotocol/sdk/server/index.js` → `@modelcontextprotocol/sdk/server`
    - Update server initialization pattern
    - Replace deprecated `setRequestHandler` pattern with 1.x registration
  - Copy `scripts/godot_operations.gd` to `skills/godot/scripts/`
  - Add build step to copy GDScript to dist folder
  - Ensure all 14 automation tools work:
    - `launch_editor`, `run_project`, `get_debug_output`, `stop_project`
    - `get_godot_version`, `list_projects`, `get_project_info`
    - `create_scene`, `add_node`, `load_sprite`, `export_mesh_library`, `save_scene`
    - `get_uid`, `update_project_uids`
  - Handle `activeProcess` cleanup on server shutdown (for skill auto-shutdown)
  - Preserve `GodotServer` class with all validation logic

  **Must NOT do**:
  - Change tool names or parameter schemas
  - Modify `godot_operations.gd` script logic
  - Add new tools (that's Task 5)
  - Refactor internal class structure

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Complex SDK migration with breaking changes
  - **Skills**: [`git-master`]
    - `git-master`: For atomic commits
  - **Skills Evaluated but Omitted**:
    - `ultrabrain`: SDK migration is well-documented, not novel problem

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 2, 6)
  - **Blocks**: Tasks 5, 7
  - **Blocked By**: Task 1

  **References**:

  **Pattern References**:
  - `/Users/eugene/mcp-servers/godot-mcp/src/index.ts:1-168` - GodotServer class setup and config
  - `/Users/eugene/mcp-servers/godot-mcp/src/index.ts:666-968` - All 14 tool definitions in `setupToolHandlers()`
  - `/Users/eugene/mcp-servers/godot-doc-mcp/server/src/cli.ts` - SDK 1.18 server initialization pattern (FOLLOW THIS)

  **Script References**:
  - `/Users/eugene/mcp-servers/godot-mcp/build/scripts/godot_operations.gd` - Bundle this file

  **External References**:
  - MCP SDK 1.x migration: Check npm package docs for breaking changes from 0.6

  **WHY Each Reference Matters**:
  - godot-mcp/src/index.ts is the 1600-line file being migrated
  - godot-doc-mcp/cli.ts shows the TARGET SDK pattern
  - godot_operations.gd must be bundled exactly (Godot runtime dependency)

  **Acceptance Criteria**:

  **TDD:**
  - [ ] All 10 godot-mcp tests pass: `cd skills/godot && npm test -- --grep "godot-automation"`
  - [ ] Test command: `npm test` → PASS (10 automation tests from Task 6)

  **Automated Verification:**
  ```bash
  # AC4.1: Server builds without deprecation warnings
  cd skills/godot && npm run build 2>&1 | grep -ic "deprecated"
  # Assert: Output is "0"

  # AC4.2: GDScript bundled in dist
  test -f skills/godot/dist/scripts/godot_operations.gd
  # Assert: Exit code 0

  # AC4.3: All 14 tools registered
  cd skills/godot && node -e "
    import('./dist/server.js').then(m => {
      console.log(JSON.stringify(Object.keys(m.toolHandlers || m.tools || {})));
    });
  " | jq 'length'
  # Assert: Output is "14"

  # AC4.4: get_godot_version works (smoke test)
  cd skills/godot && node -e "
    import('./dist/server.js').then(async m => {
      const result = await m.handleGetGodotVersion();
      console.log(result.content ? 'Tool works' : 'Tool failed');
    });
  "
  # Assert: Output is "Tool works" (or Godot version string)
  ```

  **Evidence to Capture:**
  - [ ] Build output showing no deprecation warnings
  - [ ] Test output showing 10 automation tests pass

  **Commit**: YES
  - Message: `feat(skills/godot): migrate godot-mcp with SDK 1.18 upgrade`
  - Files: `skills/godot/src/server.ts`, `skills/godot/scripts/godot_operations.gd`
  - Pre-commit: `cd skills/godot && npm test && npm run build`

---

- [x] 5. Implement capture_viewport tool

  **What to do**:
  - Create `skills/godot/scripts/viewport_capture.gd` EditorPlugin:
    ```gdscript
    @tool
    extends EditorScript

    func _run():
        var viewport = EditorInterface.get_editor_viewport_2d() # or 3D
        await RenderingServer.frame_post_draw
        var img = viewport.get_texture().get_image()
        var screenshots_dir = ProjectSettings.globalize_path("res://").path_join(".godot/screenshots")
        DirAccess.make_dir_recursive_absolute(screenshots_dir)
        var filename = "viewport_%d.png" % Time.get_unix_time_from_system()
        img.save_png(screenshots_dir.path_join(filename))
        print("SCREENSHOT_PATH:" + screenshots_dir.path_join(filename))
    ```
  - Add new `capture_viewport` tool to server.ts:
    - Parameters: `projectPath` (required)
    - Executes viewport_capture.gd via `--script` flag
    - Parses output for `SCREENSHOT_PATH:` line
    - Returns `{ path: "/absolute/path/to/screenshot.png" }`
  - Create `.godot/screenshots/` directory if missing
  - Handle errors (no project, Godot not found, etc.)

  **Must NOT do**:
  - Capture specific panels (scope is viewport only)
  - Add configuration options beyond projectPath
  - Implement screenshot streaming or real-time capture

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: New feature with GDScript + TypeScript integration
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `playwright`: Not browser automation

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (sequential)
  - **Blocks**: Task 7
  - **Blocked By**: Tasks 2, 4

  **References**:

  **Pattern References**:
  - `/Users/eugene/mcp-servers/godot-mcp/src/index.ts:475-543` - `executeOperation()` pattern for running GDScript
  - `/Users/eugene/mcp-servers/godot-mcp/src/index.ts:1482-1551` - `handleCreateScene()` as similar tool handler

  **API References**:
  - Godot EditorInterface: `get_editor_viewport_2d()`, `get_editor_viewport_3d()`
  - Image save: `Image.save_png(path)` 

  **WHY Each Reference Matters**:
  - executeOperation shows how to run GDScript via Godot CLI and parse output
  - handleCreateScene shows error handling pattern for similar operations

  **Acceptance Criteria**:

  **TDD:**
  - [ ] Test file created: `skills/godot/tests/capture-viewport.test.ts`
  - [ ] Test covers: tool returns valid path
  - [ ] Test covers: creates screenshots directory
  - [ ] Test command: `npm test -- capture-viewport.test.ts` → PASS

  **Automated Verification (requires Godot project):**
  ```bash
  # AC5.1: Tool registered
  cd skills/godot && node -e "
    import('./dist/server.js').then(m => {
      console.log('capture_viewport' in (m.toolHandlers || m.tools || {}) ? 'Found' : 'Missing');
    });
  "
  # Assert: Output is "Found"

  # AC5.2: GDScript exists
  test -f skills/godot/scripts/viewport_capture.gd
  # Assert: Exit code 0

  # AC5.3: GDScript bundled in dist
  test -f skills/godot/dist/scripts/viewport_capture.gd
  # Assert: Exit code 0
  ```

  **For manual verification with real Godot project:**
  ```bash
  # Agent runs tool against test project
  skill_mcp(mcp_name="godot", tool_name="capture_viewport", arguments='{"projectPath":"/path/to/test/project"}')
  # Assert: Returns JSON with "path" field
  # Assert: File at returned path exists and is valid PNG
  ```

  **Commit**: YES
  - Message: `feat(skills/godot): add capture_viewport tool for editor screenshots`
  - Files: `skills/godot/scripts/viewport_capture.gd`, `skills/godot/src/server.ts`
  - Pre-commit: `cd skills/godot && npm test && npm run build`

---

- [x] 6. Write tests for godot-mcp tool handlers

  **What to do**:
  - Create test files for godot-mcp tools:
    - `tests/automation/launch-editor.test.ts`
    - `tests/automation/run-project.test.ts`
    - `tests/automation/project-management.test.ts` (list_projects, get_project_info)
    - `tests/automation/scene-operations.test.ts` (create_scene, add_node, save_scene)
    - `tests/automation/godot-version.test.ts`
  - Mock Godot executable for unit tests
  - Test parameter validation (required fields, path validation)
  - Test error handling (invalid paths, Godot not found)
  - Minimum 10 test cases covering core functionality

  **Must NOT do**:
  - Integration tests requiring real Godot installation
  - Tests for capture_viewport (that's part of Task 5)
  - Modify source code

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Test writing with clear patterns to follow
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `git-master`: No commits in this task

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 2, 4)
  - **Blocks**: Task 4 (tests must exist before migration is "complete")
  - **Blocked By**: None (can write tests against expected behavior)

  **References**:

  **Test References**:
  - `/Users/eugene/mcp-servers/godot-doc-mcp/server/test/*.test.ts` - Test patterns to follow
  - `/Users/eugene/Documents/Github Projects/GodotyApp/Godoty/packages/app/src/utils/server-health.test.ts` - Godoty test patterns

  **Pattern References**:
  - `/Users/eugene/mcp-servers/godot-mcp/src/index.ts:974-1047` - handleLaunchEditor to test
  - `/Users/eugene/mcp-servers/godot-mcp/src/index.ts:207-216` - validatePath function to test

  **WHY Each Reference Matters**:
  - godot-doc-mcp tests show vitest patterns used in original codebase
  - Handler methods show exact behavior to verify

  **Acceptance Criteria**:

  **Automated Verification:**
  ```bash
  # AC6.1: At least 10 test cases
  cd skills/godot && npx vitest list 2>&1 | grep -c "automation/"
  # Assert: Output ≥ 10

  # AC6.2: Tests pass (with mocked Godot)
  cd skills/godot && npm test -- --grep "automation" 2>&1 | tail -5
  # Assert: Contains "10 passed" or similar

  # AC6.3: Test files exist
  ls -1 skills/godot/tests/automation/*.test.ts | wc -l
  # Assert: Output ≥ 5
  ```

  **Commit**: NO (groups with Task 4)

---

- [x] 7. Integration testing and final verification

  **What to do**:
  - Run full test suite: `cd skills/godot && npm test`
  - Verify skill loads via OpenCode: `skill(name="godot")`
  - Test both MCP servers are callable:
    - `skill_mcp(mcp_name="godot", tool_name="get_godot_version")`
    - `skill_mcp(mcp_name="godot-doc", tool_name="godot_list_classes", arguments='{"limit":5}')`
  - Verify no SDK deprecation warnings in build
  - Run smoke test with real Godot project if available
  - Update SKILL.md with final usage instructions
  - Verify all 19 tools (14+4+1) are registered

  **Must NOT do**:
  - Add new features
  - Fix bugs by changing behavior (flag for future tasks)
  - Modify tool implementations

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Final integration verification requires multiple checks
  - **Skills**: [`git-master`]
    - `git-master`: For final commit
  - **Skills Evaluated but Omitted**:
    - `playwright`: No browser testing

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (sequential, final)
  - **Blocks**: None (final task)
  - **Blocked By**: Tasks 2, 4, 5

  **References**:

  **All Previous Task Outputs**:
  - All acceptance criteria from Tasks 1-6 should pass

  **WHY Each Reference Matters**:
  - Integration test verifies all components work together

  **Acceptance Criteria**:

  **Automated Verification:**
  ```bash
  # AC7.1: Full test suite passes
  cd skills/godot && npm test
  # Assert: Exit code 0, ≥22 tests pass

  # AC7.2: Build has no deprecation warnings
  cd skills/godot && npm run build 2>&1 | grep -ic "deprecated"
  # Assert: Output is "0"

  # AC7.3: All 19 tools registered
  cd skills/godot && node -e "
    Promise.all([
      import('./dist/server.js').then(m => Object.keys(m.tools || {}).length),
      import('./dist/doc-server.js').then(m => Object.keys(m.tools || {}).length)
    ]).then(([a, b]) => console.log(a + b));
  "
  # Assert: Output is "19" (15 + 4)

  # AC7.4: SKILL.md has usage instructions
  grep -c "## Usage" skills/godot/SKILL.md
  # Assert: Output is "1"
  ```

  **Evidence to Capture:**
  - [ ] Full test output with all tests passing
  - [ ] skill_mcp calls to both servers returning valid responses

  **Commit**: YES
  - Message: `feat(skills/godot): complete godot skill migration with 19 tools`
  - Files: `skills/godot/SKILL.md`
  - Pre-commit: `cd skills/godot && npm test && npm run build`

---

## Commit Strategy

| After Task | Message | Files | Verification |
|------------|---------|-------|--------------|
| 1 | `feat(skills): create godot skill scaffold with dual MCP configuration` | skills/godot/* | npm run build |
| 2, 3 | `feat(skills/godot): migrate godot-doc-mcp with all 4 documentation tools` | skills/godot/src/doc/*, tests/doc/* | npm test |
| 4, 6 | `feat(skills/godot): migrate godot-mcp with SDK 1.18 upgrade` | skills/godot/src/server.ts, scripts/* | npm test |
| 5 | `feat(skills/godot): add capture_viewport tool for editor screenshots` | skills/godot/scripts/viewport_capture.gd | npm test |
| 7 | `feat(skills/godot): complete godot skill migration with 19 tools` | skills/godot/SKILL.md | npm test |

---

## Success Criteria

### Verification Commands
```bash
# All tests pass
cd skills/godot && npm test
# Expected: ≥22 tests pass, exit code 0

# Build succeeds with no deprecation warnings
cd skills/godot && npm run build 2>&1 | grep -ic "deprecated"
# Expected: 0

# Skill loads
skill(name="godot")
# Expected: Returns skill description, no error

# Both MCPs callable
skill_mcp(mcp_name="godot", tool_name="get_godot_version")
skill_mcp(mcp_name="godot-doc", tool_name="godot_list_classes", arguments='{"limit":3}')
# Expected: Both return valid JSON
```

### Final Checklist
- [ ] All "Must Have" present (19 tools, SDK 1.18, tests)
- [ ] All "Must NOT Have" absent (no scope creep, no behavior changes)
- [ ] All tests pass (≥22)
- [ ] Build has no deprecation warnings
- [ ] Skill loads via OpenCode
- [ ] Both MCP servers respond to tool calls
