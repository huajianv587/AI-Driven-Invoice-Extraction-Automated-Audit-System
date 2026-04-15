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
        soft: "0 24px 60px rgba(15, 23, 42, 0.08)",
        focus: "0 18px 40px rgba(39, 94, 255, 0.16)"
      },
      colors: {
        ink: "#0f172a",
        slate: "#5f6f89",
        canvas: "#f4f7fb",
        line: "#d7e1ef",
        brand: "#335cff",
        brandSoft: "#eff3ff",
        mint: "#0f9d8a",
        amber: "#b7791f",
        rose: "#c15372"
      }
    }
  },
  plugins: []
};

export default config;
