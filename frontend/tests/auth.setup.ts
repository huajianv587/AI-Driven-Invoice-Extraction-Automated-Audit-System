import fs from "node:fs";
import path from "node:path";
import { expect, test as setup } from "@playwright/test";

import { authFile, getAdminCredentials } from "./helpers/env";

setup("authenticate as bootstrap admin", async ({ page }) => {
  const { email, password } = getAdminCredentials();
  fs.mkdirSync(path.dirname(authFile), { recursive: true });

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /^Sign in$/i }).click();

  await expect(page).toHaveURL(/\/app\/dashboard$/, { timeout: 30000 });
  await page.context().storageState({ path: authFile });
});
