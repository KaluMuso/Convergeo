#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import process from "node:process";
import { fileURLToPath } from "node:url";

const SEVERITIES = ["info", "low", "moderate", "high", "critical"];
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
  if (Object.hasOwn(data, "error")) {
    const message =
      isRecord(data.error) && typeof data.error.message === "string"
        ? data.error.message
        : String(data.error);
    throw new Error(`pnpm audit reported a command error: ${message}`);
  }
  if (!isRecord(data.advisories)) {
    throw new Error("pnpm audit JSON is missing the advisories object");
  }
  if (!isRecord(data.metadata) || !isRecord(data.metadata.vulnerabilities)) {
    throw new Error("pnpm audit JSON is missing vulnerability metadata");
  }

  // pnpm 9.15.4 counts finding records, which need not equal the number of
  // unique advisories or the number of affected dependency paths.
  const counts = Object.fromEntries(
    SEVERITIES.map((severity) => [severity, 0]),
  );
  for (const severity of SEVERITIES) {
    const count = data.metadata.vulnerabilities[severity];
    if (!Number.isSafeInteger(count) || count < 0) {
      throw new Error(
        `pnpm audit has an invalid ${severity} vulnerability count`,
      );
    }
  }
  for (const severity of Object.keys(data.metadata.vulnerabilities)) {
    if (!SEVERITIES.includes(severity)) {
      throw new Error(`pnpm audit has an unknown ${severity} severity count`);
    }
  }
  for (const [key, advisory] of Object.entries(data.advisories)) {
    if (!isRecord(advisory)) {
      throw new Error(`pnpm audit advisory ${key} must be an object`);
    }
    if (!SEVERITIES.includes(advisory.severity)) {
      throw new Error(`pnpm audit advisory ${key} has an invalid severity`);
    }
    if (
      typeof advisory.module_name !== "string" ||
      advisory.module_name.trim() === ""
    ) {
      throw new Error(`pnpm audit advisory ${key} has no module name`);
    }
    if (!Array.isArray(advisory.findings) || advisory.findings.length === 0) {
      throw new Error(`pnpm audit advisory ${key} has no findings`);
    }
    for (const finding of advisory.findings) {
      if (
        !isRecord(finding) ||
        typeof finding.version !== "string" ||
        finding.version.trim() === "" ||
        !Array.isArray(finding.paths) ||
        finding.paths.length === 0 ||
        finding.paths.some((path) => typeof path !== "string" || path === "")
      ) {
        throw new Error(`pnpm audit advisory ${key} has a malformed finding`);
      }
    }
    counts[advisory.severity] += advisory.findings.length;
  }
  for (const severity of SEVERITIES) {
    if (data.metadata.vulnerabilities[severity] !== counts[severity]) {
      throw new Error(
        `pnpm audit ${severity} count does not match advisory findings`,
      );
    }
  }
  if (
    Object.hasOwn(data, "muted") &&
    (!Array.isArray(data.muted) || data.muted.length !== 0)
  ) {
    throw new Error("pnpm audit contains muted or malformed advisories");
  }

  return data;
}

export function blockingAdvisories(data) {
  return Object.entries(data.advisories)
    .filter(([, advisory]) => BLOCKING_SEVERITIES.has(advisory.severity))
    .map(([key, advisory]) => ({
      id: advisory.github_advisory_id || advisory.id || key,
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
  const findings = SEVERITIES.reduce(
    (total, severity) => total + data.metadata.vulnerabilities[severity],
    0,
  );
  if ((status === 0 && findings > 0) || (status === 1 && findings === 0)) {
    throw new Error("pnpm audit exit status disagrees with its finding counts");
  }
  return { data, blockers: blockingAdvisories(data) };
}

export function gateExitCode({ blockers }) {
  return blockers.length > 0 ? 1 : 0;
}

function evidencePaths(args) {
  const paths = {};
  const names = new Map([
    ["--output", "stdout"],
    ["--stderr-output", "stderr"],
    ["--status-output", "status"],
  ]);
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--") continue;
    const name = names.get(arg);
    if (
      !name ||
      paths[name] ||
      !args[index + 1] ||
      args[index + 1].startsWith("--")
    ) {
      throw new Error(`invalid audit evidence argument: ${arg}`);
    }
    paths[name] = args[index + 1];
    index += 1;
  }
  return paths;
}

export function runAudit({
  args = process.argv.slice(2),
  spawn = spawnSync,
  write = writeFileSync,
} = {}) {
  const paths = evidencePaths(args);
  const result = spawn("pnpm", ["audit", "--json"], {
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
    shell: process.platform === "win32",
  });

  if (paths.stdout) write(paths.stdout, result.stdout ?? "", "utf8");
  if (paths.stderr) write(paths.stderr, result.stderr ?? "", "utf8");
  if (paths.status) {
    write(
      paths.status,
      JSON.stringify(
        {
          exitCode: result.status ?? null,
          signal: result.signal ?? null,
          spawnError: result.error
            ? { code: result.error.code ?? null, message: result.error.message }
            : null,
        },
        null,
        2,
      ) + "\n",
      "utf8",
    );
  }

  return assessAuditProcess(result);
}

function main() {
  try {
    const { blockers } = runAudit();
    const gateStatus = gateExitCode({ blockers });
    if (gateStatus !== 0) {
      console.error("Blocking high/critical dependency advisories:");
      for (const blocker of blockers) {
        console.error(
          `- ${blocker.severity} ${blocker.id} ${blocker.module} ` +
            `(vulnerable ${blocker.vulnerableVersions}; patched ${blocker.patchedVersions})`,
        );
      }
      return gateStatus;
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
