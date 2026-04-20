import { expect, test } from "@playwright/test";

import { expectStableScreenshot, isMobileProject } from "./helpers/ui";

test("landing page surfaces the premium finance message", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByText("Invoice evidence, risk review")).toBeVisible();
  await expect(page.getByRole("link", { name: /Open secure workspace/i })).toBeVisible();
  await expectStableScreenshot(page, isMobileProject(testInfo.project.name) ? "landing-mobile.png" : "landing-desktop.png");
});
