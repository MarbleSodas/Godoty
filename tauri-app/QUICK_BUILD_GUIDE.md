# Quick Build Guide - Godoty Tauri Application

## Prerequisites

- ✅ Rust installed (already present at `%USERPROFILE%\.cargo\bin`)
- ✅ Bun package manager
- ✅ Node.js and Angular CLI
- ✅ Windows development environment

## Quick Start

### Option 1: One-Time Build (Recommended for now)

```powershell
# Navigate to tauri-app directory
cd tauri-app

# Set PATH and build (release)
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"; bun run tauri build

# Or for development
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"; bun run tauri dev
```

### Option 2: Permanent PATH Setup (Recommended for regular development)

1. Open System Environment Variables:
   - Press `Win + X` → System
   - Click "Advanced system settings"
   - Click "Environment Variables"

2. Add to User PATH:
   - Find "Path" under User variables
   - Click "Edit"
   - Click "New"
   - Add: `%USERPROFILE%\.cargo\bin`
   - Click "OK" on all dialogs

3. Restart PowerShell and run:
   ```powershell
   cd tauri-app
   bun run tauri build
   ```

## Build Commands

### Development Build (with hot reload)
```powershell
bun run tauri dev
```
- Starts Angular dev server on http://localhost:4200
- Launches Tauri app in debug mode
- Enables hot module replacement
- Faster compilation, larger binary

### Production Build
```powershell
bun run tauri build
```
- Builds optimized Angular bundle
- Compiles Rust in release mode
- Creates installers:
  - MSI: `src-tauri/target/release/bundle/msi/tauri-app_0.1.0_x64_en-US.msi`
  - NSIS: `src-tauri/target/release/bundle/nsis/tauri-app_0.1.0_x64-setup.exe`

### Frontend Only
```powershell
bun run build    # Production build
bun run start    # Development server
```

## Build Output Locations

```
tauri-app/
├── dist/                                    # Angular build output
│   └── browser/                            # Frontend bundle
├── src-tauri/
│   └── target/
│       ├── debug/
│       │   └── tauri-app.exe              # Debug executable
│       └── release/
│           ├── tauri-app.exe              # Release executable
│           └── bundle/
│               ├── msi/                   # MSI installer
│               └── nsis/                  # NSIS installer
```

## Troubleshooting

### "cargo: command not found"
**Solution:** Run with PATH set:
```powershell
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"; bun run tauri build
```

### Stack Overflow Error
**Status:** ✅ Fixed in current version
**Previous Issue:** Infinite recursion in Storage::default()

### Send Trait Errors
**Status:** ✅ Fixed in current version
**Previous Issue:** MutexGuard held across await points

### Build Fails with "conflicting implementations"
**Status:** ✅ Fixed in current version
**Previous Issue:** Duplicate Default trait implementations

## Development Workflow

1. **Start Development Server:**
   ```powershell
   bun run tauri dev
   ```

2. **Make Changes:**
   - Frontend: Edit files in `src/` (auto-reloads)
   - Backend: Edit files in `src-tauri/src/` (auto-recompiles)

3. **Test Changes:**
   - Application window updates automatically
   - Check console for errors

4. **Build for Distribution:**
   ```powershell
   bun run tauri build
   ```

## Performance Notes

- **First build:** ~2-3 minutes (compiles all dependencies)
- **Incremental builds:** ~7-22 seconds
- **Frontend only:** ~1-2 seconds

## Common Tasks

### Clean Build
```powershell
# Clean Rust build artifacts
cd src-tauri
cargo clean
cd ..

# Clean frontend
Remove-Item -Recurse -Force dist, node_modules/.cache
```

### Update Dependencies
```powershell
# Update Rust dependencies
cd src-tauri
cargo update
cd ..

# Update frontend dependencies
bun update
```

### Check for Issues
```powershell
# Check Rust code
cd src-tauri
cargo check
cargo clippy

# Check TypeScript
bun run ng lint
```

## Configuration Files

- `tauri.conf.json` - Tauri app configuration
- `src-tauri/Cargo.toml` - Rust dependencies
- `package.json` - Frontend dependencies and scripts
- `angular.json` - Angular build configuration

## Support

For detailed information about the fixes applied, see `BUILD_FIX_SUMMARY.md`.

For Tauri documentation: https://tauri.app/
For Angular documentation: https://angular.dev/

