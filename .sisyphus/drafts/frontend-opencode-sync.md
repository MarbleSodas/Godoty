# Draft: Frontend OpenCode Clone Sync

## Current State

### Package Structure
The Godoty project has a monorepo structure with `@opencode-ai` packages:
- `packages/app` - v1.1.53 (staged, not committed)
- `packages/ui` - v1.1.53 (completely untracked)
- `packages/sdk` - v1.1.53 (completely untracked)
- `packages/util` - v1.1.53 (completely untracked)

### Upstream Source
- **Repository**: https://github.com/anomalyco/opencode
- **Structure**: Same `packages/` folder structure (app, ui, sdk, util, desktop, etc.)
- **Framework**: SolidJS, Tailwind CSS v4, Vite v6

### Runtime Status: ✅ WORKING!
- **Verified**: App runs correctly at http://localhost:1420
- **UI renders**: Menu, navigation, project list, settings all visible
- **Console errors**: ZERO errors at runtime
- **Screenshot saved**: `.sisyphus/evidence/frontend-current-state.png`

### TypeScript LSP Errors (not blocking runtime)
The LSP reports errors for self-referencing imports like:
- `@opencode-ai/app/context/platform`
- `@opencode-ai/app/i18n/en`
- `@opencode-ai/ui/components/font`

These work at runtime because Vite aliases resolve them correctly, but TypeScript doesn't know about the aliases.

## Problem Summary
| Issue | Severity | Status |
|-------|----------|--------|
| Packages untracked in git | HIGH | Needs fixing |
| TypeScript LSP errors | MEDIUM | Cosmetic (runtime works) |
| App functionality | N/A | ✅ Already working |

## Open Questions
1. What should we fix? (Git tracking, TypeScript config, or both?)
2. Do you want to maintain a fork, or sync with upstream on occasion?
3. Any Godoty-specific customizations to preserve?

## Technical Decisions
- (TBD)

## Scope Boundaries
- INCLUDE: (TBD)
- EXCLUDE: (TBD)
