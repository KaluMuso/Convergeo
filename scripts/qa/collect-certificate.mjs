#!/usr/bin/env node
/**
 * Aggregates per-gate JSON fragments into a machine-readable certificate
 * plus a human-readable Markdown summary.
 *
 * Strict promotion modes exit non-zero unless verdict is
 * PASS. local-development emits LOCAL_DEVELOPMENT_REPORT and must never be
 * titled as a release certificate.
 *
 * Usage:
 *   node scripts/qa/collect-certificate.mjs \
 *     --evidence-dir scripts/qa/evidence/<sha>/<env>/<runId> \
 *     --sha <git-sha> \
 *     --mode integrated-staging \
 *     --environment staging \
 *     --run-id <id>
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { loadIsolatedGateFragments } from "./evidence-ns.mjs";
import {
  deriveCertification,
  exitCodeForVerdict,
  normalizeMode,
  normalizeStatus,
  requiredGateBlocks,
} from "./gate-status.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "../..");

function parseArgs(argv) {
  const args = {
    evidenceDir: "",
    sha: "unknown",
    environment: "local",
    branch: "unknown",
    mode: "local-development",
    runId: "unknown",
    timestamp: new Date().toISOString(),
    requiredGatesPath: join(__dirname, "required-gates.json"),
  };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--evidence-dir" && argv[i + 1]) args.evidenceDir = resolve(argv[++i]);
    else if (a === "--sha" && argv[i + 1]) args.sha = argv[++i];
    else if (a === "--environment" && argv[i + 1]) args.environment = argv[++i];
    else if (a === "--branch" && argv[i + 1]) args.branch = argv[++i];
    else if (a === "--mode" && argv[i + 1]) args.mode = argv[++i];
    else if (a === "--run-id" && argv[i + 1]) args.runId = argv[++i];
    else if (a === "--timestamp" && argv[i + 1]) args.timestamp = argv[++i];
    else if (a === "--required-gates" && argv[i + 1]) args.requiredGatesPath = resolve(argv[++i]);
  }
  if (!args.evidenceDir) {
    args.evidenceDir = join(ROOT, "scripts/qa/evidence", args.sha, args.environment, args.runId);
  }
  args.mode = normalizeMode(args.mode);
  return args;
}

/**
 * @param {string} path
 * @param {string} mode
 */
function loadRequiredGateIds(path, mode) {
  if (!existsSync(path)) return [];
  const doc = JSON.parse(readFileSync(path, "utf8"));
  const entry = doc?.modes?.[mode];
  if (!entry) return [];
  return Array.isArray(entry.required_gates) ? entry.required_gates : [];
}

/**
 * @param {string} path
 * @param {string} mode
 */
function loadModeMeta(path, mode) {
  if (!existsSync(path)) {
    return { report_only: mode === "local-development", certificate_title: "Vergeo5 Certificate" };
  }
  const doc = JSON.parse(readFileSync(path, "utf8"));
  return (
    doc?.modes?.[mode] ?? {
      report_only: mode === "local-development",
      certificate_title: "Vergeo5 Certificate",
    }
  );
}

/**
 * @param {Record<string, any>} gates
 * @param {string[]} requiredIds
 */
function annotateRequired(gates, requiredIds) {
  /** @type {Record<string, any>} */
  const out = { ...gates };
  for (const id of requiredIds) {
    if (!out[id]) {
      out[id] = {
        id,
        layer: "required-manifest",
        status: "NOT_RUN",
        detail: "required gate missing from evidence namespace",
        required: true,
      };
    } else {
      out[id] = { ...out[id], required: true };
    }
  }
  return out;
}

/**
 * @param {ReturnType<typeof parseArgs>} args
 * @param {Record<string, any>} gates
 * @param {string[]} requiredIds
 * @param {Array<{ file: string, reason: string }>} rejected
 * @param {any} modeMeta
 */
