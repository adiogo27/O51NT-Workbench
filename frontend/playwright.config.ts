import { defineConfig } from "@playwright/test";
import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

const PORT = Number(process.env.E2E_PORT ?? 8059);
const ROOT = path.resolve(HERE, "..");
// Banco/dados isolados por execução: o E2E nunca toca em data/ do usuário.
const DATA_DIR = process.env.E2E_DATA_DIR ?? mkdtempSync(path.join(tmpdir(), "o51nt-e2e-"));

// Usa o Chromium do Playwright se instalado; senão o do sistema (Kali: /usr/bin/chromium).
const systemChromium = ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"].find(existsSync);
const executablePath = process.env.PW_CHROMIUM ?? (existsSync(path.join(process.env.HOME ?? "", ".cache/ms-playwright")) ? undefined : systemChromium);

export default defineConfig({
  testDir: "./tests",
  testIgnore: "unit/**",
  timeout: 30_000,
  fullyParallel: true,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    headless: true,
    launchOptions: executablePath ? { executablePath } : {},
  },
  webServer: {
    command: `"${ROOT}/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port ${PORT} --log-level warning`,
    cwd: path.join(ROOT, "backend"),
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: false,
    timeout: 30_000,
    env: {
      O51NT_DATA_DIR: DATA_DIR,
      O51NT_SCHEDULER_ENABLED: "false",
      O51NT_SEARXNG_URL: "http://127.0.0.1:9", // porta fechada: E2E não depende de rede
      O51NT_MODELS_DIR_OVERRIDE: path.join(ROOT, "data", "models"), // reaproveita os modelos de OCR já baixados (sem rede no E2E)
    },
  },
});
