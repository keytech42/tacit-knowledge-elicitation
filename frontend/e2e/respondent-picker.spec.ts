import { test, expect, Page } from "@playwright/test";

/**
 * Helper: create a published question.
 * Returns the question detail page URL.
 */
async function createPublishedQuestion(page: Page, suffix: string) {
  const title = `E2E Respondent Test ${suffix}`;

  await page.goto("/questions/new");
  await page.getByPlaceholder("What do you want to know?").fill(title);
  await page
    .getByPlaceholder("Provide context, constraints, and what a good answer looks like...")
    .fill("Question for respondent picker e2e test.");
  await page.getByRole("button", { name: "Save as Draft" }).click();
  await page.waitForURL("**/questions/**");

  // Progress to published
  await page.getByRole("button", { name: "Submit for Review" }).click();
  await expect(page.getByText("Proposed").first()).toBeVisible();
  await page.getByRole("button", { name: "Start Review" }).click();
  await expect(page.getByText("In Review").first()).toBeVisible();
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Published").first()).toBeVisible();

  return { url: page.url(), title };
}

test.describe("Respondent Picker (QuestionDetail)", () => {
  test("AI Actions section visible on published question for admin", async ({ page }) => {
    await createPublishedQuestion(page, `${Date.now()}-ai-section`);

    // The AI Actions section should be visible for admin users
    await expect(page.getByRole("heading", { name: "AI Actions" })).toBeVisible();

    // Should show the "Assign Respondent" label (UserPicker)
    await expect(page.getByText("Assign Respondent")).toBeVisible();
    await expect(page.getByPlaceholder("Search respondents by name or email...")).toBeVisible();
  });

  test("respondent picker dropdown shows results", async ({ page }) => {
    await createPublishedQuestion(page, `${Date.now()}-respondent-dropdown`);

    const input = page.getByPlaceholder("Search respondents by name or email...");
    await input.click();

    // Dropdown should appear
    const listbox = page.getByRole("listbox");
    await expect(listbox).toBeVisible();

    // Should show at least one user (the dev user has all roles including respondent)
    await expect(listbox.locator("[role=option]").first()).toBeVisible({ timeout: 5000 });
  });

  test("assign respondent and verify assignment shown", async ({ page }) => {
    await createPublishedQuestion(page, `${Date.now()}-assign-resp`);

    const input = page.getByPlaceholder("Search respondents by name or email...");
    await input.click();

    // Wait for dropdown results
    const listbox = page.getByRole("listbox");
    await expect(listbox.locator("[role=option]").first()).toBeVisible({ timeout: 5000 });

    // Click the first result
    await listbox.locator("[role=option]").first().click();

    // The picker should now show the selected user (with clear button)
    await expect(page.getByRole("button", { name: "Clear selection" })).toBeVisible({ timeout: 5000 });

    // The question header should show "Assigned: <name>"
    await expect(page.getByText(/Assigned:/).first()).toBeVisible();
  });

  test("AI Actions not shown on draft questions", async ({ page }) => {
    const title = `E2E Draft No AI ${Date.now()}`;

    await page.goto("/questions/new");
    await page.getByPlaceholder("What do you want to know?").fill(title);
    await page
      .getByPlaceholder("Provide context, constraints, and what a good answer looks like...")
      .fill("This is a draft question body for testing.");
    await page.getByRole("button", { name: "Save as Draft" }).click();
    await page.waitForURL("**/questions/**");

    // AI Actions heading should NOT be visible on draft questions
    await expect(page.getByRole("heading", { name: "AI Actions" })).not.toBeVisible();
    await expect(page.getByText("Assign Respondent")).not.toBeVisible();
  });

  test("respondent search filters by query", async ({ page }) => {
    await createPublishedQuestion(page, `${Date.now()}-search-filter`);

    const input = page.getByPlaceholder("Search respondents by name or email...");
    await input.click();
    await input.fill("Test");

    const listbox = page.getByRole("listbox");
    await expect(listbox).toBeVisible();

    // Should find the dev user named "Test User"
    await expect(listbox.getByText("Test User")).toBeVisible({ timeout: 5000 });
  });

  test("Generate Answer Options and Recommend Respondents buttons visible", async ({ page }) => {
    await createPublishedQuestion(page, `${Date.now()}-buttons`);

    // Both AI action buttons should be visible in the AI Actions section
    await expect(page.getByRole("button", { name: "Generate Answer Options" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Recommend Respondents" })).toBeVisible();
  });
});
