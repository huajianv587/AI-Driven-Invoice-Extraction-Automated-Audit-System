import { expect, test } from "@playwright/test";

import { getAdminCredentials } from "./helpers/env";
import { expectStableScreenshot, isMobileProject } from "./helpers/ui";

test("protected app routes redirect to login and then restore the target route", async ({ context, page }, testInfo) => {
  const { email, password } = getAdminCredentials();
  await context.clearCookies();

  await page.goto("/app/dashboard");
  await expect(page).toHaveURL(/\/login\?next=%2Fapp%2Fdashboard/);
  await expect(page.getByRole("heading", { name: /Enter your workspace/i })).toBeVisible();
  await expect(page.getByLabel("Email")).toHaveValue(email);
  await expectStableScreenshot(page, isMobileProject(testInfo.project.name) ? "login-mobile.png" : "login-desktop.png");

  await page.getByLabel("Password").fill(password);
  const loginResponse = page.waitForResponse((response) =>
    response.url().includes("/api/auth/login") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /^Sign in$/i }).click();
  expect((await loginResponse).ok()).toBeTruthy();
  await expect(page).toHaveURL(/\/app\/dashboard$/, { timeout: 30000 });
  await expect(page.getByRole("heading", { name: "Mission Control" })).toBeVisible();
});
