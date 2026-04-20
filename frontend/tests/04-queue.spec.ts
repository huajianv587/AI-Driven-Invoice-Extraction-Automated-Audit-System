import { expect, test } from "@playwright/test";

import { expectStableScreenshot, isMobileProject } from "./helpers/ui";

test("queue supports search, filtering, and invoice deep links", async ({ page }, testInfo) => {
  const sellerLocator = isMobileProject(testInfo.project.name)
    ? page.getByText("Atlas Components Ltd").first()
    : page.getByText("Atlas Components Ltd").last();
  const searchLocator = isMobileProject(testInfo.project.name)
    ? page.getByText("Quartz Robotics").first()
    : page.getByText("Quartz Robotics").last();

  await page.goto("/app/queue");
  await expect(page.getByRole("heading", { name: "Review Queue" })).toBeVisible();
  await expect(sellerLocator).toBeVisible();

  await page.getByPlaceholder("Seller, buyer, invoice, or PO").fill("Quartz");
  await expect(searchLocator).toBeVisible();
  await page.getByRole("link", { name: "Details" }).first().click();
  await expect(page).toHaveURL(/\/app\/invoices\/3$/);
  await expect(page.getByRole("heading", { name: "Invoice #3" })).toBeVisible();

  await page.goto("/app/queue");
  await expectStableScreenshot(page, isMobileProject(testInfo.project.name) ? "queue-mobile.png" : "queue-desktop.png");
});
