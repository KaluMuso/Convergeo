/**
 * Single source of truth for which Playwright project(s) each E2E spec runs
 * on. `playwright.config.ts` (project `testMatch`), the execution-
 * completeness contract (`scripts/ci/verify-e2e-matrix.mjs`) and the matrix
 * regression self-tests (`scripts/qa/self-test/e2e-matrix.test.mjs`) all
 * import from here — there is deliberately no second definition of "which
 * spec runs where", mirroring how `fixtures/gating.ts` is the single
 * definition of "strict mode".
 *
 * Four classes (mirrors the certification matrix design):
 *  - BEHAVIORAL_ONCE: functional/business-logic assertion, independent of
 *    viewport and network profile. Runs once, on the canonical viewport.
 *  - RESPONSIVE_ALL_VIEWPORTS: the assertion itself is about layout at a
 *    given viewport (overflow, touch target, viewport-fit). Runs once per
 *    certification viewport — the OWNING Playwright project supplies
 *    viewport/isMobile/hasTouch; the spec must not re-loop over viewports
 *    itself (that is the double-multiplication bug PR B removes).
 *  - NETWORK_THROTTLED_ONLY: the assertion is only meaningful under a
 *    throttled network profile (byte budgets, LCP against the Fast-3G/360px
 *    budget in CLAUDE.md). Runs once, on the dedicated Fast-3G project.
 *  - PORTAL_SPECIFIC: the spec's entire purpose is proving Playwright
 *    reached the right portal/origin (not a Vercel SSO interstitial, not the
 *    wrong app) — a distinct rationale from BEHAVIORAL_ONCE even though it
 *    runs on the same canonical project.
 *
 * A spec that navigates a DIFFERENT origin mid-test (vendor-sell,
 * event-ticket) is still BEHAVIORAL_ONCE, not PORTAL_SPECIFIC: the
 * `portalBypass` auto-fixture in fixtures/test-base.ts already rewrites the
 * Vercel bypass header per request origin regardless of which project is
 * active, and both specs navigate via explicit absolute URLs
 * (`requireVendorBaseUrl()` / `urlOn()`) rather than relying on the active
 * project's `baseURL` — so no dedicated vendor project is needed.
 */

export type SpecClass =
  "BEHAVIORAL_ONCE" | "RESPONSIVE_ALL_VIEWPORTS" | "NETWORK_THROTTLED_ONLY" | "PORTAL_SPECIFIC";

export type SpecEntry = {
  /** Filename under e2e/specs/, e.g. "auth-otp.spec.ts". */
  file: string;
  class: SpecClass;
  /** Why this classification — read by reviewers and asserted by the self-test. */
  rationale: string;
};

/** Canonical non-throttled project every BEHAVIORAL_ONCE/PORTAL_SPECIFIC spec runs on. */
export const CANONICAL_PROJECT = "mobile-390";

/** The five release-certification viewports (from fixtures/viewports.ts CERTIFICATION_VIEWPORTS). */
export const RESPONSIVE_PROJECTS = [
  "mobile-360",
  "mobile-390",
  "mobile-430",
  "tablet-768",
  "desktop-1440",
] as const;

/**
 * Dedicated Fast-3G project — separate identity from "mobile-360" on
 * purpose. The `fast3g` auto-fixture in fixtures/test-base.ts throttles by
 * project NAME (`.includes("3g")`), so a spec that must NOT be throttled
 * (mobile-layout at 360px) cannot share a project with one that must be
 * (performance-smoke, clips-feed).
 */
export const FAST_3G_PROJECT = "fast-3g";

