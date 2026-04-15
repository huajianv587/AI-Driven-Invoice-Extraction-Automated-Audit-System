import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

import { repoRoot } from "../helpers/env";

test("deep ingestion report proves OCR, duplicate, email retry, and fallback loops", async ({ page }) => {
  const reportPath = path.resolve(repoRoot, "artifacts", "deep-regression", "latest.json");
  expect(fs.existsSync(reportPath)).toBeTruthy();
  const report = JSON.parse(fs.readFileSync(reportPath, "utf-8"));

  expect(report.scenario_count).toBe(4);
  const scenarios = new Map<string, any>(report.scenarios.map((item: any) => [item.scenario, item]));
  expect(scenarios.get("cc_and_duplicate")?.second?.action).toBe("skipped");
  expect(scenarios.get("concurrent_reentry")?.actions).toEqual(["inserted", "skipped"]);
  expect(scenarios.get("retry_after_email_failure")?.email_statuses).toEqual(["FAILED", "SENT"]);
  expect(scenarios.get("dify_fallback")?.item_count).toBeGreaterThan(0);

  await page.goto("/app/dashboard");
  await expect(page.getByRole("heading", { name: "Mission Control" })).toBeVisible();
  await expect(page.getByText("Atlas Components Ltd")).toBeVisible();
});
