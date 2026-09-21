import { defineConfig, devices } from "@playwright/test";

const root = ".scanner-artifact-regression";

export default defineConfig({
  testDir: "./artifact-regression",
  testMatch: "scanner-secret.spec.ts",
  retries: 1,
  workers: 1,
  reporter: [
    ["list"],
    ["html", { outputFolder: `${root}/playwright-report`, open: "never" }],
    ["json", { outputFile: `${root}/results/results.json` }],
    ["junit", { outputFile: `${root}/results/junit.xml` }],
  ],
  outputDir: `${root}/results/artifacts`,
  use: {
    ...devices["Desktop Chrome"],
    trace: "on-first-retry",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
