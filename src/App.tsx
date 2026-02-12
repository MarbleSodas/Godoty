import { Component } from "solid-js";
import "@opencode-ai/ui/styles/index.css";
import { AppBaseProviders, AppInterface, PlatformProvider, type Platform } from "@opencode-ai/app";
import "./App.css";
import UpdateBanner from "./components/UpdateBanner";
import SidecarUpdateBanner from "./components/SidecarUpdateBanner";

const platform: Platform = {
  platform: "desktop",
  openLink: (url) => window.open(url, "_blank"),
  back: () => window.history.back(),
  forward: () => window.history.forward(),
  restart: async () => window.location.reload(),
  notify: async (title, description) => {
    if (Notification.permission === "granted") {
      new Notification(title, { body: description });
    }
  },
};

const App: Component = () => {
  return (
    <div class="h-screen w-screen bg-gray-50 text-gray-900 dark:bg-gray-900 dark:text-white flex flex-col">
      <UpdateBanner />
      <SidecarUpdateBanner />
      <div class="flex-1 overflow-hidden flex flex-col">
        <PlatformProvider value={platform}>
          <AppBaseProviders>
            <AppInterface />
          </AppBaseProviders>
        </PlatformProvider>
      </div>
    </div>
  );
};

export default App;
