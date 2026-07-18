/**
 * KYC integrity helpers (VEND-01 / MR-D02).
 *
 * Production evidence showed `vendors.kyc_tier=2` with `kyc_records=0`.
 * Vendor UI must never treat a bare tier integer as "verified" unless an
 * auditable KYC record exists and the application is approved.
 */

export type KycIntegrityInput = {
  kyc_tier: number | null;
  kyc_status: string;
  kyc_record_id: string | null;
  kyc_record_status: string | null;
};

/** True when the API returned a KYC record id we can audit. */
export function hasAuditableKycRecord(input: KycIntegrityInput): boolean {
  return typeof input.kyc_record_id === "string" && input.kyc_record_id.length > 0;
}

/** Approved only when status is approved AND a record id exists. */
export function isAuditableApproved(input: KycIntegrityInput): boolean {
  if (!hasAuditableKycRecord(input)) {
    return false;
  }
  if (input.kyc_status !== "approved") {
    return false;
  }
  // When the API returns a per-record status, it must agree with approval.
  if (input.kyc_record_status !== null && input.kyc_record_status !== "approved") {
    return false;
  }
  return true;
}

/**
 * Effective tier for capability UI (e.g. wholesale).
 * Returns null when tier is unknown or not backed by an auditable approved record.
 * Tier 1 (basic seller) is allowed once approved with a record; tier ≥2 requires the same.
 */
export function effectiveKycTier(input: KycIntegrityInput): number | null {
  if (!isAuditableApproved(input)) {
    return null;
  }
  if (input.kyc_tier === null || input.kyc_tier === undefined) {
    return 1;
  }
  return input.kyc_tier;
}

/** Wholesale / T2+ capabilities — only when auditable approved AND tier ≥ 2. */
export function canUseWholesaleCapabilities(input: KycIntegrityInput): boolean {
  const tier = effectiveKycTier(input);
  return tier !== null && tier >= 2;
}

/**
 * Preferred badge is a separate earned flag from the profile API.
 * Never invent it from kyc_tier alone.
 */
export function shouldShowPreferredBadge(preferredBadge: boolean | null | undefined): boolean {
  return preferredBadge === true;
}
