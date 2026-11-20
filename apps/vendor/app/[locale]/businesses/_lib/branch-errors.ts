import { ApiError } from "@vergeo/config";

const KNOWN = new Set([
  "disabled",
  "businessNotFound",
  "branchNotFound",
  "businessSuspended",
  "ownerKycRequired",
  "locationRequired",
  "slugInvalid",
  "unregisteredLimit",
  "planLimit",
  "tooClose",
  "payoutTaken",
  "evidenceRequired",
  "evidenceLocked",
  "evidencePath",
  "invalidTransition",
  "pacraRequired",
  "pacraTaken",
  "staffSeatLimit",
  "staffDuplicate",
  "rateLimited",
]);

/** `vendor` namespace key for a branch API failure (field-level copy when known). */
export function branchErrorKey(error: unknown): string {
  if (error instanceof ApiError) {
    const raw = error.details?.message_key;
    if (typeof raw === "string" && raw.startsWith("vendor.branches.errors.")) {
      const leaf = raw.slice("vendor.branches.errors.".length);
      if (KNOWN.has(leaf)) return `branches.errors.${leaf}`;
    }
    if (error.status === 429) return "branches.errors.rateLimited";
    if (error.status === 422) return "branches.errors.validation";
    if (error.status === 0) return "branches.errors.network";
  }
  return "branches.errors.generic";
}

export function tooCloseValues(error: unknown): { min: number; nearest: number } | null {
  if (!(error instanceof ApiError)) return null;
  const min = error.details?.min_m;
  const nearest = error.details?.nearest_m;
  return typeof min === "number" && typeof nearest === "number" ? { min, nearest } : null;
}