function buildCertificate(args, gates, requiredIds, rejected, modeMeta) {
  /** @type {Record<string, any>} */
  const normalized = {};
  for (const [id, g] of Object.entries(gates)) {
    normalized[id] = { ...g, status: normalizeStatus(g.status) };
  }

  const withRequired = annotateRequired(normalized, requiredIds);

  // Malformed required fragments already surface as UNKNOWN via loader.
  for (const id of requiredIds) {
    if (withRequired[id] && requiredGateBlocks(withRequired[id].status)) {
      // keep status as-is; deriveCertification handles it
    }
  }

  const certification = deriveCertification(withRequired, {
    mode: args.mode,
    requiredGateIds: requiredIds,
  });

  const sections = {
    identity: {
      sha: args.sha,
      branch: args.branch,
      environment: args.environment,
      mode: args.mode,
      run_id: args.runId,
      generated_at: args.timestamp,
      report_only: Boolean(modeMeta.report_only),
      certificate_title: modeMeta.certificate_title,
    },
    security: pickGates(withRequired, /^(rls|secret|authz|deps|headers)/i),
    database: pickGates(withRequired, /^(migration|db|typegen)/i),
    static: pickGates(withRequired, /^(lint|typecheck|unit|i18n)/i),
    integration: pickGates(withRequired, /^(int-|api-|cart|checkout|rfq|returns|order|review)/i),
    ux: pickGates(withRequired, /^(e2e-|browse|mobile|ux-)/i),
    a11y: pickGates(withRequired, /^(a11y|axe)/i),
    performance: pickGates(withRequired, /^(perf|bundle|lighthouse|lcp)/i),
    data_quality: pickGates(withRequired, /^(data-|dq-)/i),
    payments: pickGates(withRequired, /^(payment|lenco|sandbox|money)/i),
    recovery: pickGates(withRequired, /^(backup|restore|drill)/i),
    deploy: pickGates(withRequired, /^(deploy|identity|fingerprint)/i),
  };

  return {
    schema_version: 2,
    certification,
    identity: sections.identity,
    required_gates: requiredIds,
    rejected_fragments: rejected,
    gates: withRequired,
    sections,
    summary: {
      total: Object.keys(withRequired).length,
      pass: countStatus(withRequired, "PASS"),
      fail: countStatus(withRequired, "FAIL"),
      blocked_external: countStatus(withRequired, "BLOCKED_EXTERNAL"),
      not_run: countStatus(withRequired, "NOT_RUN"),
      unknown: countStatus(withRequired, "UNKNOWN"),
      measurement_unstable: countStatus(withRequired, "MEASUREMENT_UNSTABLE"),
      rejected: rejected.length,
    },
  };
}

/**
 * @param {Record<string, { status: string }>} gates
 * @param {RegExp} pattern
 */
function pickGates(gates, pattern) {
  /** @type {Record<string, any>} */
  const out = {};
  for (const [id, g] of Object.entries(gates)) {
    if (pattern.test(id)) out[id] = g;
  }
  return out;
}

/**
 * @param {Record<string, { status: string }>} gates
 * @param {string} status
 */
function countStatus(gates, status) {
  return Object.values(gates).filter((g) => g.status === status).length;
}

/**
 * @param {ReturnType<typeof buildCertificate>} cert
 */
