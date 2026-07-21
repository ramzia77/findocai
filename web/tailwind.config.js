/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        // Restrained fintech accent -- deep emerald, used sparingly for
        // primary actions/success states, never as a broad wash.
        accent: {
          50: "#ECF6F1",
          100: "#D3EAE0",
          200: "#A8D5C1",
          300: "#7BBFA1",
          400: "#4A9F7C",
          500: "#0F7A5C",
          600: "#0C6249",
          700: "#0A4F3B",
        },
      },
    },
  },
  plugins: [],
};
