import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

import { applyRootEnvToProcess, getPorts, repoRoot, roleAuthFile } from "./tests/helpers/env";

applyRootEnvToProcess({
  skipKeys: ["APP_ENV", "ALLOW_REAL_INTEGRATION_TESTS", "WEB_DEEP_RESET_DEMO_DB", "WEB_DEEP_CONFIRM"]
});

const { frontendPort } = getPorts();
const stackPort = Number(process.env.PLAYWRIGHT_DEEP_STACK_PORT || process.env.PLAYWRIGHT_STACK_PORT || 3411);
const baseURL = `http://localhost:${frontendPort}`;
const pythonPath = (() => {
  const candidate = path.join(repoRoot, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  return fs.existsSync(candidate) ? candidate : "python";
})();
const stackScript = path.join(repoRoot, "scripts", "run_web_deep_stack.py");
const quote = (value: string) => `"${value.replace(/"/g, '\\"')}"`;

export default defineConfig({
  testDir: "./tests",
  timeout: 180000,
  workers: 1,
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report-deep", open: "never" }]
  ],
  expect: {
    timeout: 15000,
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
    timeout: 900000,
    reuseExistingServer: !process.env.CI && process.env.REUSE_DEEP_STACK !== "0"
  },
  projects: [
    {
      name: "deep-setup",
      testMatch: /deep\/auth\.setup\.ts/,
      use: { baseURL }
    },
    {
      name: "deep-visual-desktop",
      dependencies: ["deep-setup"],
      testMatch: /deep\/visual\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        baseURL,
        storageState: roleAuthFile("admin"),
        viewport: { width: 1440, height: 1100 }
      }
    },
    {
      name: "deep-visual-mobile",
      dependencies: ["deep-setup"],
      testMatch: /deep\/visual\.spec\.ts/,
      use: {
        ...devices["Pixel 5"],
        baseURL,
        browserName: "chromium",
        storageState: roleAuthFile("admin")
      }
    },
    {
      name: "deep-admin-desktop",
      dependencies: ["deep-setup"],
      testMatch: [/deep\/api-permissions\.spec\.ts/, /deep\/admin-flow\.spec\.ts/, /deep\/closed-loop\.spec\.ts/],
      use: {
        ...devices["Desktop Chrome"],
        baseURL,
        storageState: roleAuthFile("admin"),
        viewport: { width: 1440, height: 1100 }
      }
    },
    {
      name: "deep-reviewer-desktop",
      dependencies: ["deep-setup"],
      testMatch: /deep\/reviewer-role\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        baseURL,
        storageState: roleAuthFile("reviewer"),
        viewport: { width: 1440, height: 1000 }
      }
    },
    {
      name: "deep-ops-desktop",
      dependencies: ["deep-setup"],
      testMatch: /deep\/ops-role\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        baseURL,
        storageState: roleAuthFile("ops"),
        viewport: { width: 1440, height: 1000 }
      }
    },
    {
      name: "deep-admin-mobile",
      dependencies: ["deep-setup"],
      testMatch: /deep\/mobile-shell\.spec\.ts/,
      use: {
        ...devices["Pixel 5"],
        baseURL,
        browserName: "chromium",
        storageState: roleAuthFile("admin")
      }
    }
  ]
});
