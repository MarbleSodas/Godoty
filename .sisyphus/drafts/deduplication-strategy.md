# Draft: Dependency Deduplication Strategy

## Problem
The `bg_79e87aad` investigation revealed a **critical** issue: there are 3 copies of `solid-js` installed in the project, with version mismatches:
- `node_modules/solid-js`: **v1.9.11**
- `packages/app/node_modules/solid-js`: **v1.9.10**
- `packages/ui/node_modules/solid-js`: **v1.9.10**

This breaks the "singleton reactivity" rule of SolidJS. When `packages/app` uses one copy and `packages/ui` uses another, signals created in one scope don't trigger updates in the other, leading to a broken/frozen UI (often a black screen or non-responsive components).

## Root Cause
Despite our previous `bun install`, the lockfile or `bun`'s hoisting logic decided to install nested dependencies because `packages/app/package.json` explicitly pinned `1.9.10` while the root might have allowed `^1.9.3` which resolved to `1.9.11`.

## Plan
1. **Force Resolution**: Use `overrides` or `resolutions` in the root `package.json` to force `1.9.11` globally.
2. **Nuke Node Modules**: Delete all `node_modules` folders to ensure a clean install.
3. **Reinstall**: Run `bun install` to generate a fresh, correct lockfile.
4. **Verify**: Check `ls` again to confirm nested `node_modules/solid-js` are GONE.

This is the definitive fix for the "reactivity mismatch" class of black screen bugs.
