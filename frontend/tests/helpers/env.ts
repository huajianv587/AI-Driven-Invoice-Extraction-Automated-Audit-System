import fs from "node:fs";
import path from "node:path";

export const frontendRoot = path.resolve(__dirname, "..", "..");
export const repoRoot = path.resolve(frontendRoot, "..");
export const authFile = path.resolve(frontendRoot, "tests", ".auth", "admin.json");
export const roleAuthFile = (role: "admin" | "reviewer" | "ops") =>
  path.resolve(frontendRoot, "tests", ".auth", `${role}.json`);

type EnvMap = Record<string, string>;

function parseEnvFile(filePath: string): EnvMap {
  if (!fs.existsSync(filePath)) {
    return {};
  }

  const values: EnvMap = {};
  for (const rawLine of fs.readFileSync(filePath, "utf-8").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) {
      continue;
    }
    const [rawKey, ...rest] = line.split("=");
    const key = rawKey.trim();
    let value = rest.join("=").trim();
    if ((value.startsWith("\"") && value.endsWith("\"")) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }
  return values;
}

export function loadRootEnv(): EnvMap {
  const values: EnvMap = {
    ...parseEnvFile(path.join(repoRoot, ".env.example")),
    ...parseEnvFile(path.join(repoRoot, ".env"))
  };
  for (const [key, value] of Object.entries(process.env)) {
    if (value !== undefined) {
      values[key] = value;
    }
  }
  return values;
}

export function applyRootEnvToProcess(options: { skipKeys?: string[] } = {}) {
  const values = loadRootEnv();
  const skipKeys = new Set(options.skipKeys ?? []);
  for (const [key, value] of Object.entries(values)) {
    if (skipKeys.has(key)) {
      continue;
    }
    if (process.env[key] === undefined && value !== undefined) {
      process.env[key] = value;
    }
  }
  return values;
}

export function getPorts() {
  const env = loadRootEnv();
  return {
    apiPort: Number(env.API_PORT || 8009),
    frontendPort: Number(env.FRONTEND_PORT || 3000),
    stackPort: Number(env.PLAYWRIGHT_STACK_PORT || 3410)
  };
}

export function getAdminCredentials() {
  const env = loadRootEnv();
  return {
    email: env.AUTH_BOOTSTRAP_ADMIN_EMAIL || "admin@invoice-audit.local",
    password: env.AUTH_BOOTSTRAP_ADMIN_PASSWORD || "ChangeMe123!"
  };
}

export function getRefreshCookieName() {
  const env = loadRootEnv();
  return env.AUTH_COOKIE_NAME || "invoice_refresh_token";
}

export function getRoleCredentials(role: "admin" | "reviewer" | "ops" | "inactive") {
  if (role === "admin") {
    return getAdminCredentials();
  }
  const defaults = {
    reviewer: { email: "reviewer@invoice-audit.local", password: "Reviewer123!" },
    ops: { email: "ops@invoice-audit.local", password: "OpsUser123!" },
    inactive: { email: "inactive@invoice-audit.local", password: "Inactive123!" }
  };
  return defaults[role];
}
