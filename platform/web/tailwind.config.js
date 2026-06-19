/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        critical: { DEFAULT: '#dc2626', light: '#ef4444', dark: '#991b1b' },
        high: { DEFAULT: '#ea580c', light: '#f97316', dark: '#c2410c' },
        medium: { DEFAULT: '#ca8a04', light: '#eab308', dark: '#a16207' },
        low: { DEFAULT: '#16a34a', light: '#22c55e', dark: '#15803d' },
        monitoring: { DEFAULT: '#0891b2', light: '#06b6d4', dark: '#0e7490' },
      },
    },
  },
  plugins: [],
};
