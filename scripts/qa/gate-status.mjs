#!/usr/bin/env node
/**
 * Canonical gate status vocabulary for release certification.
 * Every gate MUST resolve to exactly one of these — never translate
 * BLOCKED_EXTERNAL / NOT_RUN / UNKNOWN / MEASUREMENT_UNSTABLE into PASS.
 */

/** @typedef {'PASS'|'FAIL'|'BLOCKED_EXTERNAL'|'NOT_RUN'|'UNKNOWN'|'MEASUREMENT_UNSTABLE'} GateStatus */

/** @type {readonly GateStatus[]} */
export const GATE_STATUSES = Object.freeze([
  "PASS",
  "FAIL",
  "BLOCKED_EXTERNAL",
  "NOT_RUN",
  "UNKNOWN",
  "MEASUREMENT_UNSTABLE",
]);

/** @type {Set<GateStatus>} */
const PASS_LIKE = new Set(["PASS"]);

/** @type {Set<GateStatus>} */
const FAIL_LIKE = new Set(["FAIL"]);

/** @type {Set<GateStatus>} */
const NON_PASS = new Set([
  "FAIL",
  "BLOCKED_EXTERNAL",
  "NOT_RUN",
  "UNKNOWN",
  "MEASUREMENT_UNSTABLE",
]);

/**
 * @param {unknown} raw
 * @returns {GateStatus}
 */
export function normalizeStatus(raw) {
  const s = String(raw ?? "UNKNOWN").toUpperCase();
  if (GATE_STATUSES.includes(/** @type {GateStatus} */ (s))) {
    return /** @type {GateStatus} */ (s);
  }
  return "UNKNOWN";
}

/**
 * @param {GateStatus} status
 * @returns {boolean}
 */
export function isPass(status) {
  return PASS_LIKE.has(status);
}

/**
 * @param {GateStatus} status
 * @returns {boolean}
 */
export function isHardFail(status) {
  return FAIL_LIKE.has(status);
}

/**
 * @param {GateStatus} status
 * @returns {boolean}
 */
export function isNonPass(status) {
  return NON_PASS.has(status);
}

/**
 * Derive overall certification verdict from gate map.
 * @param {Record<string, { status: GateStatus }>} gates
 * @returns {'CERTIFIABLE_AFTER_INTEGRATION'|'BASELINE_FAILING'|'BLOCKED_EXTERNAL'}
 */
export function deriveCertification(gates) {
  const values = Object.values(gates);
  if (values.some((g) => g.status === "FAIL")) {
    return "BASELINE_FAILING";
  }
  const allBlocked =
    values.length > 0 &&
    values.every(
      (g) => g.status === "BLOCKED_EXTERNAL" || g.status === "NOT_RUN" || g.status === "UNKNOWN",
    );
  if (allBlocked) {
    return "BLOCKED_EXTERNAL";
  }
  // Any non-PASS (except pure FAIL handled above) blocks full certification.
  if (values.some((g) => isNonPass(g.status))) {
    return "BASELINE_FAILING";
  }
  return "CERTIFIABLE_AFTER_INTEGRATION";
}
