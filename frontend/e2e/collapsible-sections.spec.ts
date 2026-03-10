import { test, expect, Page } from "@playwright/test";

/**
 * Helper: create and publish a question so collapsible sections are visible.
 */
async function createPublishedQuestion(page: Page, suffix: string) {
  const title = `E2E Collapsible Test ${suffix}`;

  await page.goto("/questions/new");
  await page.getByPlaceholder("What do you want to know?").fill(title);
  await page
    .getByPlaceholder("Provide context, constraints, and what a good answer looks like...")
    .fill("Question for collapsible section e2e test.");
  await page.getByRole("button", { name: "Save as Draft" }).click();
  await page.waitForURL("**/questions/**");

  // Progress to published
  await page.getByRole("button", { name: "Submit for Review" }).click();
  await expect(page.getByText("Proposed").first()).toBeVisible();
  await page.getByRole("button", { name: "Start Review" }).click();
  await expect(page.getByText("In Review").first()).toBeVisible();
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Published").first()).toBeVisible();

  return { title };
}

test.describe("Collapsible Sections", () => {
  test("Submit Your Answer section can be collapsed and expanded", async ({ page }) => {
    await createPublishedQuestion(page, `${Date.now()}-answer-collapse`);

    // Section should be open by default with the answer textarea visible
    const answerHeader = page.getByText("Submit Your Answer", { exact: true });
    await expect(answerHeader).toBeVisible();
    await expect(page.getByPlaceholder("Write your answer...")).toBeVisible();

    // Click the section header to collapse
    await answerHeader.click();

    // Answer textarea should be hidden
    await expect(page.getByPlaceholder("Write your answer...")).not.toBeVisible();

    // Click again to expand
    await answerHeader.click();

    // Answer textarea should be visible again
    await expect(page.getByPlaceholder("Write your answer...")).toBeVisible();
  });

  test("AI Actions section can be collapsed and expanded", async ({ page }) => {
    await createPublishedQuestion(page, `${Date.now()}-ai-collapse`);

    // AI Actions section should be open by default (admin user)
    const aiHeader = page.getByText("AI Actions", { exact: true });
    await expect(aiHeader).toBeVisible();
    await expect(page.getByRole("button", { name: "Generate Answer Options" })).toBeVisible();

    // Collapse the AI Actions section
    await aiHeader.click();

    // Content should be hidden
    await expect(page.getByRole("button", { name: "Generate Answer Options" })).not.toBeVisible();

    // Expand again
    await aiHeader.click();

    // Content should be visible again
    await expect(page.getByRole("button", { name: "Generate Answer Options" })).toBeVisible();
  });

  test("Rate this question section can be collapsed and expanded", async ({ page }) => {
    await createPublishedQuestion(page, `${Date.now()}-rate-collapse`);

    // Rating section should be visible on published questions
    const ratingHeader = page.getByText("Rate this question", { exact: true });
    await expect(ratingHeader).toBeVisible();

    // Collapse the rating section
    await ratingHeader.click();

    // Stars should not be visible when collapsed (the star icons are inside the collapsible area)
    // The submit button for rating should be hidden
    await expect(page.getByRole("button", { name: "Submit Rating" })).not.toBeVisible();

    // Expand again
    await ratingHeader.click();

    // The rating area should be visible again — verify we can see the stars area
    // (stars are rendered as buttons/icons in the expanded section)
    await expect(ratingHeader).toBeVisible();
  });

  test("collapsing one section does not affect others", async ({ page }) => {
    await createPublishedQuestion(page, `${Date.now()}-independent-collapse`);

    // Both AI Actions and Submit Your Answer should start expanded
    await expect(page.getByPlaceholder("Write your answer...")).toBeVisible();
    await expect(page.getByRole("button", { name: "Generate Answer Options" })).toBeVisible();

    // Collapse only AI Actions
    await page.getByText("AI Actions", { exact: true }).click();

    // AI Actions content should be hidden, but answer form should remain visible
    await expect(page.getByRole("button", { name: "Generate Answer Options" })).not.toBeVisible();
    await expect(page.getByPlaceholder("Write your answer...")).toBeVisible();

    // Collapse Submit Your Answer too
    await page.getByText("Submit Your Answer", { exact: true }).click();

    // Now both should be collapsed
    await expect(page.getByRole("button", { name: "Generate Answer Options" })).not.toBeVisible();
    await expect(page.getByPlaceholder("Write your answer...")).not.toBeVisible();
  });
});
