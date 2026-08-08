#!/usr/bin/env node
/**
 * Aggregates per-gate JSON fragments into a machine-readable release certificate
 * plus a human-readable Markdown summary.
 *
 * Usage:
 *   node scripts/qa/collect-certificate.mjs \
 *     --evidence-dir scripts/qa/evidence \
 *     --sha $(git rev-parse HEAD) \
 *     --environment local
 */
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { deriveCertification, normalizeStatus } from "./gate-status.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "../..");

function parseArgs(argv) {
  const args = {
    evidenceDir: join(ROOT, "scripts/qa/evidence"),
    sha: "unknown",
    environment: "local",
    branch: "unknown",
    timestamp: new Date().toISOString(),
  };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--evidence-dir" && argv[i + 1]) args.evidenceDir = resolve(argv[++i]);
    else if (a === "--sha" && argv[i + 1]) args.sha = argv[++i];
    else if (a === "--environment" && argv[i + 1]) args.environment = argv[++i];
    else if (a === "--branch" && argv[i + 1]) args.branch = argv[++i];
    else if (a === "--timestamp" && argv[i + 1]) args.timestamp = argv[++i];
  }
  return args;
}

/**
 * @param {string} dir
 * @returns {Record<string, { id: string, layer: string, status: string, detail?: string, duration_ms?: number }>}
 */
function loadGateFragments(dir) {
  /** @type {Record<string, any>} */
  const gates = {};
  if (!existsSync(dir)) return gates;
  for (const file of readdirSync(dir).filter((f) => f.endsWith(".json") && f.startsWith("gate-"))) {
    try {
      const raw = JSON.parse(readFileSync(join(dir, file), "utf8"));
      const id = raw.id ?? file.replace(/^gate-|\.json$/g, "");
      gates[id] = {
        ...raw,
        id,
        status: normalizeStatus(raw.status),
      };
    } catch {
      gates[file] = { id: file, layer: "unknown", status: "UNKNOWN", detail: "malformed fragment" };
    }
  }
  return gates;
}

/**
 * @param {Record<string, any>} gates
 */
function buildCertificate(args, gates) {
  const normalized = {};
  for (const [id, g] of Object.entries(gates)) {
    normalized[id] = { ...g, status: normalizeStatus(g.status) };
  }

  const sections = {
    identity: {
      sha: args.sha,
      branch: args.branch,
      environment: args.environment,
      generated_at: args.timestamp,
    },
    security: pickGates(normalized, /^(rls|secret|authz|deps|headers)/i),
    database: pickGates(normalized, /^(migration|db|typegen)/i),
    static: pickGates(normalized, /^(lint|typecheck|unit|i18n)/i),
    integration: pickGates(normalized, /^(int-|api-|cart|checkout|rfq|returns|order|review)/i),
    ux: pickGates(normalized, /^(e2e-|browse|mobile|ux-)/i),
    a11y: pickGates(normalized, /^(a11y|axe)/i),
    performance: pickGates(normalized, /^(perf|bundle|lighthouse|lcp)/i),
    data_quality: pickGates(normalized, /^(data-|dq-)/i),
    payments: pickGates(normalized, /^(payment|lenco|sandbox|money)/i),
    recovery: pickGates(normalized, /^(backup|restore|drill)/i),
  };

  const certification = deriveCertification(normalized);

  return {
    schema_version: 1,
    certification,
    identity: sections.identity,
    gates: normalized,
    sections,
    summary: {
      total: Object.keys(normalized).length,
      pass: countStatus(normalized, "PASS"),
      fail: countStatus(normalized, "FAIL"),
      blocked_external: countStatus(normalized, "BLOCKED_EXTERNAL"),
      not_run: countStatus(normalized, "NOT_RUN"),
      unknown: countStatus(normalized, "UNKNOWN"),
      measurement_unstable: countStatus(normalized, "MEASUREMENT_UNSTABLE"),
    },
  };
}

/**
 * @param {Record<string, { status: string }>} gates
 * @param {RegExp} pattern
 */
function pickGates(gates, pattern) {
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
  const lines = [
    "# Vergeo5 Release Certificate",
    "",
    `| Field | Value |`,
    `| --- | --- |`,
    `| SHA | \`${cert.identity.sha}\` |`,
    `| Branch | \`${cert.identity.branch}\` |`,
    `| Environment | ${cert.identity.environment} |`,
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
    "## Gate matrix",
    "",
    "| Gate | Layer | Status | Detail |",
    "| --- | --- | --- | --- |",
  ];

  for (const g of Object.values(cert.gates).sort((a, b) => a.id.localeCompare(b.id))) {
    const detail = (g.detail ?? "").replace(/\|/g, "\\|").slice(0, 120);
    lines.push(`| ${g.id} | ${g.layer ?? "—"} | ${g.status} | ${detail} |`);
  }

  lines.push("", "## Section rollup", "");
  for (const [section, gates] of Object.entries(cert.sections)) {
    if (section === "identity" || Object.keys(gates).length === 0) continue;
    const statuses = Object.values(gates).map((g) => g.status);
    const rollup = statuses.includes("FAIL")
      ? "FAIL"
      : statuses.every((s) => s === "PASS")
        ? "PASS"
        : statuses.some((s) => s === "BLOCKED_EXTERNAL")
          ? "BLOCKED_EXTERNAL"
          : "MIXED";
    lines.push(`- **${section}**: ${rollup} (${Object.keys(gates).length} gates)`);
  }

  lines.push(
    "",
    "---",
    "_No false green: BLOCKED_EXTERNAL, NOT_RUN, UNKNOWN, and MEASUREMENT_UNSTABLE are never translated to PASS._",
  );
  return lines.join("\n");
}

function main() {
  const args = parseArgs(process.argv);
  mkdirSync(args.evidenceDir, { recursive: true });

  const gates = loadGateFragments(args.evidenceDir);
  const cert = buildCertificate(args, gates);

  const jsonPath = join(args.evidenceDir, "release-certificate.json");
  const mdPath = join(args.evidenceDir, "release-certificate.md");

  writeFileSync(jsonPath, JSON.stringify(cert, null, 2));
  writeFileSync(mdPath, toMarkdown(cert));

  console.log(`Certificate: ${cert.certification}`);
  console.log(`  JSON: ${jsonPath}`);
  console.log(`  MD:   ${mdPath}`);
  console.log(
    `  Gates: ${cert.summary.pass} PASS / ${cert.summary.fail} FAIL / ${cert.summary.blocked_external} BLOCKED_EXTERNAL / ${cert.summary.not_run} NOT_RUN`,
  );

  process.exit(cert.certification === "BASELINE_FAILING" ? 1 : 0);
}

main();
