"use client";

import { IconHeart } from "@vergeo/ui/src/icons";
import { useEffect, useState } from "react";

import { syncWishlistWithServer } from "../../../../../lib/engagement-api";
import { isWishlistedLocal, toggleWishlistLocal } from "../../../../../lib/wishlist-local";

export type PdpWishlistButtonProps = {
  productId: string;
  productSlug: string;
  addLabel: string;
  removeLabel: string;
  savedAnnounceLabel: string;
};

/**
 * Wishlist toggle for the purchase panel. Local-first; syncs when signed in.
 */
export function PdpWishlistButton({
  productId,
  productSlug,
  addLabel,
  removeLabel,
  savedAnnounceLabel,
}: PdpWishlistButtonProps) {
  const [saved, setSaved] = useState(false);
  const [announce, setAnnounce] = useState<string | null>(null);

  useEffect(() => {
    setSaved(isWishlistedLocal({ productId, slug: productSlug }));
  }, [productId, productSlug]);

  return (
    <>
      <button
        type="button"
        data-testid="pdp-wishlist-toggle"
        data-wishlisted={saved ? "true" : "false"}
        aria-pressed={saved}
        aria-label={saved ? removeLabel : addLabel}
        onClick={() => {
          const next = toggleWishlistLocal({ productId, slug: productSlug });
          setSaved(next);
          setAnnounce(next ? savedAnnounceLabel : removeLabel);
          void syncWishlistWithServer();
        }}
        className="inline-flex min-h-11 min-w-11 items-center justify-center rounded border border-border bg-bg text-text transition-colors hover:bg-surface disabled:opacity-50 motion-reduce:transition-none"
        style={{ borderRadius: "var(--r)" }}
      >
        <IconHeart filled={saved} className={saved ? "text-danger" : "text-text-2"} />
      </button>
      <span className="sr-only" aria-live="polite">
        {announce}
      </span>
    </>
  );
}
