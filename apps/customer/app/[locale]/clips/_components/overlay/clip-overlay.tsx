"use client";

import { useTranslations } from "next-intl";
import { useRef, useState } from "react";

import { ProductSheet } from "./product-sheet";

import type { Clip } from "../types";

/**
 * M17-P05 — the shoppable overlay, mounted into M17-P04's marked slot.
 *
 * **Non-obstructive by construction.** The overlay is a single chip in the
 * card's bottom strip — it never covers the clip's subject or the play control,
 * and it does not intercept the snap-scroll gesture. The detail lives in a
 * bottom sheet that opens on an explicit tap.
 *
 * **Nothing is re-fetched.** The linked listings are already in the feed payload
 * (M17-P03 validated them server-side as belonging to the clip's vendor), so
 * opening the sheet costs zero requests — which is what keeps M17-P04's ≤150 KB
 * route and ≤5 MB session budgets intact.
 *
 * Opening and closing the sheet changes neither the scroll position nor what is
 * playing: this component owns only its own `open` state, and the feed container
 * continues to own playback.
 */
export function ClipOverlay({ clip, locale }: { clip: Clip; locale: string }) {
  const t = useTranslations("clips");
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  if (clip.listings.length === 0) {
    return null;
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-expanded={open}
        data-testid="clip-shop-trigger"
        className="tap inline-flex min-h-11 items-center gap-2 rounded-full bg-surface/90 px-4 py-2 text-sm font-medium text-text focus-visible:outline-none focus-visible:shadow-focusRing"
      >
        {t("overlay.shopThisClip")}
        <span className="rounded-full bg-primary px-2 py-0.5 text-xs text-surface">
          {clip.listings.length}
        </span>
      </button>

      <ProductSheet
        clipId={clip.id}
        listings={clip.listings}
        locale={locale}
        open={open}
        onClose={() => setOpen(false)}
        triggerRef={triggerRef}
      />
    </>
  );
}
