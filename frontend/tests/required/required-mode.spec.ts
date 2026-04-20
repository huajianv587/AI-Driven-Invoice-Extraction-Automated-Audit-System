import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

import { repoRoot } from "../helpers/env";
import { apiGet, signInApi } from "../deep/helpers";

const reportPath = path.resolve(repoRoot, "artifacts", "required-mode", "latest.json");

test.describe.configure({ mode: "serial" });

test("required smoke report proves real integrations and preserves web access", async ({ page }) => {
  expect(fs.existsSync(reportPath)).toBeTruthy();
  const report = JSON.parse(fs.readFileSync(reportPath, "utf-8"));
  const scenarios = new Map<string, any>((report.scenarios ?? []).map((item: any) => [item.scenario, item]));

  expect(report.ok).toBeTruthy();
  expect(report.mode).toBe("required");
  expect(report.scenario_count).toBe(4);
  expect((report.preflight?.connector_statuses ?? []).map((row: any) => row.status)).toEqual(["OK", "OK", "OK", "OK"]);

  const success = scenarios.get("required_success");
  expect(success?.first?.action).toBe("inserted");
  expect(success?.duplicate?.action).toBe("skipped");
  expect(success?.invoice_id).toBeTruthy();
  expect(success?.invoice_count_for_source).toBe(1);
  expect(success?.email?.event_status).toBe("SENT");
  expect(success?.email?.message_count).toBe(1);
  expect(success?.email?.body_has_unique_hash).toBeTruthy();
  expect(success?.feishu?.record_id).toBeTruthy();
  expect(success?.feishu?.record_id_unchanged).toBeTruthy();
  expect(success?.feishu?.remote_unique_hash).toBe(success?.first?.unique_hash);

  const difyFailure = scenarios.get("required_dify_failure");
  expect(difyFailure?.invoice_count_for_source).toBe(0);

  const smtpFailure = scenarios.get("required_smtp_failure");
  expect(smtpFailure?.email_statuses).toEqual(["FAILED"]);
  expect(smtpFailure?.imap_message_count).toBe(0);

  const feishuFailure = scenarios.get("required_feishu_failure");
  expect(feishuFailure?.sync_error).toBeTruthy();
  expect(feishuFailure?.remote_record_readable).toBeFalsy();

  await page.goto("/app/dashboard");
  await expect(page.getByRole("heading", { name: "Mission Control" })).toBeVisible();

  await page.goto("/app/queue");
  await expect(page.getByRole("heading", { name: "Review Queue" })).toBeVisible();

  await page.goto(`/app/review/${success.invoice_id}`);
  await expect(page.getByRole("heading", { name: `Review Desk #${success.invoice_id}` })).toBeVisible();

  await page.goto("/app/ops");
  await expect(page.getByRole("heading", { name: "Operations Center" })).toBeVisible();
  await page.getByRole("button", { name: /Run live check/i }).click();
  for (const connectorName of ["OCR", "Dify", "Feishu", "SMTP"]) {
    await expect(page.getByText(connectorName, { exact: true })).toBeVisible();
  }
});

test("required ops connector refresh stays aligned with smoke preflight", async () => {
  const admin = await signInApi("admin");
  try {
    const report = JSON.parse(fs.readFileSync(reportPath, "utf-8"));
    const expectedStatuses = new Map<string, string>(
      (report.preflight?.connector_statuses ?? []).map((row: any) => [String(row.name), String(row.status)])
    );

    const response = await apiGet(admin.api, "/api/ops/connectors?refresh=true", admin.token);
    expect(response.ok()).toBeTruthy();
    const rows = await response.json();
    const actualStatuses = new Map<string, string>(rows.map((row: any) => [String(row.name), String(row.status)]));

    for (const connectorName of ["OCR", "Dify", "Feishu", "SMTP"]) {
      expect(actualStatuses.get(connectorName)).toBe(expectedStatuses.get(connectorName));
      expect(actualStatuses.get(connectorName)).toBe("OK");
    }
  } finally {
    await admin.api.dispose();
  }
});
