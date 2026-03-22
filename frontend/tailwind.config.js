/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Stitch M3 design system
        primary: '#adc6ff',
        'primary-container': '#4d8eff',
        'on-primary': '#002e6a',
        'on-primary-container': '#00285d',
        tertiary: '#ffb95f',
        'tertiary-container': '#ca8100',
        error: '#ffb4ab',
        'error-container': '#93000a',
        surface: '#0b1326',
        'surface-container': '#171f33',
        'surface-container-low': '#131b2e',
        'surface-container-high': '#222a3d',
        'surface-container-highest': '#2d3449',
        'surface-container-lowest': '#060e20',
        'on-surface': '#dae2fd',
        'on-surface-variant': '#c2c6d6',
        outline: '#8c909f',
        'outline-variant': '#424754',
        secondary: '#b7c8e1',
        'secondary-container': '#3a4a5f',
        // Legacy aliases (keeps existing code working during migration)
        navy: {
          900: '#0b1326',
          850: '#131b2e',
          800: '#171f33',
          700: '#222a3d',
          600: '#2d3449',
          500: '#424754',
        },
        accent: {
          blue: '#4d8eff',
          green: '#10b981',
          red: '#ef4444',
          yellow: '#f59e0b',
          purple: '#8b5cf6',
        },
      },
      fontFamily: {
        headline: ['Manrope', 'system-ui', 'sans-serif'],
        body: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
};
