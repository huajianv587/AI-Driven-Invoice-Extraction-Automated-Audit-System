import { expect, test } from "@playwright/test";

import { clearAuditDirectory, invoiceIds, isMobileProject, saveAuditScreenshot } from "./helpers/ui";

test.describe.configure({ mode: "serial" });

test.beforeAll(({}, testInfo) => {
  if (!isMobileProject(testInfo.project.name)) {
    clearAuditDirectory();
  }
});

test("capture manual UI audit screenshots", async ({ context, page }, testInfo) => {
  const suffix = isMobileProject(testInfo.project.name) ? "mobile" : "desktop";
  const pages = [
    { path: "/", name: `landing-${suffix}.png`, heading: /Invoice evidence, risk review/i, marker: /Open secure workspace/i },
    { path: "/login", name: `login-${suffix}.png`, heading: /Enter your workspace/i, marker: /Sign in/i },
    { path: "/app/dashboard", name: `dashboard-${suffix}.png`, heading: "Mission Control", marker: "Atlas Components Ltd" },
    { path: "/app/control-room", name: `control-room-${suffix}.png`, heading: "Control Room", marker: "Recent intake history" },
    { path: "/app/queue", name: `queue-${suffix}.png`, heading: "Review Queue", marker: "Quartz Robotics" },
    { path: `/app/review/${invoiceIds.pendingRisk}`, name: `review-${suffix}.png`, heading: `Review Desk #${invoiceIds.pendingRisk}`, marker: "Atlas Components Ltd" },
    { path: "/app/ops", name: `ops-${suffix}.png`, heading: "Operations Center", marker: "Read-only demo" }
  ];

  for (const item of pages) {
    await context.clearCookies();
    await page.goto(item.path);
    await expect(page.getByRole("heading", { name: item.heading })).toBeVisible();
    if (item.path === "/login") {
      await expect(page.getByRole("button", { name: /^Sign in$/i })).toBeVisible();
    } else if (item.path === "/app/control-room") {
      await expect(page.getByText("Recent intake history")).toBeVisible();
    } else if (item.path === "/app/queue") {
      await expect(page.getByRole("link", { name: "Details" }).first()).toBeVisible();
    } else {
      await expect(page.getByText(item.marker).first()).toBeVisible();
    }
    await saveAuditScreenshot(page, item.name);
  }
});
