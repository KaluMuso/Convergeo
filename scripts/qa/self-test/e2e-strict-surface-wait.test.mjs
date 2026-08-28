import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const SPEC_DIR = path.join(REPO_ROOT, "e2e", "specs");

function readSpec(file) {
  return readFileSync(path.join(SPEC_DIR, file), "utf8");
}

/** Strips comments so a pattern discussed in prose doesn't count as live code. */
function stripComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !line.trim().startsWith("//"))
    .join("\n");
}

/**
 * RC-5 regression coverage (E2E run #52's actual Playwright artifact, not a
 * hypothesis): three required-synthetic-surface checks raced an immediate
 * `isVisible()` read against the page still rendering, and misclassified a
 * genuinely-present PDP/vendor-storefront/cart-contents as absent —
 * confirmed because the SAME failing attempt's own DOM snapshot showed the
 * full surface. `Locator.isVisible({ timeout })` does not fix this: per
 * Playwright's own type declarations that option is `@deprecated` and
 * documented as "ignored ... does not wait for the element to become
 * visible and returns immediately."
 *
 * This does not ban `isVisible()` globally (it is still correct for the
 * honest instant-fallback read in non-strict/local exploratory mode) — it
 * only encodes the release-critical contract: in
 * strictSyntheticRequired()/strict mode, a required synthetic surface must
 * be given a genuine bounded wait (`waitFor`/`toBeVisible`) before a spec
 * concludes it is absent.
 */
describe("strict-mode required-surface checks use a genuine bounded wait", () => {
  it("browse-journey PDP check waits in strict mode, not an unconditional instant isVisible", () => {
    const source = readSpec("browse-journey.spec.ts");
    assert.match(
      source,
      /const pdpAvailable = strictSyntheticRequired\(\)\s*\n\s*\? await buyBox\s*\n\s*\.waitFor\(\{ state: "visible", timeout: \d+_?\d* \}\)/,
      "browse-journey.spec.ts must wait for the PDP buy box in strict mode instead of racing an instant isVisible()",
    );
  });

  it("browse-journey cart terminal-state check waits in strict mode, not an instant isVisible after the loading-inclusive assertion", () => {
    const source = readSpec("browse-journey.spec.ts");
    assert.match(
      source,
      /const hasItems = strictSyntheticRequired\(\)\s*\n\s*\? await page\s*\n\s*\.getByTestId\("cart-vendor-groups"\)\s*\n\s*\.waitFor\(\{ state: "visible", timeout: \d+_?\d* \}\)/,
      "browse-journey.spec.ts must wait for the cart's terminal vendor-groups state in strict mode, not sample right after an assertion that also accepts cart-loading",
    );
  });

  it("ux-surfaces vendor storefront check uses waitFor, not the deprecated isVisible({ timeout }) no-op wait", () => {
    const source = readSpec("ux-surfaces.spec.ts");
    assert.match(
      source,
      /\.waitFor\(\{ state: "visible", timeout: \d+_?\d* \}\)\s*\n\s*\.then\(\(\) => true\)\s*\n\s*\.catch\(\(\) => false\)/,
      "ux-surfaces.spec.ts must locate the vendor storefront surface via waitFor(), not isVisible({ timeout })",
    );
    assert.ok(
      !/isVisible\(\{\s*timeout/.test(stripComments(source)),
      "ux-surfaces.spec.ts must not reintroduce isVisible({ timeout }) — Playwright documents that option as " +
        "deprecated and ignored (see node_modules/playwright-core/types/types.d.ts)",
    );
  });

  it("critical-path PDP check waits in strict mode and fails closed instead of falling through to payment-mock", () => {
    const source = readSpec("critical-path.spec.ts");
    assert.match(
      source,
      /const pdpAvailable = strictSyntheticRequired\(\)\s*\n\s*\? await buyBox\s*\n\s*\.waitFor\(\{ state: "visible", timeout: \d+_?\d* \}\)/,
      "critical-path.spec.ts must wait for the PDP buy box in strict mode instead of racing an instant isVisible()",
    );
    assert.match(
      source,
      /if \(!pdpAvailable\) \{\s*\n\s*if \(strictSyntheticRequired\(\)\) \{\s*\n\s*throw new Error\(/,
      "critical-path.spec.ts must throw in strict mode when the PDP is genuinely unavailable, not silently " +
        "continue into the payment-mock confirmation branch (the exact E2E run #52 false-pass loophole)",
    );
  });

  it("critical-path.spec.ts imports strictSyntheticRequired", () => {
    const source = readSpec("critical-path.spec.ts");
    assert.match(source, /strictSyntheticRequired/);
    assert.match(source, /from "\.\.\/fixtures\/env"/);
  });

  it("isVisible() itself is not banned — non-strict fallback reads still use it", () => {
    for (const file of ["browse-journey.spec.ts", "critical-path.spec.ts"]) {
      const source = readSpec(file);
      assert.ok(
        /: await buyBox\.isVisible\(\)\.catch\(\(\) => false\)/.test(source),
        `${file} must keep the instant isVisible() read for the non-strict/local exploratory branch`,
      );
    }
  });
});
