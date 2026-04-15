import { expect, test } from "@playwright/test";

import { getAdminCredentials } from "../helpers/env";

test("mobile shell keeps landing, login, and dashboard usable", async ({ context, page }) => {
  const { email, password } = getAdminCredentials();
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Enterprise-grade invoice operations/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /Open secure workspace/i })).toBeVisible();

  await context.clearCookies();
  await page.goto("/app/dashboard");
  await expect(page).toHaveURL(/\/login\?next=%2Fapp%2Fdashboard/);
  await expect(page.getByRole("heading", { name: /Enter your workspace/i })).toBeVisible();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /^Sign in$/i }).click();

  await expect(page.getByRole("heading", { name: "Mission Control" })).toBeVisible();
  await expect(page.getByText("Invoice Operations Suite")).toBeVisible();
});
