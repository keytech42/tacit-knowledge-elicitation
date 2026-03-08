import { test, expect } from "@playwright/test";

test.describe("Answers", () => {
  /**
   * Helper: create and publish a question so we can submit answers to it.
   * Returns the question detail page URL.
   */
  async function createPublishedQuestion(
    page: import("@playwright/test").Page,
    suffix: string
  ) {
    const title = `E2E Answer Test Question ${suffix}`;

    await page.goto("/questions/new");
    await page.getByPlaceholder("What do you want to know?").fill(title);
    await page
      .getByPlaceholder(
        "Provide context, constraints, and what a good answer looks like..."
      )
      .fill("A question for testing answer submission.");
    await page.getByRole("button", { name: "Save as Draft" }).click();
    await page.waitForURL("**/questions/**");

    // Progress to published: submit → start review → publish
    await page.getByRole("button", { name: "Submit for Review" }).click();
    await expect(page.getByText("Proposed").first()).toBeVisible();

    await page.getByRole("button", { name: "Start Review" }).click();
    await expect(page.getByText("In Review").first()).toBeVisible();

    await page.getByRole("button", { name: "Publish" }).click();
    await expect(page.getByText("Published").first()).toBeVisible();

    return page.url();
  }

  test("answer form is visible on published question", async ({ page }) => {
    await createPublishedQuestion(page, `${Date.now()}-form`);

    await expect(
      page.getByRole("heading", { name: "Submit Your Answer" })
    ).toBeVisible();
    await expect(
      page.getByPlaceholder("Write your answer...")
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Submit Answer" })
    ).toBeVisible();
  });

  test("submit an answer and verify it appears", async ({ page }) => {
    await createPublishedQuestion(page, `${Date.now()}-submit`);

    const answerText = `E2E test answer content ${Date.now()}`;

    // Fill and submit
    await page.getByPlaceholder("Write your answer...").fill(answerText);
    await page.getByRole("button", { name: "Submit Answer" }).click();

    // Answer should appear in the answers list
    await expect(page.getByText(answerText)).toBeVisible();

    // The answers count should update
    await expect(page.getByText("Answers (1)")).toBeVisible();
  });

  test("can navigate to answer detail page", async ({ page }) => {
    await createPublishedQuestion(page, `${Date.now()}-detail`);

    const answerText = `E2E answer for detail test ${Date.now()}`;

    // Submit an answer
    await page.getByPlaceholder("Write your answer...").fill(answerText);
    await page.getByRole("button", { name: "Submit Answer" }).click();

    // Wait for the answer to appear in the refreshed list, then click its link
    const answerLink = page.locator("a", { hasText: answerText });
    await answerLink.waitFor({ state: "visible" });
    await answerLink.click();

    // Should be on answer detail page
    await page.waitForURL("**/answers/**");

    // Verify answer content and status badge
    await expect(page.getByText(answerText)).toBeVisible();
    await expect(page.getByText("Submitted").first()).toBeVisible();
  });
});
