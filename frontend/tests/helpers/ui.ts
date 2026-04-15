import fs from "node:fs";
import path from "node:path";
import { expect, type BrowserContext, type Page } from "@playwright/test";

import { frontendRoot, repoRoot } from "./env";

export const invoiceIds = {
  pendingRisk: 1,
  approvedSynced: 2,
  failedSync: 3,
  rejected: 4,
  cleanPending: 5,
  reviewCandidate: 6
};

export function isMobileProject(projectName: string) {
  return projectName.toLowerCase().includes("mobile");
}

export async function prepareStablePage(page: Page) {
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation-duration: 0s !important;
        animation-delay: 0s !important;
        transition-duration: 0s !important;
        transition-delay: 0s !important;
        caret-color: transparent !important;
      }
    `
  });
  await page.evaluate(async () => {
    if ("fonts" in document) {
      await document.fonts.ready;
    }
  });
}

export async function expectStableScreenshot(page: Page, name: string, options = {}) {
  await prepareStablePage(page);
  await expect(page).toHaveScreenshot(name, {
    fullPage: true,
    animations: "disabled",
    maxDiffPixelRatio: 0.02,
    ...options
  });
}

export async function cookieHeader(context: BrowserContext) {
  const cookies = await context.cookies();
  return cookies.map((cookie) => `${cookie.name}=${cookie.value}`).join("; ");
}

export async function saveAuditScreenshot(page: Page, name: string) {
  await prepareStablePage(page);
  const outputDir = path.resolve(repoRoot, "artifacts", "ui-audit", "latest");
  fs.mkdirSync(outputDir, { recursive: true });
  await page.screenshot({
    path: path.join(outputDir, name),
    fullPage: true
  });
}

export function clearAuditDirectory() {
  const outputDir = path.resolve(repoRoot, "artifacts", "ui-audit", "latest");
  fs.rmSync(outputDir, { recursive: true, force: true });
  fs.mkdirSync(outputDir, { recursive: true });
}
