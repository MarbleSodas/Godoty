/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/**/*.{html,ts}',
    './projects/**/*.{html,ts}',
  ],
  theme: {
    extend: {
      colors: {
        // Canvas-style color palette
        canvas: {
          primary: '#202531',    // Main background
          secondary: '#1a1e29',  // Chat area background
          accent: '#2d333b',     // Hover states
          highlight: '#478cbf',  // Accent color (keeping existing)
          text: '#e6edf3',       // Primary text
          textSecondary: '#8b949e', // Secondary text
          border: '#30363d',     // Borders
          sidebar: '#161b22',    // Sidebar background
        },
        // Legacy dark colors for compatibility during transition
        dark: {
          primary: '#212529',
          secondary: '#1a1d21',
          accent: '#363d4a',
          highlight: '#478cbf',
          text: '#e2e8f0',
          border: '#363d4a',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'fade-in-up': 'fadeInUp 0.3s ease-out',
        'slide-down': 'slideDown 0.2s ease-out',
        'slide-right': 'slideRight 0.2s ease-out',
        'text-fade-up': 'textFadeUp 0.25s ease-out',
      },
      keyframes: {
        fadeIn: {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        fadeInUp: {
          from: { opacity: '0', transform: 'translateY(10px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        slideDown: {
          from: { transform: 'translateY(-10px)', opacity: '0' },
          to: { transform: 'translateY(0)', opacity: '1' },
        },
        slideRight: {
          from: { transform: 'translateX(20px)', opacity: '0' },
          to: { transform: 'translateX(0)', opacity: '1' },
        },
        textFadeUp: {
          from: { transform: 'translateY(4px)', opacity: '0' },
          to: { transform: 'translateY(0)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}