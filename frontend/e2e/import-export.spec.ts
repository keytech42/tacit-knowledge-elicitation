import { test, expect } from "@playwright/test";
import path from "path";
import fs from "fs";
import os from "os";

test.describe("Question Import/Export", () => {
  test("export and import buttons visible on admin queue", async ({ page }) => {
    await page.goto("/admin/questions");
    await expect(page.getByRole("button", { name: "Export" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Import" })).toBeVisible();
  });

  test("export modal opens with filters and download", async ({ page }) => {
    // Create a question first so export has data
    await page.goto("/questions/new");
    await page.getByPlaceholder("What do you want to know?").fill(`E2E Export Test ${Date.now()}`);
    await page
      .getByPlaceholder("Provide context, constraints, and what a good answer looks like...")
      .fill("Body for export e2e test.");
    await page.getByRole("button", { name: "Save as Draft" }).click();
    await page.waitForURL("**/questions/**");

    // Go to admin queue and open export modal
    await page.goto("/admin/questions");
    await page.getByRole("button", { name: "Export" }).click();

    // Modal should show filters and match count
    await expect(page.getByText("Export Questions")).toBeVisible();
    await expect(page.getByText(/\d+ question/)).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole("button", { name: "Download JSON" })).toBeVisible();

    // Download the file
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Download JSON" }).click(),
    ]);
    const filePath = await download.path();
    expect(filePath).toBeTruthy();

    const content = JSON.parse(fs.readFileSync(filePath!, "utf-8"));
    expect(content.version).toBe("1.0");
    expect(content.questions.length).toBeGreaterThan(0);
    expect(content.questions[0]).toHaveProperty("title");
    expect(content.questions[0]).toHaveProperty("_metadata");
  });

  test("import modal validates and creates questions", async ({ page }) => {
    // Prepare a JSON file to import
    const importData = {
      version: "1.0",
      questions: [
        {
          title: `E2E Imported Q ${Date.now()}`,
          body: "Body from import e2e test.",
          category: "E2E",
          answer_options: [
            { body: "Option Alpha", display_order: 1 },
            { body: "Option Beta", display_order: 2 },
          ],
        },
      ],
    };
    const tmpFile = path.join(os.tmpdir(), `import-test-${Date.now()}.json`);
    fs.writeFileSync(tmpFile, JSON.stringify(importData));

    await page.goto("/admin/questions");
    await page.getByRole("button", { name: "Import" }).click();
    await expect(page.getByText("Import Questions")).toBeVisible();

    // Upload the file
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(tmpFile);

    // Preview table should appear
    await expect(page.getByText("1 question found")).toBeVisible();
    await expect(page.getByText("Valid")).toBeVisible();
    await expect(page.getByText(importData.questions[0].title.slice(0, 30))).toBeVisible();

    // Import
    await page.getByRole("button", { name: /Import 1 Question/i }).click();

    // Success toast
    await expect(page.getByText(/Created 1 question/)).toBeVisible({ timeout: 5000 });

    // Clean up
    fs.unlinkSync(tmpFile);
  });

  test("import modal shows validation errors for bad file", async ({ page }) => {
    const badData = {
      version: "1.0",
      questions: [
        { title: "", body: "has body but no title" },
        { title: "Valid title", body: "" },
      ],
    };
    const tmpFile = path.join(os.tmpdir(), `import-bad-${Date.now()}.json`);
    fs.writeFileSync(tmpFile, JSON.stringify(badData));

    await page.goto("/admin/questions");
    await page.getByRole("button", { name: "Import" }).click();

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(tmpFile);

    // Should show errors
    await expect(page.getByText("2 with errors")).toBeVisible();
    await expect(page.getByText("Missing title")).toBeVisible();
    await expect(page.getByText("Missing body")).toBeVisible();

    // Import button should show fix message and be disabled
    const importBtn = page.getByRole("button", { name: /Fix 2 errors/i });
    await expect(importBtn).toBeVisible();
    await expect(importBtn).toBeDisabled();

    fs.unlinkSync(tmpFile);
  });

  test("roundtrip: export then import produces drafts", async ({ page }) => {
    // Create a question
    await page.goto("/questions/new");
    await page.getByPlaceholder("What do you want to know?").fill(`E2E Roundtrip ${Date.now()}`);
    await page
      .getByPlaceholder("Provide context, constraints, and what a good answer looks like...")
      .fill("Roundtrip e2e body.");
    await page.getByRole("button", { name: "Save as Draft" }).click();
    await page.waitForURL("**/questions/**");

    // Export
    await page.goto("/admin/questions");
    await page.getByRole("button", { name: "Export" }).click();
    await expect(page.getByText(/\d+ question/)).toBeVisible({ timeout: 5000 });
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Download JSON" }).click(),
    ]);
    const filePath = await download.path();
    const content = fs.readFileSync(filePath!, "utf-8");

    // Write exported content to a temp file for import
    const tmpFile = path.join(os.tmpdir(), `roundtrip-${Date.now()}.json`);
    fs.writeFileSync(tmpFile, content);

    // Import
    await page.goto("/admin/questions");
    await page.getByRole("button", { name: "Import" }).click();
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(tmpFile);

    await expect(page.getByText(/\d+ question.*found/)).toBeVisible();
    await page.getByRole("button", { name: /Import \d+ Question/i }).click();
    await expect(page.getByText(/Created \d+ question/)).toBeVisible({ timeout: 5000 });

    fs.unlinkSync(tmpFile);
  });
});
