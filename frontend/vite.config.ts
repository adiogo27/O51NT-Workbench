/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  build: { outDir: "../backend/static", emptyOutDir: true, chunkSizeWarningLimit: 800 },
  test: { include: ["tests/unit/**/*.test.ts"], environment: "node" },
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8051" } },
});
