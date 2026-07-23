import type { TrustLevel, VendorTier } from "./corner-ribbon";

export type { TrustLevel, VendorTier };

/** Ordered commercial tiers — Platinum reserved for future billing (D3). */
export const COMMERCIAL_TIER_ORDER: readonly VendorTier[] = [
  "bronze",
  "silver",
  "gold",
  "platinum",
] as const;

/** Static metadata for tier strip / perk display (labels via i18n in apps). */
export const TIER_META: Record<VendorTier, { order: number; accentVar: string }> = {
  bronze: { order: 0, accentVar: "#A67C52" },
  silver: { order: 1, accentVar: "#8A9BAA" },
  gold: { order: 2, accentVar: "var(--accent)" },
  platinum: { order: 3, accentVar: "var(--primary-deep)" },
};

export type VendorTrustInput = {
  preferredBadge: boolean;
  /** Auditable approved KYC tier (1–3), not commercial tier. */
  kycTier: number | null;
};

/** Map KYC / preferred signals to the trust ladder (never commercial tier). */
export function resolveTrustLevel(input: VendorTrustInput): TrustLevel {
  if (input.preferredBadge) {
    return "preferred";
  }
  if (input.kycTier !== null && input.kycTier >= 2) {
    return "sector_verified";
  }
  if (input.kycTier !== null && input.kycTier >= 1) {
    return "id_verified";
  }
  return "self_listed";
}

/** Whether a trust pill should appear on compact cards (skip self-listed). */
export function trustLevelForCard(input: VendorTrustInput): TrustLevel | undefined {
  const level = resolveTrustLevel(input);
  return level === "self_listed" ? undefined : level;
}

/** NULL or unknown → bronze (free tier at launch). */
export function normalizeCommercialTier(value: string | null | undefined): VendorTier {
  if (value === "silver" || value === "gold" || value === "platinum") {
    return value;
  }
  return "bronze";
}
