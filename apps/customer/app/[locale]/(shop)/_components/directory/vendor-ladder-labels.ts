import {
  normalizeCommercialTier,
  resolveTrustLevel,
  trustLevelForCard,
  type TrustLevel,
  type VendorTier,
} from "@vergeo/ui/src/vendor-ladder";

export type VendorLadderLabels = {
  trust: Record<TrustLevel, string>;
  tiers: Record<VendorTier, string>;
  tierPerks: Record<VendorTier, string>;
  tierStripAria: string;
};

export function vendorTrustForCard(
  input: { preferredBadge: boolean; kycTier: number | null },
  labels: VendorLadderLabels,
): { trust?: TrustLevel; trustLabel?: string } {
  const trust = trustLevelForCard({
    preferredBadge: input.preferredBadge,
    kycTier: input.kycTier,
  });
  if (!trust) {
    return {};
  }
  return { trust, trustLabel: labels.trust[trust] };
}

export function vendorCommercialTier(
  commercialTier: string | null | undefined,
  labels: VendorLadderLabels,
): { tier: VendorTier; tierLabel: string } {
  const tier = normalizeCommercialTier(commercialTier);
  return { tier, tierLabel: labels.tiers[tier] };
}

export function vendorTrustRibbon(
  input: { preferredBadge: boolean; kycTier: number | null },
  labels: VendorLadderLabels,
): { trust: TrustLevel; trustLabel: string } {
  const trust = resolveTrustLevel({
    preferredBadge: input.preferredBadge,
    kycTier: input.kycTier,
  });
  return { trust, trustLabel: labels.trust[trust] };
}

export function buildTierStripItems(labels: VendorLadderLabels) {
  return (["bronze", "silver", "gold", "platinum"] as const).map((id) => ({
    id,
    label: labels.tiers[id],
    perk: labels.tierPerks[id],
  }));
}

export function buildVendorLadderLabels(t: (key: string) => string): VendorLadderLabels {
  const tr = (key: string): string => t(key);
  return {
    trust: {
      self_listed: tr("trust.selfListed"),
      id_verified: tr("trust.idVerified"),
      sector_verified: tr("trust.sectorVerified"),
      preferred: tr("trust.preferred"),
    },
    tiers: {
      bronze: tr("tiers.bronze"),
      silver: tr("tiers.silver"),
      gold: tr("tiers.gold"),
      platinum: tr("tiers.platinum"),
    },
    tierPerks: {
      bronze: tr("tiers.perks.bronze"),
      silver: tr("tiers.perks.silver"),
      gold: tr("tiers.perks.gold"),
      platinum: tr("tiers.perks.platinum"),
    },
    tierStripAria: tr("tiers.stripAria"),
  };
}
