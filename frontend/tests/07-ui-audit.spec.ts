import { expect, test } from "@playwright/test";

import { getAdminCredentials } from "./helpers/env";
import { clearAuditDirectory, invoiceIds, isMobileProject, saveAuditScreenshot } from "./helpers/ui";

test.describe.configure({ mode: "serial" });

test.beforeAll(({}, testInfo) => {
  if (!isMobileProject(testInfo.project.name)) {
    clearAuditDirectory();
  }
});

test("capture manual UI audit screenshots", async ({ context, page }, testInfo) => {
  const { email, password } = getAdminCredentials();
  const suffix = isMobileProject(testInfo.project.name) ? "mobile" : "desktop";
  const pages = [
    { path: "/", name: `landing-${suffix}.png`, heading: /Enterprise-grade invoice operations/i, marker: /Open secure workspace/i },
    { path: "/login", name: `login-${suffix}.png`, heading: /Enter your workspace/i, marker: /Sign in/i },
    { path: "/app/dashboard", name: `dashboard-${suffix}.png`, heading: "Mission Control", marker: "Atlas Components Ltd" }
  ];

  if (!isMobileProject(testInfo.project.name)) {
    pages.push(
      { path: "/app/queue", name: "queue-desktop.png", heading: "Review Queue", marker: "Quartz Robotics" },
      { path: `/app/review/${invoiceIds.pendingRisk}`, name: "review-desktop.png", heading: `Review Desk #${invoiceIds.pendingRisk}`, marker: "Atlas Components Ltd" },
      { path: "/app/ops", name: "ops-desktop.png", heading: "Operations Center", marker: "Demo connector rate limit" }
    );
  }

  for (const item of pages) {
    if (item.path === "/login") {
      await context.clearCookies();
    }
    await page.goto(item.path);
    await expect(page.getByRole("heading", { name: item.heading })).toBeVisible();
    if (item.path === "/login") {
      await expect(page.getByRole("button", { name: /^Sign in$/i })).toBeVisible();
    } else {
      await expect(page.getByText(item.marker).first()).toBeVisible();
    }
    await saveAuditScreenshot(page, item.name);
    if (item.path === "/login") {
      await page.getByLabel("Email").fill(email);
      await page.getByLabel("Password").fill(password);
      await page.getByRole("button", { name: /^Sign in$/i }).click();
      await expect(page.getByRole("heading", { name: "Mission Control" })).toBeVisible();
    }
  }
});
