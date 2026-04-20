import { expect, test } from "@playwright/test";

import { getAdminCredentials } from "../helpers/env";
import { expectStableScreenshot, isMobileProject } from "../helpers/ui";

test("deep visual baseline covers public, auth, and workspace shells", async ({ context, page }, testInfo) => {
  const { email, password } = getAdminCredentials();
  const mobile = isMobileProject(testInfo.project.name);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Invoice evidence, risk review/i })).toBeVisible();
  await expectStableScreenshot(page, mobile ? "deep-landing-mobile.png" : "deep-landing-desktop.png");

  await context.clearCookies();
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: /Enter your workspace/i })).toBeVisible();
  await expectStableScreenshot(page, mobile ? "deep-login-mobile.png" : "deep-login-desktop.png");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /^Sign in$/i }).click();
  await expect(page.getByRole("heading", { name: "Mission Control" })).toBeVisible();

  if (mobile) {
    await expectStableScreenshot(page, "deep-dashboard-mobile.png", {
      mask: [page.getByTestId("activity-day-label")],
      maskColor: "#071009"
    });
    await page.goto("/app/control-room");
    await expect(page.getByRole("heading", { name: "Control Room" })).toBeVisible();
    await expectStableScreenshot(page, "deep-control-room-mobile.png");
    return;
  }

  await page.goto("/app/dashboard");
  await expect(page.getByRole("heading", { name: "Mission Control" })).toBeVisible();
  await expectStableScreenshot(page, "deep-dashboard-desktop.png", {
    mask: [page.getByTestId("activity-day-label")],
    maskColor: "#071009"
  });

  await page.goto("/app/queue");
  await expect(page.getByRole("heading", { name: "Review Queue" })).toBeVisible();
  await expectStableScreenshot(page, "deep-queue-desktop.png");

  await page.goto("/app/review/1");
  await expect(page.getByRole("heading", { name: "Review Desk #1" })).toBeVisible();
  await expectStableScreenshot(page, "deep-review-desktop.png");

  await page.goto("/app/ops");
  await expect(page.getByRole("heading", { name: "Operations Center" })).toBeVisible();
  await expectStableScreenshot(page, "deep-ops-desktop.png");

  await page.goto("/app/control-room");
  await expect(page.getByRole("heading", { name: "Control Room" })).toBeVisible();
  await expectStableScreenshot(page, "deep-control-room-desktop.png");
});
