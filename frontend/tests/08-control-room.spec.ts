import { expect, test } from "@playwright/test";

import { expectStableScreenshot, isMobileProject } from "./helpers/ui";

test("control room exposes readiness, intake, and alert shortcuts", async ({ page }, testInfo) => {
  await page.goto("/app/control-room");
  await expect(page.getByRole("heading", { name: "Control Room" })).toBeVisible();
  await expect(page.getByText("Readiness wall")).toBeVisible();
  await expect(page.getByText("Current intake queue", { exact: true })).toBeVisible();
  await expect(page.getByText("Recent intake history", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Choose files/i })).toBeVisible();
  await expectStableScreenshot(page, isMobileProject(testInfo.project.name) ? "control-room-mobile.png" : "control-room-desktop.png");
});
