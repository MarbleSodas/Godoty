# Draft: Debugging Dependency Discrepancies (Dev vs Build)

## Hypothesis
1. **Tree Shaking/Externalization**: A dependency used at runtime is marked as `devDependency` or `external` in Vite, causing it to be missing from the production bundle.
2. **Sidecar Dependencies**: The sidecar binary (`opencode-cli`) depends on system libraries (like `libc`, `libssl`) that are present in the dev environment but missing or version-mismatched in the packaged app's environment.
3. **Rust Features**: Production build might be missing a Cargo feature enabled in dev.
4. **Vite Define/Env**: `import.meta.env` or `process.env` differences causing conditional imports to fail.

## Research Plan
- **Audit `package.json`**: Compare `dependencies` vs `devDependencies`.
- **Audit `vite.config.ts`**: Check for `external` or `rollupOptions`.
- **Audit `Cargo.toml`**: Check features and dependencies.
- **Inspect Build Logs**: Look for "Treating X as external" warnings during `vite build`.
- **Verify Sidecar Linked Libs**: Use `otool -L` (macOS) or `ldd` (Linux) on the sidecar binary to see dynamic link requirements.
