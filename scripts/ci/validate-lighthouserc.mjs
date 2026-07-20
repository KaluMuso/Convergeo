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
  ", default LCP ≤",
  lcp,
  "ms (blocking)",
);
