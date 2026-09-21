import { expect, test as base } from "./test-base";

/**
 * Artifact policy for the one browser journey that enters a live scanner PIN.
 * Other specs retain the repository's normal failure diagnostics.
 */
export const SCANNER_ARTIFACT_POLICY = {
  trace: "off",
  video: "off",
  screenshot: "off",
} as const;

type ScannerArtifactWorkerFixtures = {
  _scannerPromptSnapshotGuard: boolean;
};

export const test = base.extend<{}, ScannerArtifactWorkerFixtures>({
  _scannerPromptSnapshotGuard: [
    async ({}, use) => {
      const previous = process.env.PLAYWRIGHT_NO_COPY_PROMPT;
      process.env.PLAYWRIGHT_NO_COPY_PROMPT = "1";
      try {
        await use(true);
      } finally {
        if (previous === undefined) {
          delete process.env.PLAYWRIGHT_NO_COPY_PROMPT;
        } else {
          process.env.PLAYWRIGHT_NO_COPY_PROMPT = previous;
        }
      }
    },
    { auto: true, scope: "worker" },
  ],
});

export { expect };
