import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: "ui-lab.spec.ts",
  fullyParallel: false,
  workers: 1,
  forbidOnly: true,
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 7_000 },
  outputDir: "build/browser-tests/results",
  reporter: [
    ["list"],
    ["html", { outputFolder: "build/browser-tests/report", open: "never" }],
  ],
  // Missing or changed baselines must fail comparison, never create new ones.
  updateSnapshots: "none",
  snapshotPathTemplate:
    "{testDir}/../build/browser-tests/baselines/{platform}/{projectName}/{arg}{ext}",
  use: {
    baseURL: process.env.UI_LAB_BASE_URL || "http://localhost:3000",
    browserName: "chromium",
    channel: "msedge",
    headless: true,
    actionTimeout: 7_000,
    navigationTimeout: 20_000,
    colorScheme: "light",
    reducedMotion: "reduce",
    locale: "en-GB",
    timezoneId: "Europe/London",
    deviceScaleFactor: 1,
    serviceWorkers: "block",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "edge-desktop-1440", use: { channel: "msedge", viewport: { width: 1440, height: 900 } } },
    { name: "edge-tablet-768", use: { channel: "msedge", viewport: { width: 768, height: 1024 } } },
    { name: "edge-mobile-390", use: { channel: "msedge", viewport: { width: 390, height: 844 } } },
  ],
  // Deliberately no webServer: use an existing server without managing its process.
});
