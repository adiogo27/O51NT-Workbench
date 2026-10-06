import type { Config } from "tailwindcss";

const v = (name: string) => `var(--color-${name})`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: v("background"),
        foreground: v("foreground"),
        primary: { DEFAULT: v("primary"), foreground: v("primary-foreground") },
        secondary: { DEFAULT: v("secondary"), foreground: v("secondary-foreground") },
        accent: { DEFAULT: v("accent"), foreground: v("accent-foreground") },
        muted: { DEFAULT: v("muted"), foreground: v("muted-foreground") },
        border: v("border"),
        danger: v("danger"),
        warning: v("warning"),
        success: v("success"),
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) * 0.75)",
        sm: "calc(var(--radius) * 0.5)",
      },
      fontFamily: { sans: "var(--font-family)", mono: ['"JetBrains Mono"', "ui-monospace", "monospace"] },
    },
  },
  plugins: [],
} satisfies Config;
