#!/usr/bin/env node
/**
 * Validate lighthouserc.json blocking policy (G19 / VE-P06 / RC-06).
 * Kept as a file (not inline YAML) so `//` comments cannot comment-out the
 * rest of a one-line `node -e` invocation on GitHub Actions.
 */
import { readFileSync } from "node:fs";

const cfg = JSON.parse(readFileSync("lighthouserc.json", "utf8"));
if (!cfg.ci?.collect?.url?.length) throw new Error("missing ci.collect.url");
if (!cfg.vergeo?.bundle?.defaultMaxKbGz) throw new Error("missing vergeo.bundle");

const numberOfRuns = cfg.ci.collect?.numberOfRuns ?? 3;
if (numberOfRuns < 3) {
  throw new Error(
    `ci.collect.numberOfRuns must be >= 3 (got ${numberOfRuns}) — single-run LHCI flakes at the perf≥0.50 floor`,
  );
}

const matrix = cfg.ci.assert?.assertMatrix;
if (!Array.isArray(matrix) || !matrix.length) {
  throw new Error("missing ci.assert.assertMatrix (blocking G19 policy)");
}

/** URL patterns allowed to keep SEO at warn (documented noindex / SERP waivers). */
function isSeoWarnAllowed(pattern) {
  return /checkout/.test(pattern || "");
}

for (const row of matrix) {
  const pattern = row.matchingUrlPattern || "";
  for (const [key, spec] of Object.entries(row.assertions || {})) {
    if (!Array.isArray(spec) || spec[0] === "off") continue;
    const isCheckoutSeoWarn =
      key === "categories:seo" && isSeoWarnAllowed(pattern) && spec[0] === "warn";
    if (isCheckoutSeoWarn) continue;
    if (spec[0] !== "error") {
      throw new Error(`assertion ${key} on ${pattern} must be error (got ${spec[0]})`);
    }
    if (key === "categories:performance" || key === "largest-contentful-paint") {
      const options = spec[1] || {};
      if (options.aggregationMethod !== "median") {
        throw new Error(
          `assertion ${key} on ${pattern} must use aggregationMethod=median (got ${options.aggregationMethod ?? "default"})`,
        );
      }
    }
  }
}

const defaultRow = matrix[matrix.length - 1];
const lcp = defaultRow.assertions["largest-contentful-paint"]?.[1]?.maxNumericValue;
console.log(
  "lighthouserc.json OK —",
  cfg.ci.collect.url.length,
  "URLs,",
  "assertMatrix rows",
  matrix.length,
  ", runs",
  numberOfRuns,
  "(median perf/LCP), default LCP ≤",
  lcp,
  "ms (blocking)",
);
