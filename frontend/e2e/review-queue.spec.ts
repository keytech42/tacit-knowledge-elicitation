import { test, expect, Page } from "@playwright/test";

/**
 * Helper: create a published question with a question-level review.
 * Uses question reviews to avoid self-review conflicts in single-user CI.
 */
async function createQuestionWithReview(page: Page, suffix: string) {
  await page.goto("/questions/new");
  await page.getByPlaceholder("What do you want to know?").fill(`E2E Review Queue ${suffix}`);
  await page
    .getByPlaceholder("Provide context, constraints, and what a good answer looks like...")
    .fill("Question for review queue e2e test.");
  await page.getByRole("button", { name: "Save as Draft" }).click();
  await page.waitForURL("**/questions/**");

  // Advance to published
  await page.getByRole("button", { name: "Submit for Review" }).click();
  await expect(page.getByText("Proposed").first()).toBeVisible();
  await page.getByRole("button", { name: "Start Review" }).click();
  await expect(page.getByText("In Review").first()).toBeVisible();

  const questionId = page.url().split("/questions/")[1];

  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Published").first()).toBeVisible();

  // Create a question review via API
  await page.evaluate(async (qId) => {
    const token = localStorage.getItem("token");
    const resp = await fetch("/api/v1/reviews", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ target_type: "question", target_id: qId }),
    });
    if (!resp.ok) throw new Error(`Failed to create review: ${resp.status}`);
  }, questionId);

  return questionId;
}

/** Switch to the "question" review tab (created reviews are question-level). */
async function switchToQuestionTab(page: Page) {
  const questionTab = page.getByRole("button", { name: /question reviews/i });
  if (await questionTab.isVisible()) {
    await questionTab.click();
  }
}

test.describe("Review Queue", () => {
  test("list view renders review cards without errors", async ({ page }) => {
    await createQuestionWithReview(page, `${Date.now()}-list`);

    // Navigate to reviews page in list mode
    await page.goto("/reviews");
    const listBtn = page.getByRole("button", { name: /list/i });
    if (await listBtn.isVisible()) {
      await listBtn.click();
    }
    await switchToQuestionTab(page);

    // The page should render without crashing — at least one review card should be visible
    const cards = page.locator("main a[href^='/reviews/']");
    await expect(cards.first()).toBeVisible({ timeout: 5000 });

    // Card should contain a status badge (verdict)
    await expect(cards.first().locator("span").first()).toBeVisible();
  });

  test("list view cards have hover elevation styles", async ({ page }) => {
    await createQuestionWithReview(page, `${Date.now()}-hover`);

    await page.goto("/reviews");
    const listBtn = page.getByRole("button", { name: /list/i });
    if (await listBtn.isVisible()) {
      await listBtn.click();
    }
    await switchToQuestionTab(page);

    const card = page.locator("main a[href^='/reviews/']").first();
    await expect(card).toBeVisible({ timeout: 5000 });

    // Card should have hover elevation classes (shadow + translate)
    const classes = await card.getAttribute("class");
    expect(classes).toContain("hover:shadow");
    expect(classes).toContain("hover:-translate-y");
  });

  test("kanban view cards have hover elevation styles", async ({ page }) => {
    await createQuestionWithReview(page, `${Date.now()}-kanban-hover`);

    await page.goto("/reviews");
    const boardBtn = page.getByRole("button", { name: /board/i });
    if (await boardBtn.isVisible()) {
      await boardBtn.click();
    }
    await switchToQuestionTab(page);

    // Kanban cards should have hover lift effect
    const card = page.locator("main a[href^='/reviews/']").first();
    await expect(card).toBeVisible({ timeout: 5000 });

    const classes = await card.getAttribute("class");
    expect(classes).toContain("hover:shadow");
    expect(classes).toContain("hover:-translate-y");
  });

  test("kanban view cards have status-colored hover borders", async ({ page }) => {
    await createQuestionWithReview(page, `${Date.now()}-kanban-border`);

    await page.goto("/reviews");
    const boardBtn = page.getByRole("button", { name: /board/i });
    if (await boardBtn.isVisible()) {
      await boardBtn.click();
    }
    await switchToQuestionTab(page);

    // In the "Pending" column, card hover border should NOT be border-primary/30 (generic)
    // It should use the column's status color
    const card = page.locator("main a[href^='/reviews/']").first();
    await expect(card).toBeVisible({ timeout: 5000 });

    const classes = await card.getAttribute("class");
    // Should NOT have the generic primary hover border
    expect(classes).not.toContain("hover:border-primary");
    // Should have a status-colored hover border
    expect(classes).toContain("hover:border-status");
  });

  test("board and list toggle works on reviews page", async ({ page }) => {
    await page.goto("/reviews");

    const listBtn = page.getByRole("button", { name: /list/i });
    const boardBtn = page.getByRole("button", { name: /board/i });

    await expect(listBtn).toBeVisible();
    await expect(boardBtn).toBeVisible();

    // Switch to board view
    await boardBtn.click();
    // Kanban columns should show verdict statuses
    await expect(page.getByText("Pending").first()).toBeVisible();
    await expect(page.getByText("Approved").first()).toBeVisible();

    // Switch back to list view
    await listBtn.click();
    await expect(page.getByRole("heading", { name: /reviews/i })).toBeVisible();
  });
});
