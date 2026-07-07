import type { CSSProperties, ReactNode } from "react";

import { PriceBlock } from "./price-block";
import { StarRating } from "./star-rating";

export type ProductCardProps = {
  as?: "article" | "div";
  title: string;
  vendorLabel: string;
  media?: ReactNode;
  categoryColor?: string;
  badge?: ReactNode;
  ngwee: number;
  oldNgwee?: number;
  savingsLabel?: string;
  rating: number;
  reviewCount: number;
  noReviewsLabel?: ReactNode;
  reviewCountLabel?: string;
  quickAddLabel: string;
  wishlistLabel: string;
  onQuickAdd?: () => void;
  onWishlistToggle?: () => void;
  isWishlisted?: boolean;
  skeleton?: boolean;
  className?: string;
};

const cardBaseStyle: CSSProperties = {
  backgroundColor: "var(--surface)",
  borderRadius: "var(--r-lg)",
  boxShadow: "var(--shadow-1)",
  border: "1px solid var(--border)",
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
  minWidth: 0,
  transition: "box-shadow var(--dur) var(--ease-out), transform var(--dur) var(--ease-out)",
};

const shimmerBlock: CSSProperties = {
  background: "linear-gradient(90deg, var(--bg-2) 25%, var(--border) 50%, var(--bg-2) 75%)",
  backgroundSize: "200% 100%",
  animation: "shimmer 1.4s ease-in-out infinite",
};

function ProductCardSkeleton({ className }: { className?: string }) {
  return (
    <article
      className={className}
      data-testid="product-card-skeleton"
      aria-busy="true"
      style={cardBaseStyle}
    >
      <div style={{ ...shimmerBlock, aspectRatio: "4 / 3", width: "100%" }} />
      <div
        style={{
          padding: "var(--sp-3)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--sp-2)",
        }}
      >
        <div style={{ ...shimmerBlock, height: 14, width: "40%", borderRadius: "var(--r-pill)" }} />
        <div style={{ ...shimmerBlock, height: 18, width: "90%", borderRadius: "var(--r-sm)" }} />
        <div style={{ ...shimmerBlock, height: 14, width: "60%", borderRadius: "var(--r-sm)" }} />
        <div style={{ ...shimmerBlock, height: 20, width: "50%", borderRadius: "var(--r-sm)" }} />
      </div>
    </article>
  );
}

export function ProductCard({
  as: Component = "article",
  title,
  vendorLabel,
  media,
  categoryColor,
  badge,
  ngwee,
  oldNgwee,
  savingsLabel,
  rating,
  reviewCount,
  noReviewsLabel,
  reviewCountLabel,
  quickAddLabel,
  wishlistLabel,
  onQuickAdd,
  onWishlistToggle,
  isWishlisted = false,
  skeleton = false,
  className,
}: ProductCardProps) {
  if (skeleton) {
    return <ProductCardSkeleton className={className} />;
  }

  return (
    <Component
      className={className}
      data-testid="product-card"
      style={{
        ...cardBaseStyle,
        ...(categoryColor
          ? { background: `linear-gradient(180deg, ${categoryColor}22 0%, var(--surface) 48px)` }
          : {}),
      }}
    >
      <div style={{ position: "relative", aspectRatio: "4 / 3", backgroundColor: "var(--bg-2)" }}>
        {media}
        {badge ? (
          <div style={{ position: "absolute", top: "var(--sp-2)", left: "var(--sp-2)" }}>
            {badge}
          </div>
        ) : null}
        <div
          style={{
            position: "absolute",
            top: "var(--sp-2)",
            right: "var(--sp-2)",
            display: "flex",
            gap: "var(--sp-2)",
          }}
        >
          {onWishlistToggle ? (
            <button
              type="button"
              aria-label={wishlistLabel}
              aria-pressed={isWishlisted}
              onClick={onWishlistToggle}
              data-testid="product-card-wishlist"
              style={{
                minWidth: 44,
                minHeight: 44,
                borderRadius: "50%",
                border: "1px solid var(--border)",
                backgroundColor: "var(--surface)",
                cursor: "pointer",
              }}
            >
              {isWishlisted ? "♥" : "♡"}
            </button>
          ) : null}
        </div>
        {onQuickAdd ? (
          <button
            type="button"
            onClick={onQuickAdd}
            aria-label={quickAddLabel}
            data-testid="product-card-quick-add"
            style={{
              position: "absolute",
              bottom: "var(--sp-2)",
              right: "var(--sp-2)",
              minHeight: 44,
              padding: "0 var(--sp-3)",
              borderRadius: "var(--r-pill)",
              border: "none",
              backgroundColor: "var(--primary)",
              color: "var(--surface)",
              fontWeight: 600,
              fontSize: "var(--fs-sm)",
              cursor: "pointer",
            }}
          >
            {quickAddLabel}
          </button>
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
          {vendorLabel}
        </p>
        <h3
          style={{
            margin: 0,
            fontSize: "var(--fs-h3)",
            fontWeight: 600,
            color: "var(--text)",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
            lineHeight: 1.3,
          }}
        >
          {title}
        </h3>
        <StarRating
          value={rating}
          reviewCount={reviewCount}
          noReviewsSlot={noReviewsLabel}
          reviewCountLabel={reviewCountLabel}
        />
        <PriceBlock ngwee={ngwee} oldNgwee={oldNgwee} savingsLabel={savingsLabel} />
      </div>
    </Component>
  );
}
