#!/usr/bin/env node
/** Strict, read-only portal proof before the isolated email diagnostic starts. */

import { spawn } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

import { emailAcceptanceConfig } from "../../e2e/email-acceptance/safety.ts";
import { probeStagingAccess } from "./e2e-staging-probe.mjs";

const REPO_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);

async function executePlaywright(env) {
  const cwd = path.join(REPO_ROOT, "e2e");
  const executable = path.join(cwd, "node_modules", ".bin", "playwright");
  return new Promise((resolve, reject) => {
    const child = spawn(
      executable,
      ["test", "--config=playwright.email-acceptance.config.ts"],
      {
        cwd,
        env,
        stdio: "inherit",
      },
    );
    child.once("error", reject);
    child.once("exit", (code) => resolve(code ?? 1));
  });
}

export async function runEmailAcceptance(
  env = process.env,
  { probe = probeStagingAccess, execute = executePlaywright } = {},
) {
  // Validate destinations and synthetic credentials without revealing values.
  emailAcceptanceConfig(env, { requireProbe: false });
  const strictEnv = { ...env, E2E_STRICT_SHA: "true" };
  for (const portal of ["customer", "vendor"]) {
    const result = await probe(strictEnv, { portal });
    if (
      result?.verdict !== "PASS" ||
      result.shaVerified !== true ||
      result.shaSkipped === true
    ) {
      throw new Error(
        `${portal} strict staging SHA probe failed; browser did not start`,
      );
    }
  }
  return execute({ ...strictEnv, E2E_EMAIL_PROBE_SHA: env.E2E_EXPECT_SHA });
}

const isMain =
  process.argv[1] &&
  import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;
if (isMain) {
  runEmailAcceptance()
    .then((code) => {
      process.exitCode = code;
    })
    .catch((error) => {
      console.error(
        error instanceof Error
          ? error.message
          : "email acceptance preflight failed",
      );
      process.exitCode = 1;
    });
}
