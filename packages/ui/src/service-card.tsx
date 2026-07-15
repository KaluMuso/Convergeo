import type { ReactNode } from "react";

import { Pill } from "./pill";
import { PriceBlock } from "./price-block";
import { StarRating } from "./star-rating";

export type ServiceTag = {
  label: string;
  color: string;
};

export type ServiceCardProps = {
  as?: "article" | "div";
  title: string;
  providerLabel: string;
  media?: ReactNode;
  tags?: ServiceTag[];
  fromNgwee?: number;
  fromPriceLabel?: string;
  rating: number;
  reviewCount: number;
  noReviewsLabel?: ReactNode;
  reviewCountLabel?: string;
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

function ServiceCardSkeleton({ className }: { className?: string }) {
  return (
    <article
      className={className}
      data-testid="service-card-skeleton"
      aria-busy="true"
      style={cardBaseStyle}
    >
      <div style={{ ...shimmerBlock, aspectRatio: "3 / 2", width: "100%" }} />
      <div
        style={{
          padding: "var(--sp-3)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--sp-2)",
        }}
      >
        <div style={{ ...shimmerBlock, height: 18, width: "80%", borderRadius: "var(--r-sm)" }} />
        <div style={{ ...shimmerBlock, height: 14, width: "55%", borderRadius: "var(--r-sm)" }} />
      </div>
    </article>
  );
}

export function ServiceCard({
  as: Component = "article",
  title,
  providerLabel,
  media,
  tags,
  fromNgwee,
  fromPriceLabel,
  rating,
  reviewCount,
  noReviewsLabel,
  reviewCountLabel,
  ctaLabel,
  onCtaClick,
  skeleton = false,
  className,
}: ServiceCardProps) {
  if (skeleton) {
    return <ServiceCardSkeleton className={className} />;
  }

  return (
    <Component
      className={["card-lift", className].filter(Boolean).join(" ")}
      data-testid="service-card"
      style={cardBaseStyle}
    >
      <div style={{ aspectRatio: "3 / 2", backgroundColor: "var(--bg-2)" }}>{media}</div>
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
          {providerLabel}
        </p>
        <StarRating
          value={rating}
          reviewCount={reviewCount}
          noReviewsSlot={noReviewsLabel}
          reviewCountLabel={reviewCountLabel}
        />
        {tags && tags.length > 0 ? (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-2)" }}>
            {tags.map((tag) => (
              <Pill key={tag.label} label={tag.label} color={tag.color} />
            ))}
          </div>
        ) : null}
        {fromNgwee !== undefined && fromPriceLabel ? (
          <div style={{ display: "flex", alignItems: "baseline", gap: "var(--sp-2)" }}>
            <span style={{ fontSize: "var(--fs-sm)", color: "var(--text-2)" }}>
              {fromPriceLabel}
            </span>
            <PriceBlock ngwee={fromNgwee} />
          </div>
        ) : null}
        {onCtaClick ? (
          <button
            type="button"
            onClick={onCtaClick}
            data-testid="service-card-cta"
            style={{
              minHeight: 44,
              marginTop: "var(--sp-2)",
              borderRadius: "var(--r-pill)",
              border: "1px solid var(--primary)",
              backgroundColor: "transparent",
              color: "var(--primary)",
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
