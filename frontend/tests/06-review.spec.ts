import { expect, request, test } from "@playwright/test";

import { getPorts } from "./helpers/env";
import { cookieHeader, expectStableScreenshot, invoiceIds, isMobileProject } from "./helpers/ui";

test("review desk submits a decision and exposes DB-backed audit state", async ({ context, page }, testInfo) => {
  test.skip(isMobileProject(testInfo.project.name), "Review visual baseline is desktop-only for v1.");

  await page.goto(`/app/review/${invoiceIds.reviewCandidate}`);
  await expect(page.getByRole("heading", { name: `Review Desk #${invoiceIds.reviewCandidate}` })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Northstar Calibration" })).toBeVisible();
  await expectStableScreenshot(page, "review-desktop.png");

  await page.getByLabel("Review result").selectOption("Approved");
  await page.getByLabel("Handling note").fill("Approved after calibration overage was matched to the amended purchase order.");
  await page.getByRole("button", { name: /Submit review decision/i }).click();
  await expect(page.getByText("Decision saved and audit trail updated.")).toBeVisible();

  const { apiPort } = getPorts();
  const api = await request.newContext({
    baseURL: `http://127.0.0.1:${apiPort}`,
    extraHTTPHeaders: {
      Cookie: await cookieHeader(context)
    }
  });
  const me = await api.get("/api/auth/me");
  expect(me.ok()).toBeTruthy();
  const session = await me.json();
  const response = await api.get(`/api/invoices/${invoiceIds.reviewCandidate}`, {
    headers: {
      Authorization: `Bearer ${session.access_token}`
    }
  });
  expect(response.ok()).toBeTruthy();
  const detail = await response.json();
  expect(detail.invoice.invoice_status).toBe("Approved");
  expect(detail.review_tasks[0].review_result).toBe("Approved");
  expect(detail.events.some((event: { event_type: string; event_status: string }) =>
    event.event_type === "WORK_ORDER_SUBMITTED" && event.event_status === "Approved"
  )).toBeTruthy();
  const restore = await api.post(`/api/invoices/${invoiceIds.reviewCandidate}/review`, {
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      "Content-Type": "application/json"
    },
    data: {
      handler_user: "E2E Reset",
      handling_note: "Resetting the deterministic review candidate for downstream visual baselines.",
      review_result: "Pending"
    }
  });
  expect(restore.ok()).toBeTruthy();
  await api.dispose();
});
