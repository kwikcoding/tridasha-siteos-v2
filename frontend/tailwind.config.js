/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: "#1f2a44", 50: "#f3f5f9", 100: "#e3e8f1", 600: "#2c3a5c", 700: "#1f2a44", 900: "#121a2c" },
        gold: { DEFAULT: "#b8892b", 50: "#fbf6ea", 100: "#f4e7c6", 500: "#b8892b", 600: "#9a7121" },
      },
      fontFamily: { sans: ["Inter", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
};
