#!/usr/bin/env node
/**
 * Evidence namespace helpers — every certification run writes into an isolated
 * directory containing exact Git SHA, environment, and run ID/timestamp.
 * Collectors must refuse to load gate fragments from sibling/parent namespaces.
 */
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync } from "node:fs";
import { join, resolve, sep } from "node:path";

/**
 * @param {{ root: string, sha: string, environment: string, runId: string }} opts
 * @returns {string}
 */
export function evidenceNamespacePath(opts) {
  const sha = sanitizeSegment(opts.sha || "unknown", "unknown");
  const environment = sanitizeSegment(opts.environment || "local", "local");
  const runId = sanitizeSegment(opts.runId || "run", "run");
  return resolve(opts.root, sha, environment, runId);
}

/**
 * @param {string} value
 * @param {string} fallback
 */
function sanitizeSegment(value, fallback) {
  const cleaned = String(value)
    .replace(/[^a-zA-Z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 120);
  return cleaned || fallback;
}

/**
 * Create a clean evidence namespace. Removes any pre-existing gate-*.json in
 * that exact namespace so prior fragments cannot contaminate the run.
 *
 * @param {string} nsPath
 * @returns {string}
 */
export function prepareEvidenceNamespace(nsPath) {
  mkdirSync(nsPath, { recursive: true });
  for (const file of readdirSync(nsPath)) {
    if (file.startsWith("gate-") && file.endsWith(".json")) {
      rmSync(join(nsPath, file), { force: true });
    }
  }
  return nsPath;
}

/**
 * Load gate fragments only from the exact namespace directory.
 * Refuses to walk parents. Ignores non-gate JSON (certificates, etc.).
 * Fragments whose embedded sha/environment/run_id disagree with the expected
 * identity are rejected (stale contamination defense).
 *
 * @param {string} nsPath
 * @param {{ expectedSha?: string, expectedEnvironment?: string, expectedRunId?: string }} [identity]
 * @returns {{ gates: Record<string, any>, rejected: Array<{ file: string, reason: string }> }}
 */
export function loadIsolatedGateFragments(nsPath, identity = {}) {
  /** @type {Record<string, any>} */
  const gates = {};
  /** @type {Array<{ file: string, reason: string }>} */
  const rejected = [];

  if (!existsSync(nsPath) || !statSync(nsPath).isDirectory()) {
    return { gates, rejected };
  }

  const resolvedNs = resolve(nsPath);

  for (const file of readdirSync(resolvedNs)) {
    if (!file.startsWith("gate-") || !file.endsWith(".json")) continue;
    const full = join(resolvedNs, file);
    if (!(full.startsWith(resolvedNs + sep) || full === resolvedNs)) {
      rejected.push({ file, reason: "path-escape" });
      continue;
    }
    try {
      const raw = JSON.parse(readFileSync(full, "utf8"));
      if (identity.expectedSha && raw.sha && raw.sha !== identity.expectedSha) {
        rejected.push({ file, reason: `sha-mismatch:${raw.sha}` });
        continue;
      }
      if (
        identity.expectedEnvironment &&
        raw.environment &&
        raw.environment !== identity.expectedEnvironment
      ) {
        rejected.push({ file, reason: `env-mismatch:${raw.environment}` });
        continue;
      }
      if (identity.expectedRunId && raw.run_id && raw.run_id !== identity.expectedRunId) {
        rejected.push({ file, reason: `run-mismatch:${raw.run_id}` });
        continue;
      }
      const id = raw.id ?? file.replace(/^gate-|\.json$/g, "");
      gates[id] = { ...raw, id };
    } catch {
      rejected.push({ file, reason: "malformed" });
      const id = file.replace(/^gate-|\.json$/g, "");
      gates[id] = {
        id,
        layer: "unknown",
        status: "UNKNOWN",
        detail: "malformed fragment",
      };
    }
  }

  return { gates, rejected };
}
