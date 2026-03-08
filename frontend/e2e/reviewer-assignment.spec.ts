import { test, expect, Page } from "@playwright/test";

/**
 * Helper: create a published question and submit an answer.
 * Returns { questionUrl, answerUrl }.
 */
async function createPublishedQuestionWithAnswer(page: Page, suffix: string) {
  const title = `E2E Reviewer Test ${suffix}`;

  // Create question
  await page.goto("/questions/new");
  await page.getByPlaceholder("What do you want to know?").fill(title);
  await page
    .getByPlaceholder("Provide context, constraints, and what a good answer looks like...")
    .fill("Question for reviewer assignment e2e test.");
  await page.getByRole("button", { name: "Save as Draft" }).click();
  await page.waitForURL("**/questions/**");

  // Progress to published
  await page.getByRole("button", { name: "Submit for Review" }).click();
  await expect(page.getByText("Proposed").first()).toBeVisible();
  await page.getByRole("button", { name: "Start Review" }).click();
  await expect(page.getByText("In Review").first()).toBeVisible();
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Published").first()).toBeVisible();

  const questionUrl = page.url();

  // Submit an answer
  const answerText = `E2E test answer ${suffix}`;
  await page.getByPlaceholder("Write your answer...").fill(answerText);
  await page.getByRole("button", { name: "Submit Answer" }).click();
  await expect(page.getByText(answerText)).toBeVisible();

  // Navigate to answer detail
  const answerLink = page.locator("a", { hasText: answerText });
  await answerLink.waitFor({ state: "visible" });
  await answerLink.click();
  await page.waitForURL("**/answers/**");

  const answerUrl = page.url();
  return { questionUrl, answerUrl, title, answerText };
}

test.describe("Reviewer Assignment (AnswerDetail)", () => {
  test("UserPicker appears on submitted answer for reviewer/admin", async ({ page }) => {
    await createPublishedQuestionWithAnswer(page, `${Date.now()}-picker-visible`);

    // The answer should be in "Submitted" state
    await expect(page.getByText("Submitted").first()).toBeVisible();

    // UserPicker should be visible with "Assign reviewer:" label
    await expect(page.getByText("Assign reviewer:")).toBeVisible();
    await expect(page.getByPlaceholder("Search reviewers...")).toBeVisible();
  });

  test("UserPicker dropdown shows results on focus", async ({ page }) => {
    await createPublishedQuestionWithAnswer(page, `${Date.now()}-dropdown`);

    const input = page.getByPlaceholder("Search reviewers...");
    await input.click();

    // Dropdown should appear with a listbox
    const listbox = page.getByRole("listbox");
    await expect(listbox).toBeVisible();

    // Should show at least the dev user with "(you)" tag since we're logged in as a reviewer
    await expect(listbox.getByText("(you)")).toBeVisible({ timeout: 5000 });
  });

  test("search filters users by name", async ({ page }) => {
    await createPublishedQuestionWithAnswer(page, `${Date.now()}-search`);

    const input = page.getByPlaceholder("Search reviewers...");
    await input.click();
    await input.fill("Test");

    // Should show results containing "Test" in the dropdown
    const listbox = page.getByRole("listbox");
    await expect(listbox).toBeVisible();

    // Wait for search results (debounced 200ms)
    await page.waitForTimeout(300);
    await expect(listbox.getByText("Test User")).toBeVisible({ timeout: 5000 });
  });

  test("assign reviewer via UserPicker and verify review appears", async ({ page }) => {
    await createPublishedQuestionWithAnswer(page, `${Date.now()}-assign`);

    const input = page.getByPlaceholder("Search reviewers...");
    await input.click();

    // Wait for the dropdown with "(you)" — the dev user
    const listbox = page.getByRole("listbox");
    await expect(listbox.getByText("(you)")).toBeVisible({ timeout: 5000 });

    // Click the first option (should be the dev user with "(you)")
    await listbox.getByText("(you)").click();

    // A review should appear in the Reviews section
    await expect(page.getByText("Reviews (1)")).toBeVisible({ timeout: 5000 });

    // The review should show "Pending" status
    await expect(page.getByText("Pending").first()).toBeVisible();
  });

  test("UserPicker not shown for approved answers", async ({ page }) => {
    await createPublishedQuestionWithAnswer(page, `${Date.now()}-no-picker`);

    // Assign a reviewer (self) and approve
    const input = page.getByPlaceholder("Search reviewers...");
    await input.click();
    const listbox = page.getByRole("listbox");
    await expect(listbox.getByText("(you)")).toBeVisible({ timeout: 5000 });
    await listbox.getByText("(you)").click();
    await expect(page.getByText("Reviews (1)")).toBeVisible({ timeout: 5000 });

    // Navigate to the review and approve
    const reviewLink = page.locator("a", { hasText: "Pending" });
    await reviewLink.click();
    await page.waitForURL("**/reviews/**");

    await page.getByRole("button", { name: "Approve" }).click();
    await expect(page.getByText("Approved").first()).toBeVisible();

    // Navigate back to the answer
    await page.goBack();
    await page.waitForURL("**/answers/**");

    // Wait for reload — answer should now be approved
    await expect(page.getByText("Approved").first()).toBeVisible({ timeout: 5000 });

    // UserPicker should NOT be visible (only shown for submitted/under_review)
    await expect(page.getByPlaceholder("Search reviewers...")).not.toBeVisible();
  });

  test("can navigate to review from answer detail", async ({ page }) => {
    await createPublishedQuestionWithAnswer(page, `${Date.now()}-nav-review`);

    // Assign reviewer
    const input = page.getByPlaceholder("Search reviewers...");
    await input.click();
    const listbox = page.getByRole("listbox");
    await expect(listbox.getByText("(you)")).toBeVisible({ timeout: 5000 });
    await listbox.getByText("(you)").click();
    await expect(page.getByText("Reviews (1)")).toBeVisible({ timeout: 5000 });

    // Click the review link
    const reviewLink = page.locator("a", { hasText: "Pending" });
    await reviewLink.click();
    await page.waitForURL("**/reviews/**");

    // Should see review detail with verdict actions
    await expect(page.getByRole("button", { name: "Approve" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Request Changes" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Reject" })).toBeVisible();
  });
});
