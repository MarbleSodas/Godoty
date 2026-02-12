import { defineConfig } from "vite"
import desktopPlugin from "./vite"

export default defineConfig({
  base: "./",
  plugins: [desktopPlugin] as any,
  server: {
    host: "0.0.0.0",
    allowedHosts: true,
    port: 3000,
  },
  build: {
    target: "es2021",
    // sourcemap: true,
  },
})
