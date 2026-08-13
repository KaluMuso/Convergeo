#!/usr/bin/env node
/**
 * check-release-control-contract.mjs — static RELCTRL-01 governance guard.
 *
 * Fails CI when docs/workflows regress to master-as-Production or omit required
 * release-control artifacts.
 */
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const REPO_ROOT = new URL("../..", import.meta.url).pathname;

const REQUIRED_FILES = [
  "docs/ops/production-release-control.md",
  ".github/workflows/promote-production-frontends.yml",
  ".github/workflows/capture-production-db-evidence.yml",
  "infra/release-evidence-contract.example.json",
  "scripts/ci/validate_release_parity.py",
  "scripts/ci/validate_production_db_evidence.py",
  "scripts/ci/capture_production_db_evidence.py",
  "scripts/ci/vercel-wait-production.sh",
];

const FORBIDDEN_PATTERNS = [
  {
    file: "infra/vercel.md",
    pattern: /Production Branch[`'"]?\s*[:|]\s*[`'"]?master[`'"]?/i,
    message: "infra/vercel.md must not document master as Vercel Production Branch",
  },
  {
    file: "docs/ops/production-release-control.md",
    pattern: /master\s+(is|as)\s+the\s+production\s+branch/i,
    message: "runbook must not claim master is the production branch",
  },
];

const REQUIRED_SNIPPETS = [
  {
    file: "docs/ops/production-release-control.md",
    includes: ["Production Branch", "`production`", "fail-closed"],
  },
  {
    file: ".github/workflows/promote-production-frontends.yml",
    includes: [
      "workflow_dispatch",
      "candidate_sha",
      "validate_release_parity.py",
      "validate_production_db_evidence.py",
      "I_ACCEPT_DEGRADED_PRODUCTION_EVIDENCE",
      "environment: production",
    ],
  },
  {
    file: "infra/vercel.md",
    includes: ["Production Branch", "`production`"],
  },
];

function read(rel) {
  const path = join(REPO_ROOT, rel);
  if (!existsSync(path)) {
    throw new Error(`missing required file: ${rel}`);
  }
  return readFileSync(path, "utf8");
}

function main() {
  const errors = [];

  for (const rel of REQUIRED_FILES) {
    if (!existsSync(join(REPO_ROOT, rel))) {
      errors.push(`missing required file: ${rel}`);
    }
  }

  for (const { file, pattern, message } of FORBIDDEN_PATTERNS) {
    const text = read(file);
    if (pattern.test(text)) {
      errors.push(message);
    }
  }

  for (const { file, includes } of REQUIRED_SNIPPETS) {
    const text = read(file);
    for (const snippet of includes) {
      if (!text.includes(snippet)) {
        errors.push(`${file} must include: ${snippet}`);
      }
    }
  }

  // deploy-production.yml must remain workflow_dispatch-only (not push to master).
  const deployProd = read(".github/workflows/deploy-production.yml");
  if (/^\s*push:/m.test(deployProd) && /branches:\s*\n\s*-\s*master/m.test(deployProd)) {
    errors.push("deploy-production.yml must not auto-run on master push");
  }

  // promote workflow must not run on push.
  const promote = read(".github/workflows/promote-production-frontends.yml");
  if (/^\s*push:/m.test(promote)) {
    errors.push("promote-production-frontends.yml must be workflow_dispatch only");
  }

  if (errors.length) {
    for (const err of errors) {
      console.error(`FAIL: ${err}`);
    }
    process.exit(1);
  }

  console.log("PASS: release-control contract static checks");
}

main();
