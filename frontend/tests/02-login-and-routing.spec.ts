import { expect, request, test } from "@playwright/test";

import { getAdminCredentials, getPorts, getRefreshCookieName } from "./helpers/env";
import { expectStableScreenshot, invoiceIds, isMobileProject } from "./helpers/ui";

test("public demo opens the workspace without forcing login", async ({ context, page }, testInfo) => {
  const { email, password } = getAdminCredentials();
  await context.clearCookies();

  await page.goto("/app/dashboard");
  await expect(page).toHaveURL(/\/app\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Mission Control" })).toBeVisible();
  await expect(page.getByText("Public Demo").first()).toBeVisible();

  await page.goto("/login");
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
  await expect(page.getByText("Public Demo")).toHaveCount(0);
});

test("stale refresh cookies still fall back to public demo workspace", async ({ context, page }) => {
  const { frontendPort } = getPorts();
  await context.clearCookies();
  await context.addCookies([
    {
      name: getRefreshCookieName(),
      value: "stale-session-token",
      url: `http://localhost:${frontendPort}`
    }
  ]);

  await page.goto("/app/dashboard");
  await expect(page).toHaveURL(/\/app\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Mission Control" })).toBeVisible();
  await expect(page.getByText("Public Demo").first()).toBeVisible();
});

test("public demo can read pages but cannot write review decisions", async ({ context, page }) => {
  await context.clearCookies();
  await page.goto(`/app/review/${invoiceIds.pendingRisk}`);
  await expect(page.getByRole("heading", { name: `Review Desk #${invoiceIds.pendingRisk}` })).toBeVisible();
  await expect(page.getByRole("button", { name: /Submit review decision/i })).toHaveCount(0);

  const { apiPort } = getPorts();
  const api = await request.newContext({ baseURL: `http://127.0.0.1:${apiPort}` });
  const response = await api.post(`/api/invoices/${invoiceIds.pendingRisk}/review`, {
    data: {
      handler_user: "Public Demo",
      handling_note: "Anonymous write attempts must stay blocked.",
      review_result: "NeedsReview"
    }
  });
  expect([401, 403]).toContain(response.status());
  await api.dispose();
});
