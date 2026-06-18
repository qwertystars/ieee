/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        critical: '#dc2626',
        high: '#ea580c',
        medium: '#d97706',
        low: '#65a30d',
        monitoring: '#0284c7',
      },
    },
  },
  plugins: [],
}
