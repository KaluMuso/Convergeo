#!/usr/bin/env node
/**
 * Canonical gate status vocabulary for release certification.
 * Every gate MUST resolve to exactly one of these — never translate
 * BLOCKED_EXTERNAL / NOT_RUN / UNKNOWN / MEASUREMENT_UNSTABLE into PASS.
 */

/** @typedef {'PASS'|'FAIL'|'BLOCKED_EXTERNAL'|'NOT_RUN'|'UNKNOWN'|'MEASUREMENT_UNSTABLE'} GateStatus */

/** @typedef {'local-development'|'ci'|'integrated-staging'|'production-readiness'} CertificationMode */

/** @typedef {'PASS'|'BASELINE_FAILING'|'BLOCKED_EXTERNAL'|'LOCAL_DEVELOPMENT_REPORT'|'INCOMPLETE_REQUIRED_GATES'} CertificationVerdict */

/** @type {readonly GateStatus[]} */
export const GATE_STATUSES = Object.freeze([
  "PASS",
  "FAIL",
  "BLOCKED_EXTERNAL",
  "NOT_RUN",
  "UNKNOWN",
  "MEASUREMENT_UNSTABLE",
]);

/** Statuses that must never satisfy a required gate in strict modes. */
export const NON_PASSING_FOR_REQUIRED = Object.freeze([
  "FAIL",
  "BLOCKED_EXTERNAL",
  "NOT_RUN",
  "UNKNOWN",
  "MEASUREMENT_UNSTABLE",
]);

/** @type {readonly CertificationMode[]} */
export const CERTIFICATION_MODES = Object.freeze([
  "local-development",
  "ci",
  "integrated-staging",
  "production-readiness",
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
 * @param {unknown} raw
 * @returns {CertificationMode}
 */
export function normalizeMode(raw) {
  const s = String(raw ?? "local-development").toLowerCase();
  if (CERTIFICATION_MODES.includes(/** @type {CertificationMode} */ (s))) {
    return /** @type {CertificationMode} */ (s);
  }
  // Back-compat aliases from PR #602 environment labels.
  if (s === "local" || s === "local-report" || s === "report-only") {
    return "local-development";
  }
  if (s === "staging") return "integrated-staging";
  if (s === "production" || s === "prod") return "production-readiness";
  return "local-development";
}

/**
 * @param {GateStatus} status
 * @returns {boolean}
 */
export function isPass(status) {
  return status === "PASS";
}

/**
 * @param {GateStatus} status
 * @returns {boolean}
 */
export function isHardFail(status) {
  return status === "FAIL";
}

/**
 * @param {GateStatus} status
 * @returns {boolean}
 */
export function isNonPass(status) {
  return status !== "PASS";
}

/**
 * Whether a required gate's status is acceptable for certification.
 * Missing gate is never equivalent to PASS — caller must pass status or null.
 *
 * @param {GateStatus | null | undefined} status
 * @returns {boolean}
 */
export function requiredGateSatisfied(status) {
  if (status == null) return false;
  return status === "PASS";
}

/**
 * @param {GateStatus | null | undefined} status
 * @returns {boolean}
 */
export function requiredGateBlocks(status) {
  if (status == null) return true;
  return NON_PASSING_FOR_REQUIRED.includes(status);
}

/**
 * Derive overall certification verdict from gate map + required IDs.
 *
 * @param {Record<string, { status: GateStatus }>} gates
 * @param {{ mode?: CertificationMode, requiredGateIds?: string[] }} [opts]
 * @returns {CertificationVerdict}
 */
export function deriveCertification(gates, opts = {}) {
  const mode = normalizeMode(opts.mode ?? "local-development");
  const required = opts.requiredGateIds ?? [];

  if (mode === "local-development") {
    // Explicitly named reporting-only verdict — never a release certificate.
    return "LOCAL_DEVELOPMENT_REPORT";
  }

  const missing = [];
  const blocking = [];
  for (const id of required) {
    const g = gates[id];
    if (!g) {
      missing.push(id);
      continue;
    }
    if (requiredGateBlocks(g.status)) {
      blocking.push({ id, status: g.status });
    }
  }

  if (missing.length > 0) {
    return "INCOMPLETE_REQUIRED_GATES";
  }

  const values = Object.values(gates);
  if (values.some((g) => g.status === "FAIL") || blocking.some((b) => b.status === "FAIL")) {
    return "BASELINE_FAILING";
  }

  if (blocking.length > 0) {
    const allExternal = blocking.every(
      (b) =>
        b.status === "BLOCKED_EXTERNAL" ||
        b.status === "NOT_RUN" ||
        b.status === "UNKNOWN" ||
        b.status === "MEASUREMENT_UNSTABLE",
    );
    // Required gates that are blocked/unstable still mean not certifiable.
    // Prefer BASELINE_FAILING when any hard FAIL elsewhere; otherwise
    // BLOCKED_EXTERNAL only if every blocking required gate is external-ish
    // AND no PASS-required path remains — still non-certifiable.
    if (allExternal && values.every((g) => g.status !== "FAIL")) {
      return "BLOCKED_EXTERNAL";
    }
    return "BASELINE_FAILING";
  }

  if (values.some((g) => g.status === "FAIL")) {
    return "BASELINE_FAILING";
  }

  // Optional gates may be NOT_RUN; required ones already checked.
  const optionalFail = values.some((g) => g.status === "FAIL");
  if (optionalFail) return "BASELINE_FAILING";

  return "PASS";
}

/**
 * Strict exit semantics for promotion/certification modes.
 * ONLY PASS may exit 0.
 * local-development (LOCAL_DEVELOPMENT_REPORT) may exit 0 (reporting-only).
 *
 * @param {CertificationVerdict} verdict
 * @param {CertificationMode} mode
 * @returns {number}
 */
export function exitCodeForVerdict(verdict, mode) {
  const m = normalizeMode(mode);
  if (m === "local-development") {
    return verdict === "LOCAL_DEVELOPMENT_REPORT" ? 0 : 1;
  }
  return verdict === "PASS" ? 0 : 1;
}

/**
 * Classify RLS outcomes. Never converts real assertion failures to BLOCKED_EXTERNAL.
 *
 * @param {{ toolAvailable: boolean, setupOk: boolean | null, testExitCode: number | null, detail?: string }} input
 * @returns {{ status: GateStatus, detail: string }}
 */
export function classifyRlsOutcome(input) {
  if (!input.toolAvailable) {
    return {
      status: "BLOCKED_EXTERNAL",
      detail: input.detail || "RLS tools unavailable (supabase CLI / local stack)",
    };
  }
  if (input.setupOk === false) {
    return {
      status: "FAIL",
      detail: input.detail || "RLS setup/provisioning defect",
    };
  }
  if (input.testExitCode == null) {
    return {
      status: "NOT_RUN",
      detail: input.detail || "RLS tests not executed",
    };
  }
  if (input.testExitCode === 0) {
    return { status: "PASS", detail: input.detail || "RLS assertions passed" };
  }
  return {
    status: "FAIL",
    detail: input.detail || `RLS assertions failed (exit ${input.testExitCode})`,
  };
}
