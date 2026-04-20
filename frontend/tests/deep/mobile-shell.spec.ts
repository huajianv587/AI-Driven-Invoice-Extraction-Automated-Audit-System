import { expect, test } from "@playwright/test";

test("mobile shell keeps landing, login, and dashboard usable", async ({ context, page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Invoice evidence, risk review/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /Open secure workspace/i })).toBeVisible();

  await context.clearCookies();
  await page.goto("/app/dashboard");
  await expect(page).toHaveURL(/\/app\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Mission Control" })).toBeVisible();
  await expect(page.getByText("Public Demo").first()).toBeVisible();
  await page.getByRole("button", { name: /Open navigation/i }).click();
  await expect(page.getByRole("link", { name: "Control Room" })).toBeVisible();
  await page.getByRole("link", { name: "Control Room" }).click();
  await expect(page.getByRole("heading", { name: "Control Room" })).toBeVisible();

  await page.goto("/login");
  await expect(page.getByRole("heading", { name: /Enter your workspace/i })).toBeVisible();
});
