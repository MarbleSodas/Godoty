import { Component } from "solid-js";
import "@opencode-ai/ui/dist/style.css";
import OpenCodeApp from "@opencode-ai/app";
import "./App.css";

const App: Component = () => {
  return (
    <div class="h-screen w-screen bg-gray-50 text-gray-900 dark:bg-gray-900 dark:text-white">
      <OpenCodeApp />
    </div>
  );
};

export default App;
