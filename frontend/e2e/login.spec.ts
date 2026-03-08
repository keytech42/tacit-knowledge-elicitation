import { test, expect } from "@playwright/test";

// These tests do NOT use the shared auth state — they test the login flow itself.
test.use({ storageState: { cookies: [], origins: [] } });

test.describe("Login", () => {
  test("login page renders with dev-login button", async ({ page }) => {
    await page.goto("/login");

    await expect(
      page.getByRole("heading", { name: "Knowledge Elicitation Platform" })
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Sign in as Test User" })
    ).toBeVisible();
  });

  test("dev-login redirects to questions page", async ({ page }) => {
    await page.goto("/login");

    await page.getByRole("button", { name: "Sign in as Test User" }).click();

    await page.waitForURL("**/questions");
    await expect(page.getByRole("link", { name: "Questions" })).toBeVisible();
  });

  test("unauthenticated user is redirected to login", async ({ page }) => {
    await page.goto("/questions");

    await page.waitForURL("**/login");
    await expect(
      page.getByRole("button", { name: "Sign in as Test User" })
    ).toBeVisible();
  });

  test("sign out clears session and redirects to login", async ({ page }) => {
    // First log in
    await page.goto("/login");
    await page.getByRole("button", { name: "Sign in as Test User" }).click();
    await page.waitForURL("**/questions");

    // Open user menu and sign out
    await page.getByText("Test User").click();
    await page.getByRole("button", { name: "Sign out" }).click();

    await page.waitForURL("**/login");
    await expect(
      page.getByRole("button", { name: "Sign in as Test User" })
    ).toBeVisible();
  });
});
