import { defineConfig } from "@playwright/test";

import baseConfig from "./playwright.config";

// Performance keeps the original 360px smoke alongside the current 390px run.
// The normal certification matrix and its spec classification stay unchanged.
const projects = ["mobile-360", "mobile-390"].map((name) => {
  const project = baseConfig.projects?.find((candidate) => candidate.name === name);
  if (!project?.use?.viewport) {
    throw new Error(`Accessibility smoke requires the configured ${name} viewport`);
  }
  return {
    ...project,
    testMatch: ["a11y-smoke.spec.ts"],
    metadata: {
      ...project.metadata,
      perfA11yViewport: project.use.viewport,
    },
  };
});

export default defineConfig({ ...baseConfig, projects });
