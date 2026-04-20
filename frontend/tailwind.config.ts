import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      boxShadow: {
        soft: "0 18px 48px rgba(0, 0, 0, 0.38)",
        focus: "0 0 0 1px rgba(0, 255, 136, 0.32), 0 0 28px rgba(0, 255, 136, 0.16)"
      },
      colors: {
        ink: "#f2fff8",
        slate: "rgba(210, 230, 220, 0.62)",
        canvas: "#030503",
        line: "rgba(0, 255, 136, 0.14)",
        brand: "#00ff88",
        brandSoft: "rgba(0, 255, 136, 0.10)",
        mint: "#36f3b4",
        amber: "#ffbf47",
        rose: "#ff4d66"
      }
    }
  },
  plugins: []
};

export default config;
