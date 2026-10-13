#!/usr/bin/env node
/** Strict portal/source proof before a private, non-certifying password diagnostic. */

import { execFile, spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { promisify } from "node:util";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

import { emailAcceptanceConfig } from "../../e2e/email-acceptance/safety.ts";
import { probeStagingAccess } from "./e2e-staging-probe.mjs";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const execFileAsync = promisify(execFile);
const PRIVATE_ENV_KEYS = [
  "PATH",
  "HOME",
  "TMPDIR",
  "TEMP",
  "TMP",
  "SystemRoot",
  "USERPROFILE",
  "E2E_EXPECT_SHA",
  "E2E_BASE_URL",
  "E2E_VENDOR_BASE_URL",
  "E2E_CUSTOMER_EMAIL_PASSWORD",
  "E2E_VENDOR_EMAIL_PASSWORD",
  "VERCEL_AUTOMATION_BYPASS_SECRET",
  "VERCEL_AUTOMATION_BYPASS_SECRET_CUSTOMER",
  "VERCEL_AUTOMATION_BYPASS_SECRET_VENDOR",
];

export function privateEmailEnvironment(env) {
  const privateEnv = Object.fromEntries(
    PRIVATE_ENV_KEYS.filter((key) => typeof env[key] === "string").map((key) => [key, env[key]]),
  );
  return {
    ...privateEnv,
    E2E_STRICT_SHA: "true",
    E2E_EMAIL_PROBE_SHA: env.E2E_EXPECT_SHA,
    PLAYWRIGHT_NO_COPY_PROMPT: "1",
    CERTIFICATION_MODE: "diagnostic-staging",
    SMS_OTP_TRANSPORT: "disabled",
    WAHA_OTP_READY: "false",
    CI: "true",
  };
}

async function sourceProof() {
  const options = { cwd: REPO_ROOT, timeout: 5000, maxBuffer: 1024 * 1024 };
  const { stdout: head } = await execFileAsync("git", ["rev-parse", "HEAD"], options);
  await execFileAsync("git", ["diff", "HEAD", "--quiet", "--"], options);
  const { stdout: untracked } = await execFileAsync(
    "git",
    ["ls-files", "--others", "--exclude-standard"],
    options,
  );
  return { sha: head.trim(), clean: untracked.length === 0 };
}

async function verifyRuntime() {
  const installed = JSON.parse(
    await readFile(path.join(REPO_ROOT, "e2e/node_modules/playwright/package.json"), "utf8"),
  );
  if (installed.version !== "1.56.1") throw new Error("unverified capture behavior");
}

export async function executePlaywright(env, spawnChild = spawn) {
  const cwd = path.join(REPO_ROOT, "e2e");
  const executable = path.join(cwd, "node_modules", ".bin", "playwright");
  return new Promise((resolve, reject) => {
    const child = spawnChild(
      executable,
      ["test", "--config=playwright.email-acceptance.config.ts"],
      {
        cwd,
        env,
        stdio: "ignore",
        shell: false,
      },
    );
    child.once("error", () => reject(new Error("private email diagnostic could not start")));
    child.once("exit", (code) => resolve(code === 0 ? 0 : 1));
  });
}

export async function runEmailAcceptance(
  env = process.env,
  {
    probe = probeStagingAccess,
    execute = executePlaywright,
    verifySource = sourceProof,
    runtime = verifyRuntime,
  } = {},
) {
  try {
    const config = emailAcceptanceConfig(env, { requireProbe: false });
    const checkSource = async () => {
      const proof = await verifySource();
      if (proof?.sha !== env.E2E_EXPECT_SHA || proof.clean !== true) {
        throw new Error("source proof failed");
      }
    };
    await checkSource();
    const strictEnv = { ...env, E2E_STRICT_SHA: "true" };
    for (const portal of ["customer", "vendor"]) {
      const result = await probe(strictEnv, { portal });
      if (
        result?.verdict !== "PASS" ||
        result.shaVerified !== true ||
        result.shaSkipped !== false ||
        result.portal !== portal ||
        result.host !== new URL(config[portal].origin).host ||
        result.env !== "staging" ||
        result.buildIdPrefix !== env.E2E_EXPECT_SHA.slice(0, 12)
      )
        throw new Error("portal proof failed");
    }
    await runtime();
    await checkSource();
    const code = await execute(privateEmailEnvironment(env));
    await checkSource();
    return code === 0 ? 0 : 1;
  } catch {
    // Probe/child exceptions may include credentials, bodies or private URLs.
    throw new Error("email/password diagnostic failed; private details suppressed");
  }
}

const isMain =
  process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;
if (isMain) {
  runEmailAcceptance()
    .then((code) => {
      process.exitCode = code;
    })
    .catch(() => {
      console.error("email/password diagnostic failed; private details suppressed");
      process.exitCode = 1;
    });
}