function toMarkdown(cert) {
  const title = cert.identity.certificate_title || "Vergeo5 Certificate";
  const reportOnlyNote = cert.identity.report_only
    ? "_This is a **local development report**, not a release certificate._"
    : "_Promotion certificate: only `PASS` is green._";

  const lines = [
    `# ${title}`,
    "",
    reportOnlyNote,
    "",
    `| Field | Value |`,
    `| --- | --- |`,
    `| SHA | \`${cert.identity.sha}\` |`,
    `| Branch | \`${cert.identity.branch}\` |`,
    `| Environment | ${cert.identity.environment} |`,
    `| Mode | ${cert.identity.mode} |`,
    `| Run ID | \`${cert.identity.run_id}\` |`,
    `| Generated | ${cert.identity.generated_at} |`,
    `| **Overall** | **${cert.certification}** |`,
    "",
    "## Summary",
    "",
    `| Status | Count |`,
    `| --- | ---: |`,
    ...Object.entries(cert.summary)
      .filter(([k]) => k !== "total")
      .map(([k, v]) => `| ${k.replace(/_/g, " ")} | ${v} |`),
    "",
    "## Required gates",
    "",
    "| Gate | Status | Detail |",
    "| --- | --- | --- |",
  ];

  for (const id of cert.required_gates) {
    const g = cert.gates[id] || { status: "NOT_RUN", detail: "missing" };
    const detail = String(g.detail ?? "")
      .replace(/\|/g, "\\|")
      .slice(0, 120);
    lines.push(`| ${id} | ${g.status} | ${detail} |`);
  }

  lines.push(
    "",
    "## Full gate matrix",
    "",
    "| Gate | Layer | Status | Detail |",
    "| --- | --- | --- | --- |",
  );

  for (const g of Object.values(cert.gates).sort((a, b) => a.id.localeCompare(b.id))) {
    const detail = String(g.detail ?? "")
      .replace(/\|/g, "\\|")
      .slice(0, 120);
    lines.push(`| ${g.id} | ${g.layer ?? "—"} | ${g.status} | ${detail} |`);
  }

  if (cert.rejected_fragments.length > 0) {
    lines.push("", "## Rejected fragments (stale/malformed isolation)", "");
    for (const r of cert.rejected_fragments) {
      lines.push(`- \`${r.file}\`: ${r.reason}`);
    }
  }

  lines.push(
    "",
    "---",
    "_No false green: BLOCKED_EXTERNAL, NOT_RUN, UNKNOWN, MEASUREMENT_UNSTABLE, and missing required gates are never translated to PASS._",
  );
  return lines.join("\n");
}

export function collectCertificateFromArgs(argv = process.argv) {
  const args = parseArgs(argv);
  mkdirSync(args.evidenceDir, { recursive: true });

  const requiredIds = loadRequiredGateIds(args.requiredGatesPath, args.mode);
  const modeMeta = loadModeMeta(args.requiredGatesPath, args.mode);

  const { gates, rejected } = loadIsolatedGateFragments(args.evidenceDir, {
    expectedSha: args.sha !== "unknown" ? args.sha : undefined,
    expectedEnvironment: args.environment,
    expectedRunId: args.runId !== "unknown" ? args.runId : undefined,
  });

  const cert = buildCertificate(args, gates, requiredIds, rejected, modeMeta);

  const jsonPath = join(args.evidenceDir, "release-certificate.json");
  const mdPath = join(args.evidenceDir, "release-certificate.md");

  writeFileSync(jsonPath, JSON.stringify(cert, null, 2));
  writeFileSync(mdPath, toMarkdown(cert));

  const code = exitCodeForVerdict(cert.certification, args.mode);

  return { cert, jsonPath, mdPath, exitCode: code, args };
}

function main() {
  const { cert, jsonPath, mdPath, exitCode } = collectCertificateFromArgs(process.argv);

  console.log(`Certificate: ${cert.certification}`);
  console.log(`  Mode: ${cert.identity.mode}${cert.identity.report_only ? " (report-only)" : ""}`);
  console.log(`  JSON: ${jsonPath}`);
  console.log(`  MD:   ${mdPath}`);
  console.log(
    `  Gates: ${cert.summary.pass} PASS / ${cert.summary.fail} FAIL / ${cert.summary.blocked_external} BLOCKED_EXTERNAL / ${cert.summary.not_run} NOT_RUN / rejected ${cert.summary.rejected}`,
  );
  console.log(`  Exit: ${exitCode}`);

  process.exit(exitCode);
}

const isMain = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (isMain) {
  main();
}
