"use client";

import { formatK } from "@vergeo/i18n";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { addCartItem } from "../../../(shop)/_components/cart/mini-cart-drawer";

import type { ClipListing } from "../types";

/**
 * M17-P05 — the accessible product sheet.
 *
 * Accessibility here is not decoration: this sheet opens over a scroll container
 * that owns snap behaviour and a video element, so getting focus wrong means a
 * keyboard user lands somewhere behind the sheet with no way back.
 *
 * * `role="dialog"` + `aria-modal` so assistive tech announces it as a layer;
 * * focus moves into the sheet on open and **returns to the trigger** on close;
 * * focus is trapped **while open**, with `Escape` and the close button as the
 *   documented escape paths — a trap with no exit is worse than no trap;
 * * every control is ≥44px, because this is a one-handed surface on a phone.
 *
 * Add-to-cart calls the **existing** cart function. There is exactly one cart in
 * this product; a clip-specific one would diverge on stock, pricing and merge
 * rules within a week.
 */
export function ProductSheet({
  clipId,
  listings,
  locale,
  open,
  onClose,
  triggerRef,
}: {
  clipId: string;
  listings: ClipListing[];
  locale: string;
  open: boolean;
  onClose: () => void;
  triggerRef: React.RefObject<HTMLButtonElement | null>;
}) {
  const t = useTranslations("clips");
  const sheetRef = useRef<HTMLDivElement | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [addedId, setAddedId] = useState<string | null>(null);
  const [failedId, setFailedId] = useState<string | null>(null);

  // Focus in on open, back to the trigger on close.
  useEffect(() => {
    if (!open) {
      return;
    }
    const previous = document.activeElement as HTMLElement | null;
    sheetRef.current?.focus();
    return () => {
      (triggerRef.current ?? previous)?.focus?.();
    };
  }, [open, triggerRef]);

  // Escape closes; Tab cycles inside. Both are required for the trap to be safe.
  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const focusable = sheetRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable || focusable.length === 0) {
        return;
      }
      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [open, onClose]);

  const onAdd = useCallback(
    async (listingId: string) => {
      setBusyId(listingId);
      setFailedId(null);
      try {
        // The existing cart call, plus the clip that led here. The server decides
        // whether that clip actually earns the attribution.
        await addCartItem(listingId, 1, clipId);
        setAddedId(listingId);
      } catch {
        setFailedId(listingId);
      } finally {
        setBusyId(null);
      }
    },
    [clipId],
  );

  if (!open) {
    return null;
  }

  return (
    <div
      ref={sheetRef}
      role="dialog"
      aria-modal="true"
      aria-label={t("a11y.productsLabel")}
      tabIndex={-1}
      data-testid="clip-product-sheet"
      className="fixed inset-x-0 bottom-0 z-40 max-h-[70vh] overflow-y-auto rounded-t-3 border-t border-border bg-surface p-4 pb-8 shadow-2 focus-visible:outline-none"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-h3 font-semibold text-text">{t("overlay.title")}</h2>
        <button
          type="button"
          onClick={onClose}
          data-testid="clip-sheet-close"
          className="tap min-h-11 min-w-11 rounded-full border border-border px-3 text-sm text-text focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          {t("overlay.close")}
        </button>
      </div>

      {listings.length === 0 ? (
        <p className="mt-4 text-sm text-muted">{t("overlay.empty")}</p>
      ) : (
        <ul className="mt-4 flex flex-col gap-3">
          {listings.map((listing) => (
            <li
              key={listing.listing_id}
              data-testid="clip-sheet-listing"
              data-listing-id={listing.listing_id}
              className="flex flex-col gap-2 rounded-2 border border-border p-3"
            >
              {/* Listing titles are vendor text — rendered as a text node. */}
              <p className="text-sm font-medium text-text" data-testid="clip-listing-title">
                {listing.title ?? ""}
              </p>
              {/* Integer ngwee through the shared formatter — never local maths. */}
              <p className="text-sm text-price" data-testid="clip-listing-price">
                {formatK(listing.price_ngwee, { locale })}
              </p>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={busyId === listing.listing_id}
                  onClick={() => void onAdd(listing.listing_id)}
                  data-testid="clip-add-to-cart"
                  className="tap min-h-11 rounded-full bg-primary px-4 py-2 text-sm font-medium text-surface disabled:opacity-50"
                >
                  {busyId === listing.listing_id
                    ? t("overlay.adding")
                    : addedId === listing.listing_id
                      ? t("overlay.added")
                      : t("overlay.addToCart")}
                </button>

                {/* The no-JS / degraded path: a plain link to the PDP. It is a
                    real anchor, so it works before hydration and after a JS
                    failure — the commerce path is never JS-exclusive. */}
                <Link
                  href={`/${locale}/l/${listing.listing_id}`}
                  data-testid="clip-listing-link"
                  className="tap min-h-11 rounded-full border border-border px-4 py-2 text-sm text-text"
                >
                  {t("overlay.viewProduct")}
                </Link>
              </div>

              {failedId === listing.listing_id ? (
                <p role="alert" data-testid="clip-add-failed" className="text-sm text-danger">
                  {t("overlay.failed")}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
