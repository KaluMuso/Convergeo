import type { ReactNode } from "react";

import { PriceBlock } from "./price-block";

export type EventCardProps = {
  as?: "article" | "div";
  title: string;
  dateLabel: string;
  venueLabel: string;
  media?: ReactNode;
  badge?: ReactNode;
  isFree?: boolean;
  freeLabel?: string;
  ngwee?: number;
  spotsFilled: number;
  spotsTotal: number;
  capacityLabel: string;
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

function EventCardSkeleton({ className }: { className?: string }) {
  return (
    <article
      className={className}
      data-testid="event-card-skeleton"
      aria-busy="true"
      style={cardBaseStyle}
    >
      <div style={{ ...shimmerBlock, aspectRatio: "16 / 9", width: "100%" }} />
      <div
        style={{
          padding: "var(--sp-3)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--sp-2)",
        }}
      >
        <div style={{ ...shimmerBlock, height: 18, width: "85%", borderRadius: "var(--r-sm)" }} />
        <div style={{ ...shimmerBlock, height: 14, width: "70%", borderRadius: "var(--r-sm)" }} />
        <div style={{ ...shimmerBlock, height: 8, width: "100%", borderRadius: "var(--r-pill)" }} />
      </div>
    </article>
  );
}

export function EventCard({
  as: Component = "article",
  title,
  dateLabel,
  venueLabel,
  media,
  badge,
  isFree = false,
  freeLabel,
  ngwee,
  spotsFilled,
  spotsTotal,
  capacityLabel,
  ctaLabel,
  onCtaClick,
  skeleton = false,
  className,
}: EventCardProps) {
  if (skeleton) {
    return <EventCardSkeleton className={className} />;
  }

  const fillPercent =
    spotsTotal > 0 ? Math.min(100, Math.round((spotsFilled / spotsTotal) * 100)) : 0;

  return (
    <Component
      className={["card-lift", className].filter(Boolean).join(" ")}
      data-testid="event-card"
      style={cardBaseStyle}
    >
      <div style={{ position: "relative", aspectRatio: "16 / 9", backgroundColor: "var(--bg-2)" }}>
        {media}
        {badge ? (
          <div style={{ position: "absolute", top: "var(--sp-2)", left: "var(--sp-2)" }}>
            {badge}
          </div>
        ) : null}
      </div>
      <div
        style={{
          padding: "var(--sp-3)",
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
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {title}
        </h3>
        <p style={{ margin: 0, fontSize: "var(--fs-sm)", color: "var(--text-2)" }}>{dateLabel}</p>
        <p
          style={{
            margin: 0,
            fontSize: "var(--fs-sm)",
            color: "var(--text-2)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {venueLabel}
        </p>
        <div data-testid="event-capacity-bar">
          <div
            style={{
              height: 8,
              borderRadius: "var(--r-pill)",
              backgroundColor: "var(--bg-2)",
              overflow: "hidden",
            }}
          >
            <div
              data-testid="spots-fill"
              style={{
                height: "100%",
                width: `${fillPercent}%`,
                backgroundColor: "var(--primary)",
                borderRadius: "var(--r-pill)",
                transition: "width var(--dur) var(--ease-out)",
              }}
            />
          </div>
          <p style={{ margin: "4px 0 0", fontSize: "var(--fs-micro)", color: "var(--text-3)" }}>
            {capacityLabel}
          </p>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "var(--sp-2)",
          }}
        >
          {isFree && freeLabel ? (
            <span
              data-testid="event-free-label"
              style={{ fontSize: "var(--fs-price)", fontWeight: 700, color: "var(--success)" }}
            >
              {freeLabel}
            </span>
          ) : ngwee !== undefined ? (
            <PriceBlock ngwee={ngwee} />
          ) : null}
          {onCtaClick ? (
            <button
              type="button"
              onClick={onCtaClick}
              data-testid="event-card-cta"
              style={{
                minHeight: 44,
                padding: "0 var(--sp-4)",
                borderRadius: "var(--r-pill)",
                border: "none",
                backgroundColor: "var(--primary)",
                color: "var(--surface)",
                fontWeight: 600,
                cursor: "pointer",
                flexShrink: 0,
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
      </div>
    </Component>
  );
}
