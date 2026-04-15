import { expect, test } from "@playwright/test";

test.describe.configure({ mode: "serial" });

test("admin exercises queue filters, empty state, review validation, and ops retry", async ({ page }) => {
  await page.goto("/app/queue");
  await expect(page.getByRole("heading", { name: "Review Queue" })).toBeVisible();
  await expect(page.getByText("Atlas Components Ltd")).toBeVisible();

  await page.getByPlaceholder("Seller, buyer, invoice, or PO").fill("Quartz");
  await expect(page.getByText("Quartz Robotics")).toBeVisible();
  await expect(page.getByRole("link", { name: "Details" })).toHaveCount(1);

  await page.getByPlaceholder("Seller, buyer, invoice, or PO").fill("");
  await page.getByRole("checkbox", { name: /Risk only/i }).check();
  await page.locator("select").nth(1).selectOption("largest_delta");
  await expect(page.getByText("Atlas Components Ltd")).toBeVisible();

  await page.getByPlaceholder("Seller, buyer, invoice, or PO").fill("no-match-for-deep-test");
  await expect(page.getByText("No invoices match this view")).toBeVisible();

  await page.goto("/app/review/1");
  await expect(page.getByRole("heading", { name: "Review Desk #1" })).toBeVisible();
  await page.getByLabel("Handling note").fill("short");
  await page.getByRole("button", { name: /Submit review decision/i }).click();
  await expect(page.getByText("Add a meaningful handling note.")).toBeVisible();

  await page.getByLabel("Review result").selectOption("Rejected");
  await page.getByLabel("Handling note").fill("Rejected during deep functional validation because the overage needs PO correction.");
  await page.getByRole("button", { name: /Submit review decision/i }).click();
  await expect(page.getByText("Decision saved and audit trail updated.")).toBeVisible();

  await page.goto("/app/invoices/999999");
  await expect(page.getByRole("heading", { name: /Invoice unavailable/i })).toBeVisible();

  await page.goto("/app/ops");
  await expect(page.getByRole("heading", { name: "Operations Center" })).toBeVisible();
  const retryResponse = page.waitForResponse((response) =>
    response.url().includes("/api/ops/feishu-sync/retry") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /Retry failed syncs/i }).click();
  const response = await retryResponse;
  expect([200, 409, 422, 500]).toContain(response.status());
  await expect(page.getByText(/Replay (finished|failed):/)).toBeVisible();
});
