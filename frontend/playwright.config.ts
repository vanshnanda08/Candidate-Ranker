import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./browser", workers: 1, timeout: 90000,
  outputDir: process.env.TALENTLENS_BROWSER_OUTPUT ?? "/tmp/talentlens-browser-results",
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:5173", headless: true, actionTimeout: 10000,
    launchOptions: process.env.TALENTLENS_CHROME_PATH ? { executablePath: process.env.TALENTLENS_CHROME_PATH } : {},
    trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "desktop", use: { viewport: { width: 1440, height: 1000 } } },
    { name: "narrow", use: { viewport: { width: 390, height: 844 } } }],
  webServer: [
    { command: "HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ../.venv/bin/python -m uvicorn server:app --app-dir .. --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/api/health", timeout: 90000, reuseExistingServer: false },
    { command: "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort", url: "http://127.0.0.1:5173", reuseExistingServer: false },
  ],
});
