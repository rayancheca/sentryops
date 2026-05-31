import type { Config } from "tailwindcss";

/**
 * Operator/NOC dark console theme. Colors are driven by CSS custom properties
 * defined in app/globals.css so the palette stays in one place.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--color-bg)",
        surface: "var(--color-surface)",
        "surface-2": "var(--color-surface-2)",
        border: "var(--color-border)",
        muted: "var(--color-muted)",
        text: "var(--color-text)",
        "text-dim": "var(--color-text-dim)",
        accent: "var(--color-accent)",
        "accent-dim": "var(--color-accent-dim)",
        ok: "var(--color-ok)",
        warn: "var(--color-warn)",
        danger: "var(--color-danger)",
        critical: "var(--color-critical)",
        info: "var(--color-info)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: {
        card: "var(--radius-card)",
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.03) inset, 0 8px 24px -12px rgba(0,0,0,0.6)",
        glow: "0 0 0 1px var(--color-accent-dim), 0 0 24px -8px var(--color-accent)",
      },
      keyframes: {
        "pulse-dot": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "pulse-dot": "pulse-dot 1.6s ease-in-out infinite",
        "fade-in": "fade-in var(--duration-normal) var(--ease-out-expo)",
      },
    },
  },
  plugins: [],
};

export default config;
