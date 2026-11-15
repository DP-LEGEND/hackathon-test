// Node 26: node scripts/record_backup_demo.ts (app and service already running).
import { mkdir, mkdtemp, rm, stat } from "node:fs/promises";
import { dirname, join } from "node:path";
import { setTimeout as pause } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import { chromium, expect, type BrowserContext, type Locator, type Page } from "@playwright/test";

const baseURL = new URL(process.env.GHOST_DEMO_URL || "http://localhost:3000");
const size = { width: 1920, height: 1080 };
const outputDirectory = fileURLToPath(new URL("../out", import.meta.url));
const outputFile = join(outputDirectory, "backup-demo.webm");
const heroId = "7178110a0b06-swing-0027";
const backhandId = "sample_2116_backhand_stereo";

async function savedSamplesOnly(context: BrowserContext, errors: string[]) {
  // Guard against accidentally recording a live upload/coach request or a remote asset.
  // The real local catalogue probe is allowed; all selected swing data comes from /swings/.
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const localRead = url.origin === baseURL.origin && request.method() === "GET";
    const liveData = url.pathname.startsWith("/api/") && !["/api/health", "/api/swings"].includes(url.pathname);
    if (!localRead || liveData) {
      errors.push(`Blocked non-sample request: ${request.method()} ${url.origin}${url.pathname}`);
      await route.abort();
      return;
    }
    await route.continue();
  });
}

async function walkDemo(page: Page, holdMilliseconds: number, errors: string[]) {
  page.setDefaultTimeout(30_000);
  page.setDefaultNavigationTimeout(60_000);
  page.on("pageerror", (error) => errors.push(error.message));
  const stage = page.getByRole("region", { name: "Swing replay" });

  async function beat(name: string, focus: Locator) {
    await focus.scrollIntoViewIfNeeded();
    await page.evaluate(() => document.fonts.ready);
    await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
    expect(errors, "Recording must use healthy local saved samples").toEqual([]);
    if (holdMilliseconds) {
      console.log(name);
      // Intentional narration time, after the UI is ready (not a loading timeout).
      await pause(holdMilliseconds);
    }
  }

  async function playingReplay() {
    await expect(stage.locator("canvas")).toBeVisible();
    await expect(stage.getByRole("button", { name: "Pause", exact: true })).toBeVisible();
    const slider = stage.getByRole("slider", { name: "Swing time" });
    const firstFrame = await slider.inputValue();
    await expect.poll(() => slider.inputValue(), { message: "3D replay must advance" }).not.toBe(firstFrame);
  }

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("See your swing. Find your edge.");
  await beat("1. Landing", page.getByRole("heading", { level: 1 }));
  await page.getByRole("link", { name: "Watch demo", exact: true }).click();
  const hero = page.getByRole("button", { name: new RegExp(heroId) });
  await expect(hero).toContainText("Saved sample");
  await beat("2. Load the saved hero forehand (no live upload)", hero);
  await hero.click();
  await expect(stage.getByText("Over-rotation: hips turn 157°", { exact: true })).toBeVisible();
  await expect(stage.locator("blockquote")).toHaveText("“Turn a little less and stay balanced through the ball.”");
  await playingReplay();
  await beat("3. The coach's fault and cue", stage);

  await page.getByRole("button", { name: "Show the ghost", exact: true }).click();
  const fix = page.getByRole("button", { name: /^Turn shoulders less 52\.6°/ });
  await expect(fix).toHaveAttribute("aria-busy", "false");
  await fix.click();
  await expect(fix).toHaveAttribute("aria-pressed", "true");
  await expect(fix).toContainText("Coach's pick");
  await stage.getByRole("button", { name: "Side by side", exact: true }).click();
  await expect(stage.getByRole("button", { name: "Overlay", exact: true })).toHaveAttribute("aria-pressed", "true");
  await stage.getByRole("button", { name: "0.25× slow-mo", exact: true }).click();
  await playingReplay();
  await beat("4. Your swing and ghost, side by side", stage);

  // Court view alone only moves the camera; this step actually enables the ball paths.
  await page.getByRole("button", { name: "Show the court", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Where the ball goes", exact: true })).toBeVisible();
  await expect(stage.getByText("PREDICTED · you · in", { exact: true })).toBeVisible();
  await expect(stage.getByText("PREDICTED · ghost · in", { exact: true })).toBeVisible();
  await expect(stage.getByRole("button", { name: "Overlay", exact: true })).toHaveAttribute("aria-pressed", "true");
  await playingReplay();
  await beat("5. Side-by-side PREDICTED ball paths", stage);

  const changes = page.getByRole("region", { name: "What the fix changes", exact: true });
  const shoulder = changes.getByRole("row", { name: /Shoulder turn/ });
  await expect(shoulder).toContainText("137.6°");
  await expect(shoulder).toContainText("85°");
  await beat("6. The over-rotation fix, measured by code", changes);
  await beat("7. Predicted numbers and their caveats", page.getByRole("region", { name: "Ball PREDICTED", exact: true }));

  await page.getByRole("button", { name: "Try another swing", exact: true }).click();
  const backhand = page.getByRole("button", { name: new RegExp(backhandId) });
  await expect(backhand).toContainText("Saved sample");
  await beat("8. Pick the saved backhand", backhand);
  await backhand.click();
  await expect(stage.getByText("No fault found in what was checked", { exact: true })).toBeVisible();
  await expect(stage.locator("blockquote")).toHaveText("“Nothing to fix in what the coach could check.”");
  await playingReplay();
  // The backhand has no coached fix: finish here, rather than showing an example edit.
  await beat("9. Backhand: nothing to fix in what was checked", stage);
  expect(errors).toEqual([]);
}

async function main() {
  if (!["http:", "https:"].includes(baseURL.protocol) || !["localhost", "127.0.0.1", "[::1]"].includes(baseURL.hostname)) {
    throw new Error("GHOST_DEMO_URL must point to the locally running app.");
  }
  const browser = await chromium.launch();
  try {
    const options = {
      baseURL: baseURL.origin,
      viewport: size,
      deviceScaleFactor: 1,
      reducedMotion: "no-preference" as const,
      serviceWorkers: "block" as const,
    };
    // Compile lazy routes and check both samples before creating the recorded page.
    const warmup = await browser.newContext(options);
    try {
      const health = await warmup.request.get("/api/health");
      expect(health.ok(), "Start the local app and Python service before recording").toBe(true);
      const errors: string[] = [];
      await savedSamplesOnly(warmup, errors);
      await walkDemo(await warmup.newPage(), 0, errors);
    } finally {
      await warmup.close();
    }

    await mkdir(outputDirectory, { recursive: true });
    const recordingDirectory = await mkdtemp(join(outputDirectory, ".recording-"));
    let context: BrowserContext | undefined;
    try {
      context = await browser.newContext({ ...options, recordVideo: { dir: recordingDirectory, size } });
      const page = await context.newPage();
      const video = page.video();
      if (!video) throw new Error("Playwright did not start video recording.");
      const errors: string[] = [];
      await savedSamplesOnly(context, errors);
      await walkDemo(page, 3000, errors);
      await context.close(); // Flush the encoder before saving the named WebM.
      await video.saveAs(outputFile);
    } finally {
      await context?.close();
      // Only remove this run's private temporary folder, never the named output video.
      if (dirname(recordingDirectory) !== outputDirectory) throw new Error("Unexpected recording directory.");
      await rm(recordingDirectory, { recursive: true, force: true });
    }
    console.log(`Saved ${outputFile} (${(await stat(outputFile)).size} bytes)`);
  } finally {
    await browser.close();
  }
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
