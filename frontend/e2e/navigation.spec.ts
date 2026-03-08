import { test, expect } from "@playwright/test";

test.describe("Navigation", () => {
  test("nav bar shows correct links for admin user", async ({ page }) => {
    await page.goto("/questions");

    const nav = page.locator("nav");

    // Dev user has all roles including admin and reviewer
    await expect(nav.getByRole("link", { name: "KEP" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Questions" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Reviews" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Admin Queue" })).toBeVisible();
    await expect(
      nav.getByRole("link", { name: "Service Accounts" })
    ).toBeVisible();
    await expect(nav.getByRole("link", { name: "AI Logs" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "AI Controls" })).toBeVisible();
  });

  test("admin pages are accessible", async ({ page }) => {
    // Admin Queue
    await page.goto("/admin/questions");
    await expect(page.locator("main")).not.toHaveText("Access Denied");

    // Service Accounts
    await page.goto("/admin/service-accounts");
    await expect(page.locator("main")).not.toHaveText("Access Denied");

    // AI Logs
    await page.goto("/admin/ai-logs");
    await expect(page.locator("main")).not.toHaveText("Access Denied");

    // Settings
    await page.goto("/settings");
    await expect(page.locator("main")).not.toHaveText("Access Denied");
  });

  test("reviews page is accessible", async ({ page }) => {
    await page.goto("/reviews");
    await expect(page.locator("main")).not.toHaveText("Access Denied");
  });

  test("KEP logo navigates to questions", async ({ page }) => {
    await page.goto("/settings");
    await page.getByRole("link", { name: "KEP" }).click();
    await page.waitForURL("**/questions");
  });

  test("user menu shows user info and roles", async ({ page }) => {
    await page.goto("/questions");

    // Open user menu (use button role to avoid matching question cards)
    await page.getByRole("button", { name: /Test User/ }).click();

    // Should show email and roles
    await expect(page.getByText("dev@localhost")).toBeVisible();
    await expect(page.getByText("admin", { exact: true })).toBeVisible();
  });
});
