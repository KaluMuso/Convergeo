import { FIXTURE_VERSION, SEED, SEED_PREFIX } from "./seed.generated";
import { expectedFixtureVersion, strictCertificationRequired } from "./env";

/**
 * Canonical synthetic fixtures, re-exported from the generated contract.
 *
 * The identifiers themselves live in `seed.generated.ts`, which is emitted from
 * `services/api/app/staging/synthetic_contract.py` — the same source the seeder
 * writes from. They used to be hand-authored here and silently disagreed with
 * what the seeder actually creates, so every seeded assertion was doomed before
 * it ran.
 */
export { FIXTURE_VERSION, SEED, SEED_PREFIX };

/** Correlation id echoed by callers so staging logs can trace a run. */
export function runTag(): string {
  return `e2e-${process.env.GITHUB_RUN_ID ?? "local"}-${Date.now()}`;
}

/**
 * Verify — never mutate — the fixture generation under test.
 *
 * The destructive reset deliberately does NOT live here any more. It used to run
 * from a module-scope `beforeAll`, which Playwright executes once per spec file
 * per project: 16 files x 5 viewport projects meant ~80 interleaved destructive
 * resets, with workers deleting rows other workers were asserting on. The reset
 * is now a single guarded step in the workflow, before any browser starts.
 *
 * In a strict certification run the expected version must be present and must
 * match; outside strict mode this is advisory so local exploration still works.
 */
export function verifyFixtureVersion(): { ok: boolean; reason?: string } {
  const expected = expectedFixtureVersion();
  if (!expected) {
    if (strictCertificationRequired()) {
      return {
        ok: false,
        reason:
          "strictCertification: E2E_FIXTURE_VERSION is not set — the canonical seed step must publish the fixture version it applied",
      };
    }
    return { ok: true };
  }
  if (expected !== FIXTURE_VERSION) {
    return {
      ok: false,
      reason: `fixture version mismatch: staging was seeded from ${expected}, this suite was built against ${FIXTURE_VERSION}`,
    };
  }
  return { ok: true };
}

/** Throw in strict mode when the seeded fixture generation is not the expected one. */
export function assertFixtureVersion(): void {
  const verdict = verifyFixtureVersion();
  if (!verdict.ok) {
    throw new Error(verdict.reason ?? "fixture version verification failed");
  }
}
