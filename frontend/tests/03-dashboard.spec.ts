import { expect, test } from "@playwright/test";

import { expectStableScreenshot, isMobileProject } from "./helpers/ui";

test("dashboard renders deterministic operating posture", async ({ page }, testInfo) => {
  await page.goto("/app/dashboard");
  await expect(page.getByRole("heading", { name: "Mission Control" })).toBeVisible();
  await expect(page.getByText("Atlas Components Ltd")).toBeVisible();
  await expect(page.getByRole("link", { name: /Working slice Review Queue/i })).toBeVisible();
  await expectStableScreenshot(page, isMobileProject(testInfo.project.name) ? "dashboard-mobile.png" : "dashboard-desktop.png", {
    mask: [page.getByTestId("activity-day-label")],
    maskColor: "#071009"
  });
});
