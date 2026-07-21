"use client";

import { formatK } from "@vergeo/i18n";
import { Button } from "@vergeo/ui/src/button";
import { useTranslations } from "next-intl";
import { useEffect, useState, type RefObject } from "react";

import type { BuyBoxLabels, BuyBoxListing } from "./buy-box";
import type { ListingPurchaseControls } from "./use-listing-purchase";

type StickyMobileAtcProps = {
  listing: BuyBoxListing;
  labels: BuyBoxLabels;
  purchase: ListingPurchaseControls;
  /** Element observed to decide when the sticky bar should appear. */
  observeRef: RefObject<HTMLElement | null>;
  ariaLabel: string;
  onVisibleChange?: (visible: boolean) => void;
};

/**
 * Compact fixed ATC bar for mobile PDP (audit E10).
 * Appears when the primary buy box leaves the viewport; clears shop bottom nav.
 */
export function StickyMobileAtc({
  listing,
  labels,
  purchase,
  observeRef,
  ariaLabel,
  onVisibleChange,
}: StickyMobileAtcProps) {
  const t = useTranslations("catalog");
  const [buyBoxOutOfView, setBuyBoxOutOfView] = useState(false);
  const visible = buyBoxOutOfView && listing.inStock;
  const moqLabel = listing.moq > 1 ? t("pdp.buyBox.moq", { count: listing.moq }) : null;

  useEffect(() => {
    const target = observeRef.current;
    if (!target || typeof IntersectionObserver === "undefined") {
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry) {
          return;
        }
        // Show sticky ATC once the buy box is mostly out of view.
        setBuyBoxOutOfView(!entry.isIntersecting);
      },
      { root: null, threshold: 0.15, rootMargin: "-48px 0px 0px 0px" },
    );

    observer.observe(target);
    return () => observer.disconnect();
  }, [observeRef, listing.id]);

  useEffect(() => {
    onVisibleChange?.(visible);
    return () => onVisibleChange?.(false);
  }, [visible, onVisibleChange]);

  if (!visible) {
    return null;
  }

  return (
    <div
      data-testid="pdp-sticky-mobile-atc"
      role="region"
      aria-label={ariaLabel}
      className="fixed inset-x-0 z-40 border-t border-border bg-surface lg:hidden"
      style={{
        bottom: "calc(3.5rem + env(safe-area-inset-bottom, 0px))",
        boxShadow: "var(--shadow-2)",
        transition: "transform var(--dur) var(--ease-out), opacity var(--dur) var(--ease-out)",
      }}
    >
      <div className="mx-auto flex max-w-lg items-center gap-3 px-4 py-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-micro text-text-2">{listing.title}</p>
          <p
            className="font-mono text-lg font-semibold text-[var(--price)]"
            data-testid="pdp-sticky-price"
          >
            {formatK(listing.priceNgwee)}
          </p>
          <p
            className="truncate text-micro font-medium text-success"
            data-testid="pdp-sticky-stock"
          >
            {purchase.stockLabel}
            {moqLabel ? <span className="font-normal text-text-2"> · {moqLabel}</span> : null}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            aria-label={labels.decreaseLabel}
            data-testid="pdp-sticky-qty-decrease"
            onClick={purchase.decrease}
            disabled={purchase.atMin || purchase.adding}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded border border-border bg-bg text-lg disabled:opacity-50"
          >
            <span aria-hidden>{labels.decreaseSymbol}</span>
          </button>
          <output
            data-testid="pdp-sticky-qty-value"
            className="min-w-8 text-center font-mono text-base"
            aria-live="polite"
          >
            {purchase.quantity}
          </output>
          <button
            type="button"
            aria-label={labels.increaseLabel}
            data-testid="pdp-sticky-qty-increase"
            onClick={purchase.increase}
            disabled={purchase.atMax || purchase.adding}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded border border-border bg-bg text-lg disabled:opacity-50"
          >
            <span aria-hidden>{labels.increaseSymbol}</span>
          </button>
        </div>
        <Button
          type="button"
          variant="primary"
          size="md"
          className="shrink-0"
          disabled={purchase.adding}
          loading={purchase.adding}
          loadingLabel={labels.addingToCartLabel}
          data-testid="pdp-sticky-add-to-cart"
          aria-label={labels.addToCartLabel}
          onClick={purchase.handleAddToCart}
        >
          {labels.addToCartLabel}
        </Button>
      </div>
    </div>
  );
}
