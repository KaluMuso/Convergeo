/**
 * Pure gating policy — deliberately dependency-free.
 *
 * Kept separate from `gating.ts` so it can be unit-tested directly by Node
 * (`--experimental-strip-types`) in ordinary CI, without a browser, a Playwright
 * run, or the E2E workflow. `gating.ts` is the thin wrapper that supplies the
 * strict flag from the existing certification-mode helper.
 */

export type GateKind =
  /** Part of the release-critical suite. In a certification run, missing => FAIL. */
  | "REQUIRED_STRICT"
  /** Genuinely optional founder gate (e.g. Lenco sandbox money, WhatsApp mock). */
  | "OPTIONAL_GATE"
  /** The feature itself is intentionally switched off. */
  | "FEATURE_DISABLED"
  /** The assertion does not apply at this viewport / target. */
  | "VIEWPORT_NOT_APPLICABLE";

export type GateVerdict = {
  action: "fail" | "skip";
  kind: GateKind;
  reason: string;
};

export type GateInput = {
  kind: GateKind;
  /** Human-readable journey label, e.g. "vendor authenticated sell flow". */
  journey: string;
  /** Missing fixture variable NAMES, never their values. */
  fixtures?: readonly string[];
  /** Extra non-secret context, e.g. "payment surface not reached". */
  detail?: string;
  /** True in integrated-staging / production-readiness certification. */
  strict: boolean;
};

/**
 * Only REQUIRED_STRICT escalates, and only in a certification run. Every other
 * kind keeps skipping exactly as before, so no genuinely optional founder gate
 * is turned into a failure.
 *
 * SECRET HYGIENE: `fixtures` carries variable NAMES only. Never pass an OTP
 * code, ticket PIN, service-role key, database URL or Vercel bypass secret —
 * the reason string surfaces in failure messages and test reports.
 */
export function resolveGatePolicy(input: GateInput): GateVerdict {
  const { kind, journey, fixtures = [], detail, strict } = input;
  const missing = fixtures.length ? ` — missing fixture(s): ${fixtures.join(", ")}` : "";
  const because = detail ? ` — ${detail}` : "";

  if (kind === "REQUIRED_STRICT" && strict) {
    return {
      action: "fail",
      kind,
      reason: `REQUIRED_STRICT: ${journey} is part of the release-critical suite and cannot be skipped in integrated-staging certification${missing}${because}`,
    };
  }
  return {
    action: "skip",
    kind,
    reason: `${kind}: ${journey} skipped${missing}${because}`,
  };
}
