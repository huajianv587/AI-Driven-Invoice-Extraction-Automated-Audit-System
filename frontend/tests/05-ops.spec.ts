import { expect, test } from "@playwright/test";

import { expectStableScreenshot, isMobileProject } from "./helpers/ui";

test("ops center shows connector posture and replay controls", async ({ page }, testInfo) => {
  test.skip(isMobileProject(testInfo.project.name), "Ops visual baseline is desktop-only for v1.");

  await page.goto("/app/ops");
  await expect(page.getByRole("heading", { name: "Operations Center" })).toBeVisible();
  await expect(page.getByText("Connector mesh")).toBeVisible();
  await expect(page.getByText("Demo connector rate limit")).toBeVisible();

  const retryResponse = page.waitForResponse((response) =>
    response.url().includes("/api/ops/feishu-sync/retry") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /Retry failed syncs/i }).click();
  await expect((await retryResponse).ok()).toBeTruthy();
  await expect(page.getByText(/Replay finished:/)).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: "Operations Center" })).toBeVisible();
  await expectStableScreenshot(page, "ops-desktop.png");
});
