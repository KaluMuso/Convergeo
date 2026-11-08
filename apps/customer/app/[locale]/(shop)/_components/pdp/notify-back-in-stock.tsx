"use client";

import { emitToastKey } from "@vergeo/ui/src/toast";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { subscribeBackInStock } from "../../../../../lib/engagement-api";

type NotifyBackInStockProps = {
  listingId: string;
  locale: string;
  similarHref: string;
};

/**
 * Out-of-stock replacement for Add to cart (Amazon "Currently unavailable",
 * Takealot "Notify me"): a secondary alert CTA plus a route to similar items.
 */
export function NotifyBackInStock({
  listingId,
  locale,
  similarHref,
}: NotifyBackInStockProps) {
  const t = useTranslations("catalog.backInStock");
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");

  const onClick = async () => {
    setState("busy");
    const result = await subscribeBackInStock(listingId);
    if (result === "signed_out") {
      setState("idle");
      window.location.assign(
        `/${locale}/login?next=${encodeURIComponent(window.location.pathname)}`,
      );
      return;
    }
    if (result === "error") {
      setState("idle");
      emitToastKey("actionFailed", { type: "error" });
      return;
    }
    setState("done");
  };

  return (
    <div className="flex flex-col gap-2" data-testid="pdp-out-of-stock">
      <p className="m-0 font-display text-lg font-bold text-discount">
        {t("unavailable")}
      </p>
      {state === "done" ? (
        <p
          role="status"
          className="m-0 rounded bg-primary-tint px-3 py-2.5 text-sm font-medium text-primary-deep"
        >
          {t("subscribed")}
        </p>
      ) : (
        <button
          type="button"
          onClick={() => void onClick()}
          disabled={state === "busy"}
          data-testid="pdp-notify-me"
          className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded border border-primary bg-surface px-4 text-body font-semibold text-primary transition-colors hover:bg-primary-tint focus-visible:outline-none focus-visible:shadow-focusRing disabled:opacity-60"
        >
          <svg
            aria-hidden
            viewBox="0 0 24 24"
            className="h-5 w-5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.9"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15L6 16ZM10 20a2 2 0 0 0 4 0" />
          </svg>
          {t("notifyMe")}
        </button>
      )}
      <a
        href={similarHref}
        className="inline-flex min-h-11 items-center text-sm font-semibold text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:shadow-focusRing"
      >
        {t("seeSimilar")}
      </a>
    </div>
  );
}
