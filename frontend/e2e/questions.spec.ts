import { test, expect } from "@playwright/test";

test.describe("Questions", () => {
  test("kanban board renders with correct columns", async ({ page }) => {
    await page.goto("/questions");

    // Switch to kanban view if not already active
    const kanbanBtn = page.getByRole("button", { name: /kanban/i });
    if (await kanbanBtn.isVisible()) {
      await kanbanBtn.click();
    }

    // Dev user has admin + author roles, so should see all 6 columns
    // Primary: published, closed, archived
    // Authoring: draft, proposed, in review
    await expect(page.getByText("Published").first()).toBeVisible();
    await expect(page.getByText("Closed").first()).toBeVisible();
    await expect(page.getByText("Archived").first()).toBeVisible();
    await expect(page.getByText("Draft").first()).toBeVisible();
    await expect(page.getByText("Proposed").first()).toBeVisible();
    await expect(page.getByText("In Review").first()).toBeVisible();
  });

  test("can toggle between list and kanban views", async ({ page }) => {
    await page.goto("/questions");

    // Look for the view toggle buttons
    const listBtn = page.getByRole("button", { name: /list/i });
    const kanbanBtn = page.getByRole("button", { name: /kanban/i });

    if (await listBtn.isVisible()) {
      await listBtn.click();
      // In list view, there should be a table or list structure
      await expect(page.locator("table, [role='list']").first()).toBeVisible();
    }

    if (await kanbanBtn.isVisible()) {
      await kanbanBtn.click();
      // In kanban view, columns should be visible
      await expect(page.getByText("Published").first()).toBeVisible();
    }
  });

  test("create question as draft", async ({ page }) => {
    const title = `E2E Draft Question ${Date.now()}`;

    await page.goto("/questions/new");

    await expect(
      page.getByRole("heading", { name: "New Question" })
    ).toBeVisible();

    // Fill in the form
    await page.getByPlaceholder("What do you want to know?").fill(title);
    await page
      .getByPlaceholder(
        "Provide context, constraints, and what a good answer looks like..."
      )
      .fill("This is an E2E test question body with enough detail.");

    // Save as draft
    await page.getByRole("button", { name: "Save as Draft" }).click();

    // Should redirect to question detail
    await page.waitForURL("**/questions/**");

    // Verify the question detail shows correct title and draft status
    await expect(page.getByText(title)).toBeVisible();
    await expect(page.getByText("Draft").first()).toBeVisible();
  });

  test("create and submit question for review", async ({ page }) => {
    const title = `E2E Submitted Question ${Date.now()}`;

    await page.goto("/questions/new");

    await page.getByPlaceholder("What do you want to know?").fill(title);
    await page
      .getByPlaceholder(
        "Provide context, constraints, and what a good answer looks like..."
      )
      .fill("This is an E2E test question submitted for review.");

    // Create and submit in one step
    await page
      .getByRole("button", { name: "Create & Submit for Review" })
      .click();

    // Should redirect to question detail with "proposed" status
    await page.waitForURL("**/questions/**");
    await expect(page.getByText(title)).toBeVisible();
    await expect(page.getByText("Proposed").first()).toBeVisible();
  });

  test("full admin lifecycle: draft → proposed → in_review → published", async ({
    page,
  }) => {
    const title = `E2E Lifecycle Question ${Date.now()}`;

    // 1. Create as draft
    await page.goto("/questions/new");
    await page.getByPlaceholder("What do you want to know?").fill(title);
    await page
      .getByPlaceholder(
        "Provide context, constraints, and what a good answer looks like..."
      )
      .fill("Testing the full question lifecycle end-to-end.");
    await page.getByRole("button", { name: "Save as Draft" }).click();
    await page.waitForURL("**/questions/**");
    await expect(page.getByText("Draft").first()).toBeVisible();

    // 2. Submit for review (draft → proposed)
    await page
      .getByRole("button", { name: "Submit for Review" })
      .click();
    await expect(page.getByText("Proposed").first()).toBeVisible();

    // 3. Start review (proposed → in_review) — admin action
    await page.getByRole("button", { name: "Start Review" }).click();
    await expect(page.getByText("In Review").first()).toBeVisible();

    // 4. Publish (in_review → published) — admin action
    await page.getByRole("button", { name: "Publish" }).click();
    await expect(page.getByText("Published").first()).toBeVisible();
  });

  test("question detail page shows title, body, and status", async ({
    page,
  }) => {
    const title = `E2E Detail Question ${Date.now()}`;

    // Create a question first
    await page.goto("/questions/new");
    await page.getByPlaceholder("What do you want to know?").fill(title);
    await page
      .getByPlaceholder(
        "Provide context, constraints, and what a good answer looks like..."
      )
      .fill("Body for detail page test.");
    await page.getByRole("button", { name: "Save as Draft" }).click();
    await page.waitForURL("**/questions/**");

    // Verify detail page elements
    await expect(page.getByText(title)).toBeVisible();
    await expect(page.getByText("Body for detail page test.")).toBeVisible();
    await expect(page.getByText("Draft").first()).toBeVisible();

    // Verify author actions are visible
    await expect(page.getByRole("button", { name: "Edit" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Submit for Review" })
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Delete" })).toBeVisible();

    // Verify admin workflow buttons are visible
    await expect(page.getByText("Workflow:")).toBeVisible();
  });
});
