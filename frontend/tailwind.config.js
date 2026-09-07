/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter Variable",
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        // Near-black ground, tuned off the Argus radial gradient stops.
        ink: {
          950: "#050506",
          900: "#0a0b0e",
          850: "#0e0f13",
          800: "#14151a",
          750: "#191b21",
          700: "#20222a",
          600: "#2b2e38",
          500: "#3b3f4c",
          400: "#5b6070",
          300: "#8b90a0",
          200: "#c4c8d4",
          100: "#e7e9f0",
        },
        // Electric-cyan accent — surveillance/HUD console on the near-black
        // ground. Kept clear of the semantic signal hues below.
        accent: {
          300: "#67e8f9",
          400: "#22d3ee",
          500: "#06b6d4",
          600: "#0891b2",
        },
        // Electric-blue secondary, for a two-tone highlight where cyan alone
        // would read flat (route endpoints, impossible-travel, audit lookups).
        spark: {
          500: "#3b82f6",
        },
        // Semantic signal colors for badges / congestion / severity.
        signal: {
          critical: "#fb5b6b",
          high: "#ff8f4c",
          medium: "#ffcc4d",
          low: "#5cd0c0",
          ok: "#4ade80",
          info: "#22d3ee",
        },
      },
      boxShadow: {
        glass:
          "0 8px 32px rgba(0,0,0,0.45), inset 0 1px rgba(255,255,255,0.08)",
        "glass-hover":
          "0 12px 40px rgba(0,0,0,0.55), 0 0 30px rgba(34,211,238,0.18), inset 0 1px rgba(255,255,255,0.10)",
        glow: "0 0 24px rgba(34,211,238,0.30)",
      },
      transitionTimingFunction: {
        silk: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-down": {
          "0%": { opacity: "0", transform: "translateY(-6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(0.8)", opacity: "0.7" },
          "70%": { transform: "scale(2.2)", opacity: "0" },
          "100%": { opacity: "0" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.4s cubic-bezier(0.16,1,0.3,1) both",
        "fade-down": "fade-down 0.35s cubic-bezier(0.16,1,0.3,1) both",
        "pulse-ring": "pulse-ring 2.4s cubic-bezier(0.16,1,0.3,1) infinite",
        shimmer: "shimmer 1.6s infinite",
      },
    },
  },
  plugins: [],
};
