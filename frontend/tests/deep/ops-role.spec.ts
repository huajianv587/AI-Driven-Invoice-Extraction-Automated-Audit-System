import { expect, test } from "@playwright/test";

test("ops can operate recovery surfaces with read-only review access", async ({ page }) => {
  await page.goto("/app/dashboard");
  await expect(page.getByText("Owen Operator")).toBeVisible();
  await expect(page.getByRole("link", { name: /Ops Center/i })).toBeVisible();

  await page.goto("/app/ops");
  await expect(page.getByRole("heading", { name: "Operations Center" })).toBeVisible();
  await expect(page.getByText("Connector mesh")).toBeVisible();
  await expect(page.getByText("Demo connector rate limit")).toBeVisible();

  await page.goto("/app/review/1");
  await expect(page.getByRole("heading", { name: "Review Desk #1" })).toBeVisible();
  await expect(page.getByText("Read-only review access")).toBeVisible();
  await expect(page.getByRole("button", { name: /Submit review decision/i })).toHaveCount(0);
});
