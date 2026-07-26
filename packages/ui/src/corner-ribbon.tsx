import { tokens } from "@vergeo/ui/tokens";

export type TrustLevel = "self_listed" | "id_verified" | "sector_verified" | "preferred";
export type VendorTier = "bronze" | "silver" | "gold" | "platinum";

export type CornerRibbonProps = {
  trust?: TrustLevel;
  trustLabel?: string;
  tier?: VendorTier;
  tierLabel?: string;
  className?: string;
};

const trustColors: Record<TrustLevel, string> = {
  self_listed: tokens.colors.text3,
  id_verified: tokens.colors.info,
  sector_verified: tokens.colors.success,
  preferred: tokens.colors.accent,
};

const tierColors: Record<VendorTier, string> = {
  bronze: "#A67C52",
  silver: "#8A9BAA",
  gold: tokens.colors.accent,
  platinum: tokens.colors.primaryDeep,
};

export function CornerRibbon({ trust, trustLabel, tier, tierLabel, className }: CornerRibbonProps) {
  return (
    <div
      className={className}
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "var(--sp-2)",
      }}
    >
      {trust && trustLabel ? (
        <span
          data-testid="corner-ribbon-trust"
          data-trust={trust}
          style={{
            display: "inline-flex",
            alignItems: "center",
            padding: "4px 10px",
            borderRadius: "var(--r-pill)",
            fontSize: "var(--fs-sm)",
            fontWeight: 600,
            backgroundColor: `${trustColors[trust]}1A`,
            border: `1px solid ${trustColors[trust]}33`,
            // Dark label (not the accent) so the text meets 4.5:1 AA on the tint;
            // the accent identifies the badge via its border + background.
            color: "var(--text)",
          }}
        >
          {trustLabel}
        </span>
      ) : null}
      {tier && tierLabel ? (
        <span
          data-testid="corner-ribbon-tier"
          data-tier={tier}
          style={{
            display: "inline-flex",
            alignItems: "center",
            padding: "4px 10px",
            borderRadius: "var(--r-pill)",
            fontSize: "var(--fs-sm)",
            fontWeight: 600,
            backgroundColor: `${tierColors[tier]}1A`,
            border: `1px solid ${tierColors[tier]}33`,
            // Dark label (not the tier accent) so the text meets 4.5:1 AA on the
            // tint (bronze #A67C52 was 3.35); the accent stays on border + bg.
            color: "var(--text)",
          }}
        >
          {tierLabel}
        </span>
      ) : null}
    </div>
  );
}
