/**
 * Pure worker-count policy — deliberately dependency-free at runtime.
 *
 * Kept free of value imports for the same reason as `gating-policy.ts`: so it
 * can be unit-tested directly by Node (`--test`, type stripping) in ordinary
 * CI, without Playwright, a browser or the E2E workflow. `playwright.config.ts`
 * is the thin wrapper that supplies the certification mode from the existing
 * `certificationMode()` helper in `fixtures/env.ts` — there is no second
 * parser for `CERTIFICATION_MODE` here.
 *
 * ── Why a policy at all ─────────────────────────────────────────────────────
 * The real checkout specs (shop-cod, shop-checkout-momo) drive the deployed
 * wizard as ONE synthetic Customer — `SEED.personas.customer`. The API
 * resolves that buyer's cart by owner, not by session:
 *
 *   .eq("user_id", user_id).eq("status", "active").limit(1)
 *
 * so every spec running as that persona shares a single active cart row, and
 * `POST /checkout/session` reserves stock against it. With `fullyParallel:
 * true` and two CI workers, one spec's add-to-cart, reservation or placement
 * can land inside another's checkout — a certification failure that is a
 * property of the harness, not of the product, and one that reproduces
 * non-deterministically.
 *
 * The remedy is scheduling: a strict certification run serialises to a single
 * worker. Ordinary CI keeps two; local development keeps Playwright's own
 * default. No new identity, no relaxed assertion, no added timeout.
 *
 * `fullyParallel` is deliberately left ON. It governs whether tests WITHIN a
 * file may run in parallel; with one worker nothing runs concurrently anyway,
 * and switching it off would change the matrix's shape rather than its
 * concurrency. Retries, the per-test timeout, globalTimeout, the projects, the
 * viewports and the spec assignment are all untouched.
 */

import type { CertificationMode } from "./env";

/** Workers for ordinary (non-certification) CI. */
export const CI_WORKERS = 2;
/** Workers for a strict certification run — serialised synthetic Customer. */
export const CERTIFICATION_WORKERS = 1;

export type WorkerPolicyInput = {
  /** True when running under CI (Playwright's own `!!process.env.CI`). */
  isCI: boolean;
  /** From `certificationMode()` — never re-parsed here. */
  mode: CertificationMode;
};

/**
 * Resolve the worker count for a run.
 *
 * `undefined` means "Playwright's own default", which is what local
 * development gets; the config passes the value through verbatim.
 */
export function resolveWorkers(input: WorkerPolicyInput): number | undefined {
  if (!input.isCI) {
    return undefined;
  }
  if (input.mode === "integrated-staging" || input.mode === "production-readiness") {
    return CERTIFICATION_WORKERS;
  }
  return CI_WORKERS;
}
