import { Buffer } from "node:buffer";
import { expect, request, test } from "@playwright/test";

import { getPorts, getRoleCredentials } from "../helpers/env";
import { apiDelete, apiGet, apiPost, expiredAccessToken, signInApi } from "./helpers";

test.describe.configure({ mode: "serial" });

test("API enforces auth lifecycle, role matrix, and OpenAPI contract", async () => {
  const { apiPort } = getPorts();
  const baseURL = `http://127.0.0.1:${apiPort}`;
  const rawApi = await request.newContext({ baseURL });

  const unauthenticated = await rawApi.get("/api/dashboard/summary");
  expect(unauthenticated.ok()).toBeTruthy();

  const unauthenticatedWrite = await rawApi.post("/api/invoices/6/review", {
    data: {
      handler_user: "Public Demo",
      handling_note: "Anonymous write attempts must stay blocked.",
      review_result: "NeedsReview"
    }
  });
  expect([401, 403]).toContain(unauthenticatedWrite.status());

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
  expect(spec.paths["/api/ops/control-room"]).toBeTruthy();
  expect(spec.paths["/api/ops/intake/uploads"]).toBeTruthy();
  expect(spec.paths["/api/ops/intake/upload"]).toBeTruthy();

  const admin = await signInApi("admin");
  const extraAdminSession = await signInApi("admin");
  const reviewer = await signInApi("reviewer");
  const ops = await signInApi("ops");

  await expect((await apiGet(admin.api, "/api/dashboard/summary", admin.token)).ok()).toBeTruthy();
  await expect((await apiGet(admin.api, "/api/ops/control-room", admin.token)).ok()).toBeTruthy();
  await expect((await apiGet(admin.api, "/api/ops/intake/uploads", admin.token)).ok()).toBeTruthy();
  const sessions = await apiGet(admin.api, "/api/auth/sessions", admin.token);
  expect(sessions.ok()).toBeTruthy();
  const sessionRows = await sessions.json();
  expect(sessionRows.length).toBeGreaterThan(0);
  const revocableSession = sessionRows.find((session: any) => !session.is_current);
  expect(revocableSession).toBeTruthy();
  const revokeSession = await apiDelete(admin.api, `/api/auth/sessions/${revocableSession.id}`, admin.token);
  expect(revokeSession.ok()).toBeTruthy();
  const sessionsAfterRevoke = await apiGet(admin.api, "/api/auth/sessions", admin.token);
  const sessionRowsAfterRevoke = await sessionsAfterRevoke.json();
  expect(sessionRowsAfterRevoke.find((session: any) => session.id === revocableSession.id)?.revoked_at).toBeTruthy();
  await expect((await apiGet(reviewer.api, "/api/invoices?limit=5", reviewer.token)).ok()).toBeTruthy();
  await expect((await apiGet(ops.api, "/api/invoices/1", ops.token)).ok()).toBeTruthy();

  const reviewerOps = await apiGet(reviewer.api, "/api/ops/feishu-sync", reviewer.token);
  expect(reviewerOps.status()).toBe(403);
  const reviewerControlRoom = await apiGet(reviewer.api, "/api/ops/control-room", reviewer.token);
  expect(reviewerControlRoom.status()).toBe(403);
  const reviewerUploads = await apiGet(reviewer.api, "/api/ops/intake/uploads", reviewer.token);
  expect(reviewerUploads.status()).toBe(403);

  const opsReview = await apiPost(ops.api, "/api/invoices/6/review", ops.token, {
    handler_user: "Ops User",
    handling_note: "Ops should not be allowed to write review decisions.",
    review_result: "NeedsReview"
  });
  expect(opsReview.status()).toBe(403);
  await expect((await apiGet(ops.api, "/api/ops/control-room", ops.token)).ok()).toBeTruthy();
  await expect((await apiGet(ops.api, "/api/ops/intake/uploads", ops.token)).ok()).toBeTruthy();

  const reviewerUpload = await reviewer.api.post("/api/ops/intake/upload", {
    headers: {
      Authorization: `Bearer ${reviewer.token}`
    },
    multipart: {
      file: {
        name: "reviewer-blocked.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("%PDF-1.4\n%blocked\n")
      }
    }
  });
  expect(reviewerUpload.status()).toBe(403);

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
    extraAdminSession.api.dispose(),
    reviewer.api.dispose(),
    ops.api.dispose(),
    rawApi.dispose(),
    logoutContext.dispose()
  ]);
});
