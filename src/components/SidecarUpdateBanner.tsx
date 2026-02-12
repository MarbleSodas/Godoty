import { Component, createSignal, onMount, Show } from "solid-js";
import { invoke } from "@tauri-apps/api/core";

const SidecarUpdateBanner: Component = () => {
  const [updateAvailable, setUpdateAvailable] = createSignal<boolean>(false);
  const [version, setVersion] = createSignal<string>("");
  const [updating, setUpdating] = createSignal<boolean>(false);
  const [error, setError] = createSignal<string>("");

  onMount(async () => {
    if (import.meta.env.DEV) {
      console.log("Sidecar update check skipped in development mode");
      return;
    }
    // @ts-ignore
    if (!window.__TAURI_INTERNALS__) {
        return;
    }
    try {
      const info = await invoke<{ available: boolean, latest_version: string, release: any }>("check_sidecar_update");
      if (info.available) {
        setVersion(info.latest_version);
        setUpdateAvailable(true);
        (window as any)._sidecar_release = info.release;
      }
    } catch (e) {
      console.error("Failed to check for sidecar updates", e);
    }
  });

  const installUpdate = async () => {
    setUpdating(true);
    setError("");
    try {
      const release = (window as any)._sidecar_release;
      if (!release) throw new Error("Release info missing");

      await invoke("perform_sidecar_update", { release });
      setUpdateAvailable(false);
      alert("Sidecar updated successfully!");
    } catch (e) {
      console.error("Failed to install sidecar update", e);
      setError("Installation failed: " + String(e));
    } finally {
      setUpdating(false);
    }
  };

  return (
    <Show when={updateAvailable()}>
      <div class="bg-purple-600 text-white px-4 py-2 flex items-center justify-between shadow-md z-50 relative" data-testid="sidecar-update-banner">
        <div class="flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clip-rule="evenodd" />
          </svg>
          <div>
            <span class="font-bold">Core Update Available:</span> v{version()}
          </div>
          {error() && <span class="ml-2 text-red-200 text-sm">({error()})</span>}
        </div>
        <button 
          onClick={installUpdate}
          disabled={updating()}
          class="bg-white text-purple-600 px-3 py-1 rounded font-medium text-sm hover:bg-purple-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          {updating() ? (
            <>
              <svg class="animate-spin h-4 w-4 text-purple-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Updating...
            </>
          ) : (
            "Update Now"
          )}
        </button>
      </div>
    </Show>
  );
};

export default SidecarUpdateBanner;
