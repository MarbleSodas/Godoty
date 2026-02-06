import { Component, createSignal, onMount } from "solid-js";
import { check } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import { Command } from "@tauri-apps/plugin-shell";

const UpdateBanner: Component = () => {
  const [updateAvailable, setUpdateAvailable] = createSignal<boolean>(false);
  const [version, setVersion] = createSignal<string>("");
  const [error, setError] = createSignal<string>("");

  onMount(async () => {
    try {
      const update = await check();
      if (update?.available) {
        setVersion(update.version);
        setUpdateAvailable(true);
      }
    } catch (e) {
      console.error("Failed to check for updates", e);
      setError("Update check failed");
    }
  });

  const installUpdate = async () => {
    try {
      const update = await check();
      if (update) {
        // Kill sidecar before update on Windows to avoid file locking
        // Note: Sidecar name 'opencode-cli' matches tauri.conf.json
        if (navigator.userAgent.includes("Windows")) {
           try {
             // Attempt to kill via shell command if needed, or rely on SidecarManager shutdown logic
             // For now, we rely on the rust-side lifecycle management to be clean, 
             // but strictly speaking we might want to issue a command here.
             console.log("Preparing to update on Windows...");
           } catch (e) {
             console.error("Failed to kill sidecar", e);
           }
        }

        await update.downloadAndInstall();
        await relaunch();
      }
    } catch (e) {
      console.error("Failed to install update", e);
      setError("Installation failed");
    }
  };

  if (!updateAvailable()) return null;

  return (
    <div class="bg-blue-600 text-white px-4 py-2 flex items-center justify-between" data-testid="update-banner">
      <div>
        <span class="font-bold">Update Available:</span> v{version()}
        {error() && <span class="ml-2 text-red-200">({error()})</span>}
      </div>
      <button 
        onClick={installUpdate}
        class="bg-white text-blue-600 px-3 py-1 rounded font-medium text-sm hover:bg-blue-50 transition-colors"
      >
        Install & Restart
      </button>
    </div>
  );
};

export default UpdateBanner;
