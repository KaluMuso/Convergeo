import { strictCertificationRequired } from "./env";
import { resolveGatePolicy } from "./gating-policy";
import type { GateInput, GateKind, GateVerdict } from "./gating-policy";

export type { GateKind, GateVerdict };

/**
 * Decide what to do about an unavailable precondition.
 *
 * The strict flag comes from the existing `strictCertificationRequired()`
 * helper — there is deliberately no second definition of "strict mode".
 */
export function resolveGate(input: Omit<GateInput, "strict">): GateVerdict {
  return resolveGatePolicy({ ...input, strict: strictCertificationRequired() });
}

/** Throw when a required journey cannot run in a certification run. */
export function enforceGate(verdict: GateVerdict): void {
  if (verdict.action === "fail") {
    throw new Error(verdict.reason);
  }
}
