import { test, expect, Page } from "@playwright/test";

/**
 * Helper: create a published question, submit an answer, and assign a reviewer.
 * Returns the review detail page URL.
 */
async function createReviewForAnswer(page: Page, suffix: string) {
  const title = `E2E Review Detail ${suffix}`;

  // Create and publish question
  await page.goto("/questions/new");
  await page.getByPlaceholder("What do you want to know?").fill(title);
  await page
    .getByPlaceholder("Provide context, constraints, and what a good answer looks like...")
    .fill("Question for review detail e2e test.");
  await page.getByRole("button", { name: "Save as Draft" }).click();
  await page.waitForURL("**/questions/**");

  await page.getByRole("button", { name: "Submit for Review" }).click();
  await expect(page.getByText("Proposed").first()).toBeVisible();
  await page.getByRole("button", { name: "Start Review" }).click();
  await expect(page.getByText("In Review").first()).toBeVisible();
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Published").first()).toBeVisible();

  // Submit an answer
  const answerText = `E2E review detail answer ${suffix}`;
  await page.getByPlaceholder("Write your answer...").fill(answerText);
  await page.getByRole("button", { name: "Submit Answer" }).click();
  await expect(page.getByText(answerText)).toBeVisible();

  // Navigate to answer detail
  const answerLink = page.locator("a", { hasText: answerText });
  await answerLink.waitFor({ state: "visible" });
  await answerLink.click();
  await page.waitForURL("**/answers/**");

  // Assign reviewer via UserPicker
  const input = page.getByPlaceholder("Search reviewers...");
  await input.click();
  const listbox = page.getByRole("listbox");
  await expect(listbox.getByText("(you)")).toBeVisible({ timeout: 5000 });
  await listbox.getByText("(you)").click();
  await expect(page.getByText("Reviews (1)")).toBeVisible({ timeout: 5000 });

  // Navigate to review detail
  const reviewLink = page.locator("a", { hasText: "Pending" });
  await reviewLink.click();
  await page.waitForURL("**/reviews/**");

  return { reviewUrl: page.url(), title, answerText };
}

test.describe("Review Detail Page", () => {
  test("assign additional reviewer picker visible", async ({ page }) => {
    await createReviewForAnswer(page, `${Date.now()}-additional`);

    // The "Assign additional reviewer" picker should be visible
    await expect(page.getByText("Assign additional reviewer")).toBeVisible();
    await expect(page.getByPlaceholder("Search for a reviewer...")).toBeVisible();
  });

  test("review shows assigned-by attribution", async ({ page }) => {
    await createReviewForAnswer(page, `${Date.now()}-attribution`);

    // Should show "(assigned by <name>)" since we assigned via the endpoint
    await expect(page.getByText(/assigned by/)).toBeVisible();
  });

  test("verdict buttons visible for assigned reviewer", async ({ page }) => {
    await createReviewForAnswer(page, `${Date.now()}-verdict-btns`);

    // All three verdict buttons should be visible
    await expect(page.getByRole("button", { name: "Approve" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Request Changes" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Reject" })).toBeVisible();
  });

  test("approve verdict updates review status", async ({ page }) => {
    await createReviewForAnswer(page, `${Date.now()}-approve`);

    await page.getByRole("button", { name: "Approve" }).click();

    // Status should change to "Approved"
    await expect(page.getByText("Approved").first()).toBeVisible({ timeout: 5000 });

    // Verdict buttons should no longer be actionable
    await expect(page.getByRole("button", { name: "Approve" })).not.toBeVisible();
  });

  test("request changes verdict with comment", async ({ page }) => {
    await createReviewForAnswer(page, `${Date.now()}-changes`);

    // Add a review comment before submitting verdict
    const commentInput = page.getByPlaceholder("Review comment (optional for approve, recommended for others)");
    await commentInput.fill("Please fix the formatting.");

    await page.getByRole("button", { name: "Request Changes" }).click();

    // Status should update
    await expect(page.getByText("Changes Requested").first()).toBeVisible({ timeout: 5000 });

    // Comment should be visible
    await expect(page.getByText("Please fix the formatting.")).toBeVisible();
  });

  test("discussion section allows adding comments", async ({ page }) => {
    await createReviewForAnswer(page, `${Date.now()}-discussion`);

    // Discussion section should be visible
    await expect(page.getByText("Discussion (0)")).toBeVisible();

    // Add a comment
    const commentInput = page.getByPlaceholder("Add a comment...");
    await commentInput.fill("This is a discussion comment.");
    await page.getByRole("button", { name: "Comment" }).click();

    // Comment should appear
    await expect(page.getByText("This is a discussion comment.")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Discussion (1)")).toBeVisible();
  });
});
