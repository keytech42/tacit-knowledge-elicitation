import { test, expect, Page } from "@playwright/test";

/**
 * Helper: create a published question, submit an answer, and create a review
 * via POST /reviews API (self-assigned, the current user is the reviewer).
 *
 * NOTE: In CI with a single dev user, POST /reviews will fail with 409
 * (cannot review your own answer). Tests that need a review object use
 * question reviews instead, or test only UI structure.
 */
async function createPublishedQuestionWithAnswer(page: Page, suffix: string) {
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

  // Extract question ID before publishing
  const questionUrl = page.url();
  const questionId = questionUrl.split("/questions/")[1];

  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Published").first()).toBeVisible();

  // Submit an answer
  const answerText = `E2E review detail answer ${suffix}`;
  await page.getByPlaceholder("Write your answer...").fill(answerText);
  await page.getByRole("button", { name: "Submit Answer" }).click();
  await expect(page.getByText(answerText)).toBeVisible();

  return { questionUrl, questionId, title, answerText };
}

/**
 * Helper: create a question-level review via API.
 * Question reviews don't have author-exclusion, so they work in single-user CI.
 * Returns the review ID.
 */
async function createQuestionReview(page: Page, questionId: string): Promise<string> {
  // Extract JWT token from localStorage (the frontend stores it as "token")
  const token = await page.evaluate(() => localStorage.getItem("token"));
  const resp = await page.request.post(`/api/v1/reviews`, {
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`,
    },
    data: { target_type: "question", target_id: questionId },
  });
  if (!resp.ok()) {
    throw new Error(`Failed to create review: ${resp.status()} ${await resp.text()}`);
  }
  const body = await resp.json();
  return body.id;
}

test.describe("Review Detail Page", () => {
  test("review detail shows verdict buttons and status", async ({ page }) => {
    const { questionId } = await createPublishedQuestionWithAnswer(page, `${Date.now()}-verdict`);

    // Create a question review via API (avoids self-review issue with answers)
    const reviewId = await createQuestionReview(page, questionId);

    // Navigate to review detail
    await page.goto(`/reviews/${reviewId}`);

    // Should show pending status
    await expect(page.getByText("Pending").first()).toBeVisible();

    // All three verdict buttons should be visible for the assigned reviewer
    await expect(page.getByRole("button", { name: "Approve" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Request Changes" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Reject" })).toBeVisible();
  });

  test("approve verdict updates review status", async ({ page }) => {
    const { questionId } = await createPublishedQuestionWithAnswer(page, `${Date.now()}-approve`);
    const reviewId = await createQuestionReview(page, questionId);

    await page.goto(`/reviews/${reviewId}`);
    await page.getByRole("button", { name: "Approve" }).click();

    // Status should change to "Approved"
    await expect(page.getByText("Approved").first()).toBeVisible({ timeout: 5000 });

    // Verdict buttons should no longer be visible (not pending anymore)
    await expect(page.getByRole("button", { name: "Approve" })).not.toBeVisible();
  });

  test("request changes verdict with comment", async ({ page }) => {
    const { questionId } = await createPublishedQuestionWithAnswer(page, `${Date.now()}-changes`);
    const reviewId = await createQuestionReview(page, questionId);

    await page.goto(`/reviews/${reviewId}`);

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
    const { questionId } = await createPublishedQuestionWithAnswer(page, `${Date.now()}-discussion`);
    const reviewId = await createQuestionReview(page, questionId);

    await page.goto(`/reviews/${reviewId}`);

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

  test("review shows target content with link", async ({ page }) => {
    const { questionId, title } = await createPublishedQuestionWithAnswer(page, `${Date.now()}-target`);
    const reviewId = await createQuestionReview(page, questionId);

    await page.goto(`/reviews/${reviewId}`);

    // The target question should be shown as a clickable link
    await expect(page.getByText(title)).toBeVisible();
    await expect(page.getByText("View question")).toBeVisible();
  });

  test("review comment textarea visible when pending", async ({ page }) => {
    const { questionId } = await createPublishedQuestionWithAnswer(page, `${Date.now()}-textarea`);
    const reviewId = await createQuestionReview(page, questionId);

    await page.goto(`/reviews/${reviewId}`);

    // Review comment textarea should be visible when verdict is pending
    await expect(
      page.getByPlaceholder("Review comment (optional for approve, recommended for others)")
    ).toBeVisible();
  });
});
