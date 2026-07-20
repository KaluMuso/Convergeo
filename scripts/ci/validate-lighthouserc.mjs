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

for (const row of matrix) {
  for (const [key, spec] of Object.entries(row.assertions || {})) {
    if (!Array.isArray(spec) || spec[0] === "off") continue;
    // Checkout SEO may stay warn (noindex waiver); everything else must error.
    const isCheckoutSeo = /checkout/.test(row.matchingUrlPattern || "") && key === "categories:seo";
    if (!isCheckoutSeo && spec[0] !== "error") {
      throw new Error(
        `assertion ${key} on ${row.matchingUrlPattern} must be error (got ${spec[0]})`,
      );
    }
  }
}

const lcp = matrix[matrix.length - 1].assertions["largest-contentful-paint"]?.[1]?.maxNumericValue;
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
