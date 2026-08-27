import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

import { BOTTOM_NAV_ARIA_LABEL } from "../../../e2e/fixtures/nav-contract.ts";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

/**
 * RC-1 regression coverage (staging E2E run #52): mobile-layout.spec.ts's
 * bottom-nav check used to locate the nav via a data-testid production never
 * renders and an `a[href*='/cart']` filter the real 5-item nav can never
 * satisfy — a TEST_BUG that failed on every mobile viewport regardless of
 * runtime state. The fix locates it by its real accessible-name contract
 * instead; this proves that contract stays in sync with the copy the app
 * actually ships, so a translation-copy edit that drifts fails CI instead of
 * silently breaking the E2E locator the next time it runs.
 */
describe("bottom-nav locator contract", () => {
  it("BOTTOM_NAV_ARIA_LABEL matches the live English nav.json source", () => {
    const navMessagesPath = path.join(REPO_ROOT, "packages/i18n/messages/en/nav.json");
    const messages = JSON.parse(readFileSync(navMessagesPath, "utf8"));
    assert.equal(
      BOTTOM_NAV_ARIA_LABEL,
      messages.shop?.bottomAriaLabel,
      "e2e/fixtures/nav-contract.ts has drifted from packages/i18n/messages/en/nav.json's " +
        "shop.bottomAriaLabel — the bottom-nav E2E locator would stop matching the real app",
    );
  });

  it("is distinct from the other two nav aria-labels (no accidental cross-match)", () => {
    const navMessagesPath = path.join(REPO_ROOT, "packages/i18n/messages/en/nav.json");
    const messages = JSON.parse(readFileSync(navMessagesPath, "utf8"));
    assert.notEqual(BOTTOM_NAV_ARIA_LABEL, messages.ariaLabel);
    assert.notEqual(BOTTOM_NAV_ARIA_LABEL, messages.shop?.desktopAriaLabel);
  });

  it("mobile-layout.spec.ts locates the bottom nav by role + accessible name, not a testid", () => {
    const specPath = path.join(REPO_ROOT, "e2e/specs/mobile-layout.spec.ts");
    const source = readFileSync(specPath, "utf8");
    assert.ok(
      source.includes('page.getByRole("navigation", { name: BOTTOM_NAV_ARIA_LABEL'),
      "mobile-layout.spec.ts must locate the bottom nav via role=navigation + accessible name",
    );
    assert.ok(
      !source.includes('getByTestId("bottom-nav")'),
      "mobile-layout.spec.ts must not reintroduce the data-testid production never renders",
    );
    assert.ok(
      !/a\[href\*=.\/cart.\]/.test(source),
      "mobile-layout.spec.ts must not reintroduce the /cart-href filter the real nav can never satisfy",
    );
  });

  it("still runs on 360/390/430/768 and only skips at >=1024 (tablet-768 not lost)", () => {
    const specPath = path.join(REPO_ROOT, "e2e/specs/mobile-layout.spec.ts");
    const source = readFileSync(specPath, "utf8");
    assert.match(source, /\(viewport\?\.width \?\? 0\) >= 1024/);
    assert.match(source, /kind: "VIEWPORT_NOT_APPLICABLE"/);
  });
});
