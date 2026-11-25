"use client";

import { IconHeart } from "@vergeo/ui/src/icons";
import { emitToastKey } from "@vergeo/ui/src/toast";
import { useEffect, useState } from "react";

import {
  isWishlistedLocal,
  toggleWishlistLocal,
  type WishlistKind,
} from "../../../../../lib/wishlist-local";

function syncWishlistWithServer(): Promise<void> {
  return import("../../../../../lib/engagement-api")
    .then((mod) => mod.syncWishlistWithServer())
    .catch(() => undefined);
}

export type SaveButtonProps = {
  slug: string;
  productId?: string | null;
  kind: WishlistKind;
  addLabel: string;
  removeLabel: string;
  savedAnnounceLabel: string;
};

export function SaveButton({
  slug,
  productId,
  kind,
  addLabel,
  removeLabel,
  savedAnnounceLabel,
}: SaveButtonProps) {
  const [saved, setSaved] = useState(false);
  const [announce, setAnnounce] = useState<string | null>(null);

  useEffect(() => {
    setSaved(isWishlistedLocal({ productId, slug }));
  }, [productId, slug]);

  return (
    <>
      <button
        type="button"
        data-testid="value-save-button"
        data-wishlisted={saved ? "true" : "false"}
        aria-pressed={saved}
        aria-label={saved ? removeLabel : addLabel}
        onClick={() => {
          const next = toggleWishlistLocal({ productId, slug, kind });
          setSaved(next);
          setAnnounce(next ? savedAnnounceLabel : removeLabel);
          emitToastKey(next ? "wishlistAdded" : "wishlistRemoved", {
            type: next ? "success" : "info",
          });
          void syncWishlistWithServer();
        }}
        className="inline-flex h-11 w-11 min-h-11 min-w-11 items-center justify-center rounded border border-border bg-bg text-text transition-colors hover:bg-surface disabled:opacity-50 motion-reduce:transition-none"
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
