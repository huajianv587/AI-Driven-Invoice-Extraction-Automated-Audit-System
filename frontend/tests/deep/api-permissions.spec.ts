import { expect, request, test } from "@playwright/test";

import { getPorts, getRoleCredentials } from "../helpers/env";
import { apiGet, apiPost, expiredAccessToken, signInApi } from "./helpers";

test.describe.configure({ mode: "serial" });

test("API enforces auth lifecycle, role matrix, and OpenAPI contract", async () => {
  const { apiPort } = getPorts();
  const baseURL = `http://127.0.0.1:${apiPort}`;
  const rawApi = await request.newContext({ baseURL });

  const unauthenticated = await rawApi.get("/api/dashboard/summary");
  expect(unauthenticated.status()).toBe(401);

  const invalid = await rawApi.get("/api/dashboard/summary", {
    headers: { Authorization: "Bearer not-a-valid-token" }
  });
  expect(invalid.status()).toBe(401);

  const expired = await rawApi.get("/api/dashboard/summary", {
    headers: { Authorization: `Bearer ${expiredAccessToken("admin")}` }
  });
  expect(expired.status()).toBe(401);

  const inactive = await rawApi.post("/api/auth/login", {
    data: getRoleCredentials("inactive")
  });
  expect(inactive.status()).toBe(401);

  const openapi = await rawApi.get("/openapi.json");
  expect(openapi.ok()).toBeTruthy();
  const spec = await openapi.json();
  expect(spec.paths["/api/auth/login"]).toBeTruthy();
  expect(spec.paths["/api/auth/sessions"]).toBeTruthy();
  expect(spec.paths["/api/invoices/{invoice_id}/review"]).toBeTruthy();
  expect(spec.paths["/api/ops/feishu-sync/retry"]).toBeTruthy();

  const admin = await signInApi("admin");
  const reviewer = await signInApi("reviewer");
  const ops = await signInApi("ops");

  await expect((await apiGet(admin.api, "/api/dashboard/summary", admin.token)).ok()).toBeTruthy();
  const sessions = await apiGet(admin.api, "/api/auth/sessions", admin.token);
  expect(sessions.ok()).toBeTruthy();
  expect((await sessions.json()).length).toBeGreaterThan(0);
  await expect((await apiGet(reviewer.api, "/api/invoices?limit=5", reviewer.token)).ok()).toBeTruthy();
  await expect((await apiGet(ops.api, "/api/invoices/1", ops.token)).ok()).toBeTruthy();

  const reviewerOps = await apiGet(reviewer.api, "/api/ops/feishu-sync", reviewer.token);
  expect(reviewerOps.status()).toBe(403);

  const opsReview = await apiPost(ops.api, "/api/invoices/6/review", ops.token, {
    handler_user: "Ops User",
    handling_note: "Ops should not be allowed to write review decisions.",
    review_result: "NeedsReview"
  });
  expect(opsReview.status()).toBe(403);

  const reviewerReview = await apiPost(reviewer.api, "/api/invoices/6/review", reviewer.token, {
    handler_user: "Riley Reviewer",
    handling_note: "Reviewer role can submit a deterministic approval decision.",
    review_result: "Approved"
  });
  expect(reviewerReview.ok()).toBeTruthy();

  const detail = await apiGet(admin.api, "/api/invoices/6", admin.token);
  expect(detail.ok()).toBeTruthy();
  const detailJson = await detail.json();
  expect(detailJson.invoice.invoice_status).toBe("Approved");
  expect(detailJson.review_tasks[0].review_result).toBe("Approved");

  const restore = await apiPost(admin.api, "/api/invoices/6/review", admin.token, {
    handler_user: "Deep Reset",
    handling_note: "Restoring the deterministic review candidate after role matrix validation.",
    review_result: "Pending"
  });
  expect(restore.ok()).toBeTruthy();

  const logoutContext = await request.newContext({
    baseURL,
    extraHTTPHeaders: { "Content-Type": "application/json" }
  });
  const login = await logoutContext.post("/api/auth/login", {
    data: getRoleCredentials("admin")
  });
  expect(login.ok()).toBeTruthy();
  const logout = await logoutContext.post("/api/auth/logout");
  expect(logout.ok()).toBeTruthy();
  const meAfterLogout = await logoutContext.get("/api/auth/me");
  expect(meAfterLogout.status()).toBe(401);

  await Promise.all([
    admin.api.dispose(),
    reviewer.api.dispose(),
    ops.api.dispose(),
    rawApi.dispose(),
    logoutContext.dispose()
  ]);
});