export const SPEC_CLASSIFICATION: readonly SpecEntry[] = [
  {
    file: "a11y-smoke.spec.ts",
    class: "BEHAVIORAL_ONCE",
    rationale: "axe scan per route; violations don't depend on viewport or network profile.",
  },
  {
    file: "auth-otp.spec.ts",
    class: "BEHAVIORAL_ONCE",
    rationale:
      "OTP request/verify flow; REQUIRED_STRICT customer OTP journey, no viewport/network assertion.",
  },
  {
    file: "browse-journey.spec.ts",
    class: "BEHAVIORAL_ONCE",
    rationale:
      "home → search → category → PDP → cart → checkout functional chain; no viewport/network assertion.",
  },
  {
    file: "checkout-false-success.spec.ts",
    class: "BEHAVIORAL_ONCE",
    rationale:
      "payment-status honesty assertions (mock fixtures); independent of viewport and network profile.",
  },
  {
    file: "clips-commerce.spec.ts",
    class: "BEHAVIORAL_ONCE",
    rationale:
      "cart/attribution correctness through the overlay; not a byte-budget or LCP assertion (contrast clips-feed).",
  },
  {
    file: "clips-feed.spec.ts",
    class: "NETWORK_THROTTLED_ONLY",
    rationale:
      'byte-budget assertions are explicitly "on Fast-3G" per the spec\'s own doc comment (S1: ≤5MB/10-clip session).',
  },
  {
    file: "critical-path.spec.ts",
    class: "BEHAVIORAL_ONCE",
    rationale:
      "REQUIRED_STRICT checkout place-order -> payment surface gate; no own viewport/network code.",
  },
  {
    file: "data-quality.spec.ts",
    class: "BEHAVIORAL_ONCE",
    rationale:
      "price/content integrity scan on browse surfaces; independent of viewport and network profile.",
  },
  {
    file: "event-ticket.spec.ts",
    class: "BEHAVIORAL_ONCE",
    rationale:
      "REQUIRED_STRICT scanner verify+duplicate-reject; navigates the vendor origin via requireVendorBaseUrl()/urlOn(), covered by the portalBypass auto-fixture on any project.",
  },
  {
    file: "mobile-layout.spec.ts",
    class: "RESPONSIVE_ALL_VIEWPORTS",
    rationale:
      "overflow/touch-target/viewport-fit assertions read page.viewportSize() at runtime — genuinely viewport-dependent, owned by the Playwright project (no internal viewport loop).",
  },
  {
    file: "performance-smoke.spec.ts",
    class: "NETWORK_THROTTLED_ONLY",
    rationale:
      "LCP/CLS/INP thresholds are defined against the Fast-3G/360px budget (CLAUDE.md performance budgets).",
  },
  {
    file: "shop-checkout-momo.spec.ts",
    class: "BEHAVIORAL_ONCE",
    rationale:
      "MoMo checkout functional chain (sandbox-gated); independent of viewport and network profile.",
  },
  {
    file: "shop-cod.spec.ts",
    class: "BEHAVIORAL_ONCE",
    rationale:
      "Cash-on-Delivery checkout functional chain; independent of viewport and network profile.",
  },
  {
    file: "staging-access-smoke.spec.ts",
    class: "PORTAL_SPECIFIC",
    rationale:
      "E2E-GATE-04 — sole purpose is proving Playwright reached the real customer app, not a Vercel SSO/404/wrong portal.",
  },
  {
    file: "ux-surfaces.spec.ts",
    class: "BEHAVIORAL_ONCE",
    rationale:
      "wishlist/compare/vendor-storefront/offline/order-history surface coverage; independent of viewport and network profile.",
  },
  {
    file: "vendor-sell.spec.ts",
    class: "BEHAVIORAL_ONCE",
    rationale:
      "REQUIRED_STRICT vendor sell flow; navigates the vendor origin via requireVendorBaseUrl()/urlOn(), covered by the portalBypass auto-fixture on any project.",
  },
] as const;

/** Which project name(s) a given class runs on. */
export function projectsForClass(specClass: SpecClass): readonly string[] {
  switch (specClass) {
    case "RESPONSIVE_ALL_VIEWPORTS":
      return RESPONSIVE_PROJECTS;
    case "NETWORK_THROTTLED_ONLY":
      return [FAST_3G_PROJECT];
    case "BEHAVIORAL_ONCE":
    case "PORTAL_SPECIFIC":
      return [CANONICAL_PROJECT];
    default: {
      const exhaustive: never = specClass;
      throw new Error(`spec-classification: unhandled class ${String(exhaustive)}`);
    }
  }
}

/** Every spec file assigned to a given Playwright project name. */
export function specsForProject(projectName: string): readonly string[] {
  return SPEC_CLASSIFICATION.filter((entry) =>
    projectsForClass(entry.class).includes(projectName),
  ).map((entry) => entry.file);
}

/** All distinct project names the classification produces, in a stable order. */
export function allProjectNames(): readonly string[] {
  return [...RESPONSIVE_PROJECTS, FAST_3G_PROJECT];
}
