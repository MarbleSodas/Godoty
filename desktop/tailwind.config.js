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
          dark: '#202531',       // Main background
          darker: '#1a1e29',     // Sidebar/Darker elements
          surface: '#2d3546',    // Cards/Input backgrounds
          border: '#3b4458',     // Borders
          text: '#e0e0e0',       // Primary text
          muted: '#9ca3af',      // Secondary text/icons
          accent: '#478cbf',     // Primary Action
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Consolas', 'monospace'],
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out forwards',
        'fade-in-up': 'fadeInUp 0.3s ease-out forwards',
      },
      keyframes: {
        fadeIn: {
          'from': { opacity: '0' },
          'to': { opacity: '1' },
        },
        fadeInUp: {
          'from': { opacity: '0', transform: 'translateY(10px)' },
          'to': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
