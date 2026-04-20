import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

import { applyRootEnvToProcess, authFile, getPorts, repoRoot } from "./tests/helpers/env";

applyRootEnvToProcess({
  skipKeys: [
    "APP_ENV",
    "ALLOW_REAL_INTEGRATION_TESTS",
    "WEB_DEEP_RESET_DEMO_DB",
    "WEB_DEEP_CONFIRM",
    "DIFY_REQUIRED",
    "FEISHU_SYNC_REQUIRED",
    "FEISHU_SYNC_MODE",
    "EMAIL_ALERT_REQUIRED"
  ]
});

const { frontendPort } = getPorts();
const stackPort = Number(process.env.PLAYWRIGHT_REQUIRED_STACK_PORT || process.env.PLAYWRIGHT_STACK_PORT || 3412);
const baseURL = `http://localhost:${frontendPort}`;
const pythonPath = (() => {
  const candidate = path.join(repoRoot, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  return fs.existsSync(candidate) ? candidate : "python";
})();
const stackScript = path.join(repoRoot, "scripts", "run_web_required_stack.py");
const quote = (value: string) => `"${value.replace(/"/g, '\\"')}"`;

export default defineConfig({
  testDir: "./tests",
  timeout: 180000,
  workers: 1,
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report-required", open: "never" }]
  ],
  expect: {
    timeout: 15000
  },
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure"
  },
  webServer: {
    command: `${quote(pythonPath)} ${quote(stackScript)}`,
    url: `http://127.0.0.1:${stackPort}/healthz`,
    timeout: 900000,
    reuseExistingServer: !process.env.CI && process.env.REUSE_REQUIRED_STACK !== "0"
  },
  projects: [
    {
      name: "required-setup",
      testMatch: /(^|[\\/])tests[\\/]auth\.setup\.ts$/,
      use: { baseURL }
    },
    {
      name: "required-admin-desktop",
      dependencies: ["required-setup"],
      testMatch: /required[\\/].*\.spec\.ts$/,
      use: {
        ...devices["Desktop Chrome"],
        baseURL,
        storageState: authFile,
        viewport: { width: 1440, height: 1100 }
      }
    }
  ]
});
