import { expect, test as base, type Page, type TestInfo } from "@playwright/test";

const EXAMPLE = "Help our four-person team turn a hackathon idea into a focused, demo-ready plan.";
const INITIAL_STATUS = "Ready when you are. Add a brief to begin.";
const screenshotOptions = {
  fullPage: true,
  animations: "disabled" as const,
  caret: "hide" as const,
  // Hide only Next's development overlay during capture, not application UI.
  style: "nextjs-portal { visibility: hidden !important; }",
};

const test = base.extend<{ monitoredPage: Page }>({
  monitoredPage: async ({ page }, runTest, testInfo) => {
    const errors: string[] = [];
    page.on("console", message => {
      if (message.type() === "error") errors.push(`console: ${message.text()}`);
    });
    page.on("pageerror", error => errors.push(`pageerror: ${error.message}`));
    try {
      await runTest(page);
    } finally {
      await testInfo.attach("browser-errors", {
        body: JSON.stringify(errors, null, 2),
        contentType: "application/json",
      });
      expect(errors, "No console errors or uncaught page exceptions").toEqual([]);
    }
  },
});

async function noOverflow(page: Page) {
  await expect.poll(() => page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth,
  ), { message: "The page should not overflow horizontally" }).toBe(true);
}

async function capture(page: Page, testInfo: TestInfo, state: string) {
  await noOverflow(page);
  const name = `ui-lab-${state}.png`;
  const path = testInfo.outputPath(`${testInfo.project.name}-${name}`);
  await page.screenshot({ ...screenshotOptions, path });
  await testInfo.attach(`${testInfo.project.name}-${state}`, { path, contentType: "image/png" });
  if (process.env.UI_LAB_VISUAL === "1") {
    await expect(page).toHaveScreenshot(name, {
      ...screenshotOptions,
      maxDiffPixels: 0,
      threshold: 0,
    });
  }
}

async function finishMockRun(page: Page) {
  // Three 1.1s mock stages: advance virtual time, not wall-clock sleep.
  await page.clock.runFor(3_300);
}

test.beforeEach(async ({ monitoredPage: page, browser }, testInfo) => {
  testInfo.annotations.push({ type: "browser", description: `Microsoft Edge ${browser.version()}` });
  await page.clock.install({ time: new Date("2026-11-14T10:00:00Z") });
  const response = await page.goto("/ui-lab", { waitUntil: "load" });
  expect(response?.status(), "UI lab must be served by the existing server").toBe(200);
  await expect(page.getByRole("heading", { name: "From intent to a clear next step." })).toBeVisible();
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
  // Verify client handlers are ready before pausing time or testing submission.
  await page.getByRole("button", { name: "Use example brief", exact: true }).click();
  const brief = page.getByRole("textbox", { name: "What would you like to accomplish?" });
  await expect(brief).toHaveValue(EXAMPLE);
  await brief.fill("");
  await expect(page.getByRole("button", { name: "Run mock workflow", exact: true })).toBeDisabled();
  await page.clock.pauseAt(new Date("2026-11-14T11:00:00Z"));
});

test("validates input and submits a structured mock result", async ({ monitoredPage: page }, testInfo) => {
  const brief = page.getByRole("textbox", { name: "What would you like to accomplish?" });
  const run = page.getByRole("button", { name: "Run mock workflow", exact: true });
  await expect(page.getByRole("status")).toHaveText(INITIAL_STATUS);
  await capture(page, testInfo, "empty");
  await brief.fill("   ");
  await expect(run).toBeDisabled();
  await brief.fill("x".repeat(2_000));
  await brief.press("End");
  await brief.press("y");
  await expect(brief).toHaveValue("x".repeat(2_000));
  await page.getByRole("button", { name: "Use example brief", exact: true }).click();
  await expect(brief).toHaveValue(EXAMPLE);
  await brief.focus();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Use example brief", exact: true })).toBeFocused();
  await run.click();
  await expect(brief).toBeDisabled();
  await expect(page.getByRole("button", { name: "Working on your brief" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Cancel", exact: true })).toBeFocused();
  await expect(page.getByRole("status")).toContainText("Step 1 of 3");
  await capture(page, testInfo, "running");
  await page.clock.runFor(1_100);
  await expect(page.getByRole("status")).toContainText("Step 2 of 3");
  await page.clock.runFor(1_100);
  await expect(page.getByRole("status")).toContainText("Step 3 of 3");
  await page.clock.runFor(1_100);
  await expect(page.getByRole("status")).toContainText("Mock run complete");
  await expect(page.getByRole("heading", { name: "03 Review the outcome" })).toBeFocused();
  await expect(page.getByRole("region", { name: "Your submitted brief" })).toContainText(EXAMPLE);
  await expect(page.getByText("Fixed mock output for interface testing.", { exact: false })).toBeVisible();
  await capture(page, testInfo, "success");
  await brief.fill("A revised goal for the next run.");
  await expect(page.getByRole("status").filter({ hasText: "Previous run:" })).toBeVisible();
  await expect(run).toBeEnabled();
  await noOverflow(page);
});

test("cancels immediately without late updates and can run again", async ({ monitoredPage: page }, testInfo) => {
  const brief = page.getByRole("textbox", { name: "What would you like to accomplish?" });
  const run = page.getByRole("button", { name: "Run mock workflow", exact: true });
  await brief.fill("Keep this brief after cancelling.");
  await run.click();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(brief).toBeFocused();
  await expect(brief).toHaveValue("Keep this brief after cancelling.");
  await expect(page.getByRole("status")).toContainText("Run cancelled");
  // Cross the whole completion window to detect surviving interval callbacks.
  await page.clock.runFor(5_000);
  await expect(page.getByRole("status")).toContainText("Run cancelled");
  await expect(page.getByText("SIMULATION COMPLETE", { exact: true })).toHaveCount(0);
  await expect(run).toBeEnabled();
  await capture(page, testInfo, "cancelled");
  await run.click();
  await finishMockRun(page);
  await expect(page.getByRole("status")).toContainText("Mock run complete");
  await expect(page.getByRole("region", { name: "Your submitted brief" })).toContainText("Keep this brief after cancelling.");
  await page.getByRole("button", { name: "Reset preview", exact: true }).click();
  await expect(brief).toBeFocused();
  await expect(page.getByRole("status")).toContainText("Preview reset");
});

test("recovers from a simulated failure with one-click retry", async ({ monitoredPage: page }, testInfo) => {
  const brief = page.getByRole("textbox", { name: "What would you like to accomplish?" });
  const failure = page.getByRole("checkbox", { name: "Simulate a failure to test recovery" });
  const result = page.getByRole("region", { name: "03 Review the outcome" });
  await brief.fill("Preserve this goal during failure recovery.");
  await failure.check();
  await page.getByRole("button", { name: "Run mock workflow", exact: true }).click();
  await finishMockRun(page);
  await expect(result.getByRole("alert")).toContainText("A deliberate bump in the road.");
  await expect(page.getByRole("heading", { name: "03 Review the outcome" })).toBeFocused();
  await capture(page, testInfo, "error");
  await page.getByRole("button", { name: "Retry mock workflow", exact: true }).click();
  await expect(failure).not.toBeChecked();
  await expect(brief).toHaveValue("Preserve this goal during failure recovery.");
  await expect(page.getByRole("button", { name: "Cancel", exact: true })).toBeFocused();
  await finishMockRun(page);
  await expect(page.getByRole("status")).toContainText("Mock run complete");
  await expect(result.getByRole("alert")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Your submitted brief" })).toContainText("Preserve this goal during failure recovery.");
  await capture(page, testInfo, "retry-success");
});
