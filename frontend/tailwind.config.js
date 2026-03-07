/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        era: {
          modern: '#3b82f6',
          ww2: '#84cc16',
          ww1: '#f59e0b',
          napoleonic: '#8b5cf6',
          ancient: '#ef4444',
        },
        side: {
          blue: '#2563eb',
          red: '#dc2626',
        },
      },
    },
  },
  plugins: [],
}
