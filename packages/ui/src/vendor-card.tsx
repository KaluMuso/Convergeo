import type { ReactNode } from "react";

import { CornerRibbon } from "./corner-ribbon";
import type { TrustLevel, VendorTier } from "./corner-ribbon";

export type VendorStat = {
  label: string;
  value: string;
};

export type VendorCardProps = {
  as?: "article" | "div";
  name: string;
  categoryLabel: string;
  locationLabel: string;
  cover?: ReactNode;
  avatar?: ReactNode;
  trust?: TrustLevel;
  trustLabel?: string;
  tier?: VendorTier;
  tierLabel?: string;
  stats: VendorStat[];
  ctaLabel: string;
  onCtaClick?: () => void;
  skeleton?: boolean;
  className?: string;
};

const cardBaseStyle: React.CSSProperties = {
  backgroundColor: "var(--surface)",
  borderRadius: "var(--r-lg)",
  boxShadow: "var(--shadow-1)",
  border: "1px solid var(--border)",
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
  minWidth: 0,
};

const shimmerBlock: React.CSSProperties = {
  background: "linear-gradient(90deg, var(--bg-2) 25%, var(--border) 50%, var(--bg-2) 75%)",
  backgroundSize: "200% 100%",
  animation: "shimmer 1.4s ease-in-out infinite",
};

function VendorCardSkeleton({ className }: { className?: string }) {
  return (
    <article
      className={className}
      data-testid="vendor-card-skeleton"
      aria-busy="true"
      style={cardBaseStyle}
    >
      <div style={{ ...shimmerBlock, height: 96, width: "100%" }} />
      <div
        style={{
          padding: "var(--sp-3)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--sp-2)",
        }}
      >
        <div style={{ ...shimmerBlock, height: 20, width: "70%", borderRadius: "var(--r-sm)" }} />
        <div style={{ ...shimmerBlock, height: 14, width: "50%", borderRadius: "var(--r-sm)" }} />
      </div>
    </article>
  );
}

export function VendorCard({
  as: Component = "article",
  name,
  categoryLabel,
  locationLabel,
  cover,
  avatar,
  trust,
  trustLabel,
  tier,
  tierLabel,
  stats,
  ctaLabel,
  onCtaClick,
  skeleton = false,
  className,
}: VendorCardProps) {
  if (skeleton) {
    return <VendorCardSkeleton className={className} />;
  }

  return (
    <Component className={className} data-testid="vendor-card" style={cardBaseStyle}>
      <div style={{ position: "relative", height: 96, backgroundColor: "var(--bg-2)" }}>
        {cover}
        {avatar ? (
          <div
            style={{
              position: "absolute",
              bottom: -24,
              left: "var(--sp-3)",
              width: 56,
              height: 56,
              borderRadius: "50%",
              border: "3px solid var(--surface)",
              overflow: "hidden",
              backgroundColor: "var(--bg-2)",
            }}
          >
            {avatar}
          </div>
        ) : null}
      </div>
      <div
        style={{
          padding: "var(--sp-3)",
          paddingTop: avatar ? "var(--sp-8)" : "var(--sp-3)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--sp-2)",
          minWidth: 0,
        }}
      >
        <h3
          style={{
            margin: 0,
            fontSize: "var(--fs-h3)",
            fontWeight: 600,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {name}
        </h3>
        <p style={{ margin: 0, fontSize: "var(--fs-sm)", color: "var(--text-2)" }}>
          {categoryLabel}
        </p>
        <p
          style={{
            margin: 0,
            fontSize: "var(--fs-sm)",
            color: "var(--text-3)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {locationLabel}
        </p>
        {(trust && trustLabel) || (tier && tierLabel) ? (
          <CornerRibbon trust={trust} trustLabel={trustLabel} tier={tier} tierLabel={tierLabel} />
        ) : null}
        <div
          data-testid="vendor-stats"
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(${Math.min(stats.length, 3)}, minmax(0, 1fr))`,
            gap: "var(--sp-2)",
          }}
        >
          {stats.map((stat) => (
            <div key={stat.label} style={{ minWidth: 0, textAlign: "center" }}>
              <div
                style={{ fontSize: "var(--fs-h3)", fontWeight: 700, color: "var(--display-ink)" }}
              >
                {stat.value}
              </div>
              <div
                style={{
                  fontSize: "var(--fs-micro)",
                  color: "var(--text-3)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {stat.label}
              </div>
            </div>
          ))}
        </div>
        {onCtaClick ? (
          <button
            type="button"
            onClick={onCtaClick}
            data-testid="vendor-card-cta"
            style={{
              minHeight: 44,
              marginTop: "var(--sp-2)",
              borderRadius: "var(--r-pill)",
              border: "none",
              backgroundColor: "var(--primary)",
              color: "var(--surface)",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {ctaLabel}
          </button>
        ) : (
          <span style={{ fontSize: "var(--fs-sm)", fontWeight: 600, color: "var(--primary)" }}>
            {ctaLabel}
          </span>
        )}
      </div>
    </Component>
  );
}
