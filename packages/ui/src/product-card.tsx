import type { ReactNode } from "react";

import { IconHeart } from "./icons";
import { PriceBlock } from "./price-block";
import { StarRating } from "./star-rating";

export type ProductCardDensity = "default" | "compact";

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
  /** Required for a11y when `onQuickAdd` is provided. */
  quickAddLabel: string;
  /** Required for a11y when `onWishlistToggle` is provided. */
  wishlistLabel: string;
  onQuickAdd?: () => void;
  onWishlistToggle?: () => void;
  isWishlisted?: boolean;
  /**
   * Polite status text announced after wishlist toggles (e.g. “Saved to wishlist”).
   * Parent owns the string so ProductCard stays RSC-safe.
   */
  wishlistStatusAnnouncement?: string;
  skeleton?: boolean;
  className?: string;
  /** Accessible label for the empty media stage when no image is provided. */
  mediaEmptyLabel?: string;
  /** Layout density — compact for dense rails / search product grids. */
  density?: ProductCardDensity;
  /** Dims the card when the listing is unavailable (honest OOS styling). */
  unavailable?: boolean;
  /** Optional secondary meta (fulfillment, etc.) — never invent content here. */
  meta?: ReactNode;
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

function ProductCardSkeleton({ className }: { className?: string }) {
  return (
    <article
      className={cx(
        "flex min-w-0 flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-1",
        className,
      )}
      data-testid="product-card-skeleton"
      aria-busy="true"
    >
      <div className="aspect-[4/3] w-full animate-[shimmer_1.4s_ease-in-out_infinite] bg-bg-2 motion-reduce:animate-none" />
      <div className="flex flex-col gap-2 p-[var(--card-pad,var(--sp-3))]">
        <div className="h-3.5 w-2/5 rounded-pill bg-bg-2" />
        <div className="h-4 w-[90%] rounded-sm bg-bg-2" />
        <div className="h-3.5 w-3/5 rounded-sm bg-bg-2" />
        <div className="h-5 w-1/2 rounded-sm bg-bg-2" />
      </div>
    </article>
  );
}

/**
 * Marketplace product card — surface stage, clamped title, price emphasis.
 * Wishlist / quick-add render only when handlers are provided (no dead affordances).
 */
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
  wishlistStatusAnnouncement,
  skeleton = false,
  className,
  mediaEmptyLabel,
  density = "default",
  unavailable = false,
  meta,
}: ProductCardProps) {
  if (skeleton) {
    return <ProductCardSkeleton className={className} />;
  }

  const compact = density === "compact";

  return (
    <Component
      className={cx(
        "card-lift",
        "tap",
        "group flex min-w-0 flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-1",
        unavailable && "opacity-80",
        className,
      )}
      data-testid="product-card"
      data-density={density}
      data-unavailable={unavailable ? "true" : "false"}
      style={
        categoryColor
          ? {
              background: `linear-gradient(180deg, ${categoryColor}22 0%, var(--surface) 48px)`,
            }
          : undefined
      }
    >
      <div className="relative aspect-[4/3] bg-bg-2">
        {media ?? (
          <div
            className="flex h-full w-full items-center justify-center bg-gradient-to-br from-bg-2 to-border/40"
            data-testid="product-card-media-empty"
            role={mediaEmptyLabel ? "img" : undefined}
            aria-label={mediaEmptyLabel}
            aria-hidden={mediaEmptyLabel ? undefined : true}
          >
            <span className="h-12 w-16 rounded border border-dashed border-border/80 bg-surface/40" />
          </div>
        )}
        {badge ? (
          <div className={cx("absolute z-[1]", compact ? "left-1.5 top-1.5" : "left-2 top-2")}>
            {badge}
          </div>
        ) : null}
        {onWishlistToggle ? (
          <button
            type="button"
            aria-label={wishlistLabel}
            aria-pressed={isWishlisted}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onWishlistToggle();
            }}
            data-testid="product-card-wishlist"
            className="absolute right-2 top-2 z-[1] inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border border-border bg-surface text-text-2 shadow-1 transition-colors hover:text-primary focus-visible:outline-none focus-visible:shadow-focusRing"
          >
            <IconHeart
              filled={isWishlisted}
              className={isWishlisted ? "text-discount" : undefined}
            />
          </button>
        ) : null}
        {wishlistStatusAnnouncement ? (
          <span
            className="sr-only"
            aria-live="polite"
            aria-atomic="true"
            data-testid="product-card-wishlist-status"
          >
            {wishlistStatusAnnouncement}
          </span>
        ) : null}
        {onQuickAdd ? (
          <button
            type="button"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onQuickAdd();
            }}
            aria-label={quickAddLabel}
            data-testid="product-card-quick-add"
            className={cx(
              "absolute bottom-2 right-2 z-[1] inline-flex min-h-11 items-center rounded-pill bg-primary px-3 text-sm font-semibold text-[var(--primary-btn-fg)] shadow-1",
              "transition-opacity duration-fast ease-std motion-reduce:transition-none",
              "focus-visible:outline-none focus-visible:shadow-focusRing",
              // Always visible on coarse pointers; reveal on hover/focus for fine pointers.
              "max-md:opacity-100 md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100",
            )}
          >
            {quickAddLabel}
          </button>
        ) : null}
      </div>
      <div
        className={cx(
          "flex min-w-0 flex-col",
          compact ? "gap-1 p-[var(--sp-2)]" : "gap-1.5 p-[var(--sp-2)] sm:p-[var(--sp-3)]",
        )}
      >
        <p className={cx("m-0 truncate text-text-2", compact ? "text-xs" : "text-sm")}>
          {vendorLabel}
        </p>
        <h3
          className={cx(
            "m-0 line-clamp-2 font-semibold leading-snug text-text",
            compact ? "text-sm" : "text-h3",
          )}
        >
          {title}
        </h3>
        {!compact ? (
          <StarRating
            value={rating}
            reviewCount={reviewCount}
            noReviewsSlot={noReviewsLabel}
            reviewCountLabel={reviewCountLabel}
          />
        ) : null}
        <PriceBlock ngwee={ngwee} oldNgwee={oldNgwee} savingsLabel={savingsLabel} />
        {meta ? <div className="text-xs text-text-2">{meta}</div> : null}
        {compact && reviewCount > 0 ? (
          <StarRating
            value={rating}
            reviewCount={reviewCount}
            noReviewsSlot={noReviewsLabel}
            reviewCountLabel={reviewCountLabel}
          />
        ) : null}
      </div>
    </Component>
  );
}
