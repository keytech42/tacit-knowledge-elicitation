import { test, expect, Page } from "@playwright/test";

/**
 * Helper: create and publish a question, submit an answer, and return URLs + IDs.
 */
async function createPublishedQuestionWithAnswer(page: Page, suffix: string) {
  const title = `E2E Breadcrumb Test ${suffix}`;

  await page.goto("/questions/new");
  await page.getByPlaceholder("What do you want to know?").fill(title);
  await page
    .getByPlaceholder("Provide context, constraints, and what a good answer looks like...")
    .fill("Question for breadcrumb e2e test.");
  await page.getByRole("button", { name: "Save as Draft" }).click();
  await page.waitForURL("**/questions/**");

  // Progress to published
  await page.getByRole("button", { name: "Submit for Review" }).click();
  await expect(page.getByText("Proposed").first()).toBeVisible();
  await page.getByRole("button", { name: "Start Review" }).click();
  await expect(page.getByText("In Review").first()).toBeVisible();

  const questionUrl = page.url();
  const questionId = questionUrl.split("/questions/")[1];

  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Published").first()).toBeVisible();

  // Submit an answer
  const answerText = `E2E breadcrumb answer ${suffix}`;
  await page.getByPlaceholder("Write your answer...").fill(answerText);
  await page.getByRole("button", { name: "Submit Answer" }).click();
  await expect(page.getByText(answerText)).toBeVisible();

  return { questionUrl, questionId, title, answerText };
}

test.describe("Breadcrumbs", () => {
  test("QuestionDetail shows breadcrumb with link to Questions list", async ({ page }) => {
    const { title } = await createPublishedQuestionWithAnswer(page, `${Date.now()}-q-bc`);

    // Breadcrumb nav should be visible
    const breadcrumb = page.locator("nav.text-xs");
    await expect(breadcrumb).toBeVisible();

    // Should show "Questions / <title>"
    await expect(breadcrumb.getByText("Questions")).toBeVisible();
    await expect(breadcrumb.getByText(title)).toBeVisible();

    // "Questions" should be a link back to the list
    const questionsLink = breadcrumb.getByRole("link", { name: "Questions" });
    await expect(questionsLink).toBeVisible();
    await questionsLink.click();
    await page.waitForURL("**/questions");
  });

  test("AnswerDetail shows breadcrumb with link to Questions and parent question", async ({ page }) => {
    const { title, answerText } = await createPublishedQuestionWithAnswer(page, `${Date.now()}-a-bc`);

    // Navigate to answer detail
    const answerLink = page.locator("a", { hasText: answerText });
    await answerLink.waitFor({ state: "visible" });
    await answerLink.click();
    await page.waitForURL("**/answers/**");

    // Breadcrumb nav should be visible
    const breadcrumb = page.locator("nav.text-xs");
    await expect(breadcrumb).toBeVisible();

    // Should show "Questions / <question title> / Answer"
    await expect(breadcrumb.getByText("Questions")).toBeVisible();
    await expect(breadcrumb.getByText(title)).toBeVisible();
    await expect(breadcrumb.getByText("Answer")).toBeVisible();

    // "Questions" should link to the list
    await expect(breadcrumb.getByRole("link", { name: "Questions" })).toBeVisible();

    // Parent question title should be a link
    await expect(breadcrumb.getByRole("link", { name: title })).toBeVisible();
  });

  test("ReviewDetail shows breadcrumb with link to Reviews list", async ({ page }) => {
    const { questionId } = await createPublishedQuestionWithAnswer(page, `${Date.now()}-r-bc`);

    // Create a question review via API
    const reviewId = await page.evaluate(async (qId) => {
      const token = localStorage.getItem("token");
      const resp = await fetch("/api/v1/reviews", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
        },
        body: JSON.stringify({ target_type: "question", target_id: qId }),
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`Failed to create review: ${resp.status} ${text}`);
      }
      const data = await resp.json();
      return data.id as string;
    }, questionId);

    // Navigate to review detail
    await page.goto(`/reviews/${reviewId}`);

    // Breadcrumb nav should be visible
    const breadcrumb = page.locator("nav.text-xs");
    await expect(breadcrumb).toBeVisible();

    // Should show "Reviews / Review"
    await expect(breadcrumb.getByText("Reviews")).toBeVisible();
    await expect(breadcrumb.getByText("Review", { exact: true })).toBeVisible();

    // "Reviews" should be a link back to the reviews list
    const reviewsLink = breadcrumb.getByRole("link", { name: "Reviews" });
    await expect(reviewsLink).toBeVisible();
    await reviewsLink.click();
    await page.waitForURL("**/reviews");
  });

  test("breadcrumb question link navigates to parent question from answer detail", async ({ page }) => {
    const { title, answerText } = await createPublishedQuestionWithAnswer(page, `${Date.now()}-nav-bc`);

    // Navigate to answer detail
    const answerLink = page.locator("a", { hasText: answerText });
    await answerLink.waitFor({ state: "visible" });
    await answerLink.click();
    await page.waitForURL("**/answers/**");

    // Click the question title link in breadcrumb
    const breadcrumb = page.locator("nav.text-xs");
    await breadcrumb.getByRole("link", { name: title }).click();
    await page.waitForURL("**/questions/**");

    // Should be on the question detail page
    await expect(page.getByText(title).first()).toBeVisible();
  });
});
