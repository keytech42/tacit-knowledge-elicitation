import { test as setup, expect } from "@playwright/test";

setup("authenticate via dev-login", async ({ page }) => {
  await page.goto("/login");

  // Click the dev login button
  await page.getByRole("button", { name: "Sign in as Test User" }).click();

  // Wait for redirect to questions page
  await page.waitForURL("**/questions");

  // Verify we're authenticated — the nav bar should show "Questions"
  await expect(page.getByRole("link", { name: "Questions" })).toBeVisible();

  // Save auth state for reuse
  await page.context().storageState({ path: "e2e/.auth/user.json" });
});
