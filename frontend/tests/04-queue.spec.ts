import { expect, test } from "@playwright/test";

import { expectStableScreenshot, isMobileProject } from "./helpers/ui";

test("queue supports search, filtering, and invoice deep links", async ({ page }, testInfo) => {
  test.skip(isMobileProject(testInfo.project.name), "Queue visual baseline is desktop-only for v1.");

  await page.goto("/app/queue");
  await expect(page.getByRole("heading", { name: "Review Queue" })).toBeVisible();
  await expect(page.getByText("Atlas Components Ltd")).toBeVisible();

  await page.getByPlaceholder("Seller, buyer, invoice, or PO").fill("Quartz");
  await expect(page.getByText("Quartz Robotics")).toBeVisible();
  await page.getByRole("link", { name: "Details" }).first().click();
  await expect(page).toHaveURL(/\/app\/invoices\/3$/);
  await expect(page.getByRole("heading", { name: "Invoice #3" })).toBeVisible();

  await page.goto("/app/queue");
  await expectStableScreenshot(page, "queue-desktop.png");
});
