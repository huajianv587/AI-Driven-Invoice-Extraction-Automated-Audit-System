import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

import { applyRootEnvToProcess, authFile, getPorts, repoRoot } from "./tests/helpers/env";

applyRootEnvToProcess();

const { frontendPort, stackPort } = getPorts();
const baseURL = `http://localhost:${frontendPort}`;
const pythonPath = (() => {
  const candidate = path.join(repoRoot, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  return fs.existsSync(candidate) ? candidate : "python";
})();
const stackScript = path.join(repoRoot, "scripts", "run_web_e2e_stack.py");
const quote = (value: string) => `"${value.replace(/"/g, '\\"')}"`;

export default defineConfig({
  testDir: "./tests",
  timeout: 90000,
  workers: 1,
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report", open: "never" }]
  ],
  expect: {
    timeout: 12000,
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.02,
      threshold: 0.2
    }
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
    timeout: 360000,
    reuseExistingServer: !process.env.CI && process.env.REUSE_E2E_STACK !== "0"
  },
  projects: [
    {
      name: "setup",
      testMatch: /(^|[\\/])tests[\\/]auth\.setup\.ts$/,
      use: { baseURL }
    },
    {
      name: "desktop-chromium",
      dependencies: ["setup"],
      testIgnore: [/auth\.setup\.ts/, /deep[\\/]/],
      use: {
        ...devices["Desktop Chrome"],
        baseURL,
        storageState: authFile,
        viewport: { width: 1440, height: 1100 }
      }
    },
    {
      name: "mobile-chromium",
      dependencies: ["setup"],
      testIgnore: [/auth\.setup\.ts/, /deep[\\/]/],
      use: {
        ...devices["Pixel 5"],
        baseURL,
        browserName: "chromium",
        storageState: authFile
      }
    }
  ]
});
