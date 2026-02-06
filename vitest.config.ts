import { defineConfig } from 'vitest/config';
import solidPlugin from 'vite-plugin-solid';

export default defineConfig({
  plugins: [solidPlugin()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['src/setupTests.ts'],
    exclude: ['**/node_modules/**', '**/e2e/**'],
    server: {
      deps: {
        inline: [/solid-js/],
      },
    },
  },
  resolve: {
    conditions: ['development', 'browser'],
  },
});
