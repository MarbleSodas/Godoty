/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Godot-inspired color palette
        godot: {
          blue: '#478cbf',
          dark: '#1a1a2e',
          darker: '#16162a',
          surface: '#252538',
          border: '#3d3d5c',
          text: '#e0e0e0',
          muted: '#9090a0',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
