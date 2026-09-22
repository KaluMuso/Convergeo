#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import process from "node:process";
import { fileURLToPath } from "node:url";

const BLOCKING_SEVERITIES = new Set(["high", "critical"]);

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function parsePnpmAudit(raw) {
  if (typeof raw !== "string" || raw.trim() === "") {
    throw new Error("pnpm audit produced empty output");
  }

  let data;
  try {
    data = JSON.parse(raw);
  } catch (error) {
    throw new Error(`pnpm audit produced malformed JSON: ${error.message}`);
  }

  if (!isRecord(data)) {
    throw new Error("pnpm audit JSON root must be an object");
  }
  if (isRecord(data.error)) {
    const message =
      typeof data.error.message === "string"
        ? data.error.message
        : "unknown error";
    throw new Error(`pnpm audit reported a command error: ${message}`);
  }
  if (!isRecord(data.advisories)) {
    throw new Error("pnpm audit JSON is missing the advisories object");
  }
  if (!isRecord(data.metadata) || !isRecord(data.metadata.vulnerabilities)) {
    throw new Error("pnpm audit JSON is missing vulnerability metadata");
  }

  return data;
}

export function blockingAdvisories(data) {
  return Object.values(data.advisories)
    .filter(
      (advisory) =>
        isRecord(advisory) && BLOCKING_SEVERITIES.has(advisory.severity),
    )
    .map((advisory) => ({
      id: advisory.github_advisory_id || advisory.id || "UNKNOWN",
      module: advisory.module_name || "unknown-package",
      severity: advisory.severity,
      vulnerableVersions: advisory.vulnerable_versions || "unknown",
      patchedVersions: advisory.patched_versions || "unknown",
    }))
    .sort((left, right) =>
      `${left.severity}:${left.id}`.localeCompare(
        `${right.severity}:${right.id}`,
      ),
    );
}

export function assessAuditProcess({ status, stdout, stderr = "", error }) {
  if (error) {
    throw new Error(`failed to execute pnpm audit: ${error.message}`);
  }
  if (!Number.isInteger(status)) {
    throw new Error("pnpm audit did not return an exit status");
  }
  if (status !== 0 && status !== 1) {
    const detail = stderr.trim() ? `: ${stderr.trim()}` : "";
    throw new Error(
      `pnpm audit command failed with exit code ${status}${detail}`,
    );
  }

  const data = parsePnpmAudit(stdout);
  return { data, blockers: blockingAdvisories(data) };
}

function outputPath(args) {
  const index = args.indexOf("--output");
  if (index === -1) return null;
  if (!args[index + 1]) throw new Error("--output requires a path");
  return args[index + 1];
}

export function runAudit({
  args = process.argv.slice(2),
  spawn = spawnSync,
} = {}) {
  const result = spawn("pnpm", ["audit", "--json"], {
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
    shell: process.platform === "win32",
  });

  const destination = outputPath(args);
  if (destination && typeof result.stdout === "string") {
    writeFileSync(destination, result.stdout, "utf8");
  }

  return assessAuditProcess(result);
}

function main() {
  try {
    const { blockers } = runAudit();
    if (blockers.length > 0) {
      console.error("Blocking high/critical dependency advisories:");
      for (const blocker of blockers) {
        console.error(
          `- ${blocker.severity} ${blocker.id} ${blocker.module} ` +
            `(vulnerable ${blocker.vulnerableVersions}; patched ${blocker.patchedVersions})`,
        );
      }
      return 1;
    }

    console.log("pnpm audit: no high/critical advisories");
    return 0;
  } catch (error) {
    console.error(`pnpm audit gate error: ${error.message}`);
    return 2;
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  process.exitCode = main();
}
