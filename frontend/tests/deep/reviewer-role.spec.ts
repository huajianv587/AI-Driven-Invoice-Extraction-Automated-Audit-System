import { expect, test } from "@playwright/test";

import { expectAccessDenied } from "./helpers";

test("reviewer can review invoices but cannot enter ops controls", async ({ page }) => {
  await page.goto("/app/dashboard");
  await expect(page.getByText("Riley Reviewer")).toBeVisible();
  await expect(page.getByRole("link", { name: "Review Queue", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Ops Center", exact: true })).toHaveCount(0);

  await page.goto("/app/ops");
  await expectAccessDenied(page);

  await page.goto("/app/review/6");
  await expect(page.getByRole("heading", { name: "Review Desk #6" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Submit review decision/i })).toBeVisible();
  await page.getByLabel("Review result").selectOption("NeedsReview");
  await page.getByLabel("Handling note").fill("Reviewer can move this case back to needs-review for deep role validation.");
  await page.getByRole("button", { name: /Submit review decision/i }).click();
  await expect(page.getByText("Decision saved and audit trail updated.")).toBeVisible();
});
