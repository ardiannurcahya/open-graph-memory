/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      colors: {
        ui: {
          canvas: "var(--ui-canvas)", surface: "var(--ui-surface)", muted: "var(--ui-muted)", raised: "var(--ui-raised)", text: "var(--ui-text)", subdued: "var(--ui-subdued)", border: "var(--ui-border)", focus: "var(--ui-focus)", primary: "var(--ui-primary)", "primary-hover": "var(--ui-primary-hover)", danger: "var(--ui-danger)", "danger-bg": "var(--ui-danger-bg)", success: "var(--ui-success)", "success-bg": "var(--ui-success-bg)", warning: "var(--ui-warning)", "warning-bg": "var(--ui-warning-bg)", inverse: "var(--ui-inverse-text)",
        },
      },
    },
  },
  plugins: [],
};
