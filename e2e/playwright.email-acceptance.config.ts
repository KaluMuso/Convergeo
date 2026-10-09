import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./email-acceptance",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    ...devices["Pixel 7"],
    serviceWorkers: "block",
    trace: "off",
    screenshot: "off",
    video: "off",
  },
});
