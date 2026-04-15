import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(frontendRoot, "..");

function parseEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return {};
  const values = {};
  for (const rawLine of fs.readFileSync(filePath, "utf-8").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
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

const env = {
  ...parseEnvFile(path.join(repoRoot, ".env.example")),
  ...parseEnvFile(path.join(repoRoot, ".env")),
  ...process.env
};

const apiPort = Number(env.API_PORT || 8009);
const frontendPort = Number(env.FRONTEND_PORT || 3000);
const stackPort = Number(env.PLAYWRIGHT_STACK_PORT || 3410);
const baseURL = `http://localhost:${frontendPort}`;
const apiBaseURL = `http://localhost:${apiPort}`;
const stackHealth = `http://127.0.0.1:${stackPort}/healthz`;
const artifacts = path.join(repoRoot, "artifacts", "lighthouse");
const pythonCandidate = path.join(repoRoot, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const python = fs.existsSync(pythonCandidate) ? pythonCandidate : "python";
const commandName = (name) => (process.platform === "win32" ? `${name}.cmd` : name);

function spawnProcess(command, args, options = {}) {
  return spawn(command, args, {
    stdio: "inherit",
    shell: false,
    ...options
  });
}

async function isReady(url) {
  try {
    const response = await fetch(url, { cache: "no-store" });
    return response.ok;
  } catch {
    return false;
  }
}

async function waitFor(url, label, timeoutMs = 360000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await isReady(url)) {
      console.log(`[ok] ${label}: ${url}`);
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`${label} did not become ready: ${url}`);
}

async function runCommand(command, args, options = {}) {
  const quoteForCmd = (arg) => {
    const text = String(arg);
    if (/^[A-Za-z0-9_./:=-]+$/.test(text)) {
      return text;
    }
    return `"${text.replace(/"/g, '\\"')}"`;
  };
  await new Promise((resolve, reject) => {
    const child = options.windowsShell
      ? spawn([command, ...args].map(quoteForCmd).join(" "), {
          stdio: "inherit",
          shell: true
        })
      : spawnProcess(command, args, options);
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} ${args.join(" ")} failed with exit code ${code}`));
    });
    child.on("error", reject);
  });
}

async function loginCookie() {
  const response = await fetch(`${apiBaseURL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: env.AUTH_BOOTSTRAP_ADMIN_EMAIL || "admin@invoice-audit.local",
      password: env.AUTH_BOOTSTRAP_ADMIN_PASSWORD || "ChangeMe123!"
    })
  });
  if (!response.ok) {
    throw new Error(`Unable to log in for Lighthouse dashboard audit: HTTP ${response.status}`);
  }
  const cookie = response.headers.get("set-cookie");
  if (!cookie) {
    throw new Error("Login succeeded but no refresh cookie was returned.");
  }
  return cookie.split(";")[0];
}

async function runLighthouse(url, name, extraHeaders = {}) {
  const outputPath = path.join(artifacts, `${name}.json`);
  const args = [
    "--yes",
    "lighthouse",
    url,
    "--quiet",
    "--output=json",
    `--output-path=${outputPath}`,
    "--only-categories=performance,accessibility,best-practices,seo",
    "--chrome-flags=--headless=new --no-sandbox"
  ];
  if (Object.keys(extraHeaders).length) {
    args.push(`--extra-headers=${JSON.stringify(extraHeaders)}`);
  }
  try {
    await runCommand(commandName("npx"), args, { windowsShell: process.platform === "win32" });
  } catch (error) {
    if (!fs.existsSync(outputPath)) {
      throw error;
    }
    console.warn(`[warn] Lighthouse exited non-zero after writing ${outputPath}. Continuing with the generated report.`);
  }
  const report = JSON.parse(fs.readFileSync(outputPath, "utf-8"));
  const scores = Object.fromEntries(
    Object.entries(report.categories).map(([key, value]) => [key, Math.round(value.score * 100)])
  );
  console.log(`[lighthouse] ${name}: ${JSON.stringify(scores)}`);
  const minimums = {
    performance: 90,
    accessibility: 95,
    "best-practices": 90,
    seo: 90
  };
  for (const [key, min] of Object.entries(minimums)) {
    if ((scores[key] || 0) < min) {
      throw new Error(`${name} ${key} score ${scores[key]} is below ${min}`);
    }
  }
}

fs.mkdirSync(artifacts, { recursive: true });

let stack = null;
try {
  if (!(await isReady(stackHealth))) {
    stack = spawnProcess(python, [path.join(repoRoot, "scripts", "run_web_e2e_stack.py")], {
      cwd: repoRoot,
      env: { ...process.env, PYTHONUTF8: "1" }
    });
  }
  await waitFor(stackHealth, "Web E2E stack");
  const cookie = await loginCookie();
  await runLighthouse(`${baseURL}/`, "landing");
  await runLighthouse(`${baseURL}/app/dashboard`, "dashboard", { Cookie: cookie });
} finally {
  if (stack) {
    stack.kill();
  }
}
