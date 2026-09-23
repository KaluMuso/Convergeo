import { spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { join, relative } from "node:path";

import {
  formatScanSummary,
  scanArtifactInputs,
  scanArtifactPaths,
} from "../../scripts/ci/artifact-confidentiality-scanner.mjs";

const cases = [
  { name: "long", sentinel: "S3_SCANNER_SECRET_SENTINEL_DO_NOT_UPLOAD" },
  { name: "short-pin", sentinel: "042817" },
];
const outputRoot = join(process.cwd(), ".scanner-artifact-regression");
const config = "playwright.scanner-artifact.config.ts";

function filesUnder(root) {
  if (!existsSync(root)) return [];
  return readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
    const path = join(root, entry.name);
    return entry.isDirectory() ? filesUnder(path) : [path];
  });
}

function runCase({ name, sentinel }) {
  rmSync(outputRoot, { recursive: true, force: true });
  try {
    const run = spawnSync(
      process.execPath,
      ["./node_modules/@playwright/test/cli.js", "test", "--config", config],
      {
        cwd: process.cwd(),
        encoding: "utf8",
        env: { ...process.env, SCANNER_ARTIFACT_SENTINEL: sentinel },
      },
    );
    const transcript = `${run.stdout ?? ""}\n${run.stderr ?? ""}`;
    if (run.status === 0) throw new Error("deliberate scanner assertion unexpectedly passed");
    if (!transcript.includes("deliberate-scanner-artifact-failure")) {
      throw new Error(`scanner regression failed before the deliberate assertion (exit ${run.status})`);
    }
    const transcriptResult = scanArtifactInputs({
      inputs: [{ location: "<playwright-process-transcript>", buffer: Buffer.from(transcript) }],
      sentinels: [sentinel],
    });
    const artifactResult = scanArtifactPaths({ roots: [outputRoot], sentinels: [sentinel] });
    const transcriptSummary = formatScanSummary(transcriptResult);
    const artifactSummary = formatScanSummary(artifactResult);

    const forbiddenArtifacts = filesUnder(outputRoot).filter((path) =>
      /(?:\.zip|\.webm|\.png|error-context\.md)$/i.test(path),
    );
    if (forbiddenArtifacts.length > 0) {
      throw new Error(
        `scanner run retained forbidden diagnostics:\n${forbiddenArtifacts
          .map((path) => relative(process.cwd(), path))
          .join("\n")}`,
      );
    }
    if (transcriptSummary.verdict !== "PASS") {
      throw new Error(`scanner transcript confidentiality failure: ${JSON.stringify(transcriptSummary)}`);
    }
    if (artifactSummary.verdict !== "PASS") {
      throw new Error(`scanner artifact confidentiality failure: ${JSON.stringify(artifactSummary)}`);
    }

    const evidenceRoot = process.env.SCANNER_ARTIFACT_EVIDENCE_DIR;
    if (evidenceRoot) {
      mkdirSync(evidenceRoot, { recursive: true });
      cpSync(outputRoot, join(evidenceRoot, name), { recursive: true });
    }
    return {
      name,
      deliberateFailureExit: run.status,
      artifactFiles: artifactSummary.files,
      representations: artifactSummary.representations,
      decodedArtifacts: artifactSummary.archives + artifactSummary.base64Payloads,
      sentinelMatches: 0,
    };
  } finally {
    if (process.env.KEEP_SCANNER_ARTIFACT_EVIDENCE !== "1") {
      rmSync(outputRoot, { recursive: true, force: true });
    }
  }
}

console.log(JSON.stringify({ verdict: "PASS", cases: cases.map(runCase) }));
