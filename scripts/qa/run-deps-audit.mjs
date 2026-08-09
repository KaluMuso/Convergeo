#!/usr/bin/env node
/**
 * CI-equivalent dependency audit gate for release certification.
 * Applies the same allowlist as .github/workflows/ci.yml Dependency audit.
 * Does not allowlist fixable HIGH/CRITICAL advisories (nanoid etc.).
 */
import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const ALLOWLIST = new Set(
  (
    process.env.ALLOWLIST ||
    "GHSA-ph9p-34f9-6g65 GHSA-mh99-v99m-4gvg GHSA-7p8r-x3mc-p8w7 GHSA-mwp4-54f8-5fhr GHSA-rgw5-rvv9-x895"
  )
    .split(/\s+/)
    .filter(Boolean),
);

const auditPath = resolve(ROOT, "scripts/qa/evidence/.tmp-audit.json");
const result = spawnSync("pnpm", ["audit", "--audit-level=high", "--json"], {
  cwd: ROOT,
  encoding: "utf8",
  maxBuffer: 20 * 1024 * 1024,
});

writeFileSync(auditPath, result.stdout || "{}");

let data;
try {
  data = JSON.parse(readFileSync(auditPath, "utf8"));
} catch {
  console.error("failed to parse pnpm audit JSON");
  process.exit(1);
}

const blocking = [];
for (const adv of Object.values(data.advisories || {})) {
  if (adv.severity === "high" || adv.severity === "critical") {
    const ghsa = adv.github_advisory_id || "";
    if (ALLOWLIST.has(ghsa)) {
      console.log(`allowlisted ${ghsa} (${adv.module_name})`);
      continue;
    }
    blocking.push(`${adv.severity} ${ghsa} ${adv.module_name}`);
  }
}

if (blocking.length) {
  console.error("blocking high/critical advisories:");
  for (const b of blocking) console.error(`  - ${b}`);
  process.exit(1);
}

console.log("pnpm audit: no blocking high/critical advisories");
process.exit(0);
