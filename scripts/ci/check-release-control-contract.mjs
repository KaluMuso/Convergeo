#!/usr/bin/env node
/**
 * check-release-control-contract.mjs — static RELCTRL-01 governance guard.
 *
 * Fails CI when docs/workflows regress to a separate production release branch
 * or omit required release-control artifacts.
 */
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const REPO_ROOT = new URL("../..", import.meta.url).pathname;

const REQUIRED_FILES = [
  "docs/ops/production-release-control.md",
  ".github/workflows/promote-production-frontends.yml",
  ".github/workflows/capture-production-db-evidence.yml",
  "infra/release-evidence-contract.example.json",
  "infra/merge-release-evidence.example.json",
  "infra/staging-certification-evidence.example.json",
  "scripts/ci/validate_release_parity.py",
  "scripts/ci/validate_production_db_evidence.py",
  "scripts/ci/validate_merge_release_evidence.py",
  "scripts/ci/staging_deploy_provenance.py",
  "scripts/ci/verify_staging_certification_gate.py",
  "scripts/ci/emit_staging_certification_evidence.py",
  "scripts/ci/staging_certification_evidence.py",
  "scripts/ci/github_actions_provenance.py",
  "scripts/ci/detect_merge_evidence_scope.py",
  "scripts/ci/capture_production_db_evidence.py",
  "scripts/ci/vercel-wait-production.sh",
];

const FORBIDDEN_PATTERNS = [
  {
    file: ".github/workflows/ci.yml",
    pattern: /bind-merge-release-evidence\.py/,
    message: "ci.yml merge gate must not invoke bind-merge-release-evidence.py (RELCTRL-02)",
  },
  {
    file: ".github/workflows/ci.yml",
    pattern: /infra\/merge-release-evidence\.json/,
    message:
      "ci.yml merge gate must not require checked-in infra/merge-release-evidence.json (RELCTRL-03)",
  },
  {
    file: ".github/workflows/promote-production-frontends.yml",
    pattern: /git push|refs\/heads\/production|fast-forward production/i,
    message: "promote-production-frontends.yml must not move Git refs (master is Production)",
  },
  {
    file: "docs/ops/production-release-control.md",
    pattern: /Production Branch[`'"]?\s*\|\s*[`'"]?production[`'"]? \(not `master`\)/i,
    message: "runbook must not require a separate production Vercel branch",
  },
  {
    file: "infra/vercel.md",
    pattern: /Production Branch[`'"]?\s*\|\s*[`'"]?production[`'"]?/i,
    message: "infra/vercel.md must document master as Vercel Production Branch",
  },
];

const REQUIRED_SNIPPETS = [
  {
    file: "docs/ops/production-release-control.md",
    includes: ["Production Branch", "`master`", "fail-closed", "deprecated"],
  },
  {
    file: ".github/workflows/promote-production-frontends.yml",
    includes: [
      "workflow_dispatch",
      "candidate_sha",
      "validate_release_parity.py",
      "validate_production_db_evidence.py",
      "must equal master tip",
      "environment: production",
    ],
  },
  {
    file: "infra/vercel.md",
    includes: ["Production Branch", "`master`"],
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

  const deployProd = read(".github/workflows/deploy-production.yml");
  if (/^\s*push:/m.test(deployProd) && /branches:\s*\n\s*-\s*master/m.test(deployProd)) {
    errors.push("deploy-production.yml must not auto-run on master push");
  }

  const promote = read(".github/workflows/promote-production-frontends.yml");
  if (/^\s*push:/m.test(promote)) {
    errors.push("promote-production-frontends.yml must be workflow_dispatch only");
  }
  if (promote.includes("contents: write")) {
    errors.push("promote-production-frontends.yml must be read-only (contents: read)");
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
