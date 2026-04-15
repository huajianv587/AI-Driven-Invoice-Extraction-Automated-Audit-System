import fs from "node:fs";
import path from "node:path";
import { expect, test as setup } from "@playwright/test";

import { getRoleCredentials, roleAuthFile } from "../helpers/env";

const roles = ["admin", "reviewer", "ops"] as const;

setup("authenticate deep regression roles", async ({ browser, page }) => {
  for (const role of roles) {
    const authFile = roleAuthFile(role);
    fs.mkdirSync(path.dirname(authFile), { recursive: true });
    const context = await browser.newContext();
    const rolePage = await context.newPage();
    const { email, password } = getRoleCredentials(role);

    await rolePage.goto("/login");
    await rolePage.getByLabel("Email").fill(email);
    await rolePage.getByLabel("Password").fill(password);
    await rolePage.getByRole("button", { name: /^Sign in$/i }).click();
    await expect(rolePage).toHaveURL(/\/app\/dashboard$/, { timeout: 30000 });
    await context.storageState({ path: authFile });
    await context.close();
  }

  const inactive = getRoleCredentials("inactive");
  await page.goto("/login");
  await page.getByLabel("Email").fill(inactive.email);
  await page.getByLabel("Password").fill(inactive.password);
  await page.getByRole("button", { name: /^Sign in$/i }).click();
  await expect(page.getByText(/Invalid email or password/i)).toBeVisible();
});
