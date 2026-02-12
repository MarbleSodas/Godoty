#!/bin/bash
set -e

fix_dmg_in_dir() {
    local DMG_DIR="$1"
    local DMG_FILES=($DMG_DIR/*.dmg)

    if [ ${#DMG_FILES[@]} -eq 0 ] || [ ! -f "${DMG_FILES[0]}" ]; then
        return
    fi

    for DMG_PATH in "${DMG_FILES[@]}"; do
        if [ -f "$DMG_PATH" ]; then
            echo "Fixing DMG: $DMG_PATH"
            
            MOUNT_POINT=$(mktemp -d)
            hdiutil attach "$DMG_PATH" -mountpoint "$MOUNT_POINT" -nobrowse 2>/dev/null || true
            
            if [ -f "$MOUNT_POINT/.VolumeIcon.icns" ]; then
                rm -f "$MOUNT_POINT/.VolumeIcon.icns"
                echo "  Removed .VolumeIcon.icns"
            fi
            
            hdiutil detach "$MOUNT_POINT" 2>/dev/null || true
            rmdir "$MOUNT_POINT"
            
            echo "  Done"
        fi
    done
}

fix_dmg_in_dir "src-tauri/target/release/bundle/dmg"
fix_dmg_in_dir "src-tauri/target/debug/bundle/dmg"

echo "DMG fix complete"
