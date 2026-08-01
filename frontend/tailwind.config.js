/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Full indigo scale. 200/300/400/800/950 were used throughout the app but
        // never defined, so those utilities generated no CSS and the elements using
        // them (citation links, badges) fell back to inherited colours.
        brand: {
          50: '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
          950: '#1e1b4b',
        },
        surface: {
          light: '#f8fafc',
          dark: '#0f172a',
          cardLight: '#ffffff',
          cardDark: '#1e293b',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'soft-sm': '0 2px 8px -2px rgba(0, 0, 0, 0.05)',
        'soft-md': '0 8px 24px -4px rgba(0, 0, 0, 0.08)',
        'soft-lg': '0 16px 32px -8px rgba(0, 0, 0, 0.12)',
      }
    },
  },
  plugins: [],
};
