import crypto from "node:crypto";
import { expect, request, type APIRequestContext, type Page } from "@playwright/test";

import { getPorts, getRoleCredentials, loadRootEnv } from "../helpers/env";

export type Role = "admin" | "reviewer" | "ops";

export async function signInApi(role: Role) {
  const { apiPort } = getPorts();
  const api = await request.newContext({
    baseURL: `http://127.0.0.1:${apiPort}`,
    extraHTTPHeaders: { "Content-Type": "application/json" }
  });
  const credentials = getRoleCredentials(role);
  const response = await api.post("/api/auth/login", {
    data: credentials
  });
  expect(response.ok()).toBeTruthy();
  const session = await response.json();
  return { api, token: String(session.access_token), user: session.user };
}

export async function apiGet(api: APIRequestContext, path: string, token: string) {
  return api.get(path, {
    headers: { Authorization: `Bearer ${token}` }
  });
}

export async function apiPost(api: APIRequestContext, path: string, token: string, data: unknown) {
  return api.post(path, {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json"
    },
    data
  });
}

export function expiredAccessToken(role: Role, userId = 9999) {
  const env = loadRootEnv();
  const secret = env.AUTH_JWT_SECRET || "change-me-local-dev-secret";
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "HS256", typ: "JWT" };
  const payload = {
    sub: String(userId),
    email: `${role}@invoice-audit.local`,
    role,
    name: "Expired Session",
    iat: now - 120,
    exp: now - 60,
    type: "access"
  };
  const encode = (value: unknown) =>
    Buffer.from(JSON.stringify(value)).toString("base64url");
  const unsigned = `${encode(header)}.${encode(payload)}`;
  const signature = crypto.createHmac("sha256", secret).update(unsigned).digest("base64url");
  return `${unsigned}.${signature}`;
}

export async function expectAccessDenied(page: Page) {
  await expect(page.getByRole("heading", { name: /Access restricted/i })).toBeVisible();
  await expect(page.getByText(/does not include this workspace surface/i)).toBeVisible();
}
