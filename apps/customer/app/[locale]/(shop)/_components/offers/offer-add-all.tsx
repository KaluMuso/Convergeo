"use client";

import { Button } from "@vergeo/ui/src/button";
import { emitToastKey } from "@vergeo/ui/src/toast";
import { useState } from "react";

export type OfferAddAllLabels = {
  addAll: string;
  adding: string;
  added: string;
  failed: string;
};

type OfferAddAllProps = {
  offerId: string;
  items: Array<{ listingId: string; qty: number }>;
  labels: OfferAddAllLabels;
};

/**
 * Adds every paid item of a bundle to the cart, in order. The discount and the
 * free gift are applied by the server pricing engine — nothing is priced here.
 * The cart module is imported on click so it stays off the PDP page graph.
 */
export function OfferAddAll({ offerId, items, labels }: OfferAddAllProps) {
  const [state, setState] = useState<"idle" | "adding" | "added" | "failed">("idle");

  const onClick = async () => {
    if (state === "adding") {
      return;
    }
    setState("adding");
    try {
      const { addCartItem, openMiniCart, setLastAddedMessage } =
        await import("../cart/mini-cart-drawer");
      for (const item of items) {
        await addCartItem(item.listingId, item.qty);
      }
      setLastAddedMessage(labels.added);
      openMiniCart();
      emitToastKey("addedToCart", { type: "cart" });
      setState("added");
    } catch {
      emitToastKey("addToCartFailed", { type: "error" });
      setState("failed");
    }
  };

  return (
    <div className="flex flex-col gap-1">
      <Button
        type="button"
        variant="primary"
        className="min-h-11 w-full rounded-lg text-sm"
        loading={state === "adding"}
        loadingLabel={labels.adding}
        data-testid={`offer-add-all-${offerId}`}
        onClick={() => void onClick()}
      >
        {labels.addAll}
      </Button>
      <p className="sr-only" aria-live="polite">
        {state === "added" ? labels.added : state === "failed" ? labels.failed : ""}
      </p>
    </div>
  );
}
