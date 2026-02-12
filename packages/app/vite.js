import solidPlugin from "vite-plugin-solid"
import tailwindcss from "@tailwindcss/vite"
import { fileURLToPath } from "url"

/**
 * @type {import("vite").PluginOption}
 */
export default [
  {
    name: "opencode-desktop:config",
    config() {
      return {
        resolve: {
          alias: {
            "@": fileURLToPath(new URL("./src", import.meta.url)),
            "@opencode-ai/app": fileURLToPath(new URL("./src", import.meta.url)),
            "@opencode-ai/ui": fileURLToPath(new URL("../ui/src", import.meta.url)),
            "@opencode-ai/sdk": fileURLToPath(new URL("../sdk/src", import.meta.url)),
            "@opencode-ai/util": fileURLToPath(new URL("../util/src", import.meta.url)),
          },
        },
        worker: {
          format: "es",
        },
      }
    },
  },
  tailwindcss(),
  solidPlugin(),
]
