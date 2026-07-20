"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { addCartItem, openMiniCart, setLastAddedMessage } from "../cart/mini-cart-drawer";

import {
  clampQuantity,
  getMaxQuantity,
  getStockLabel,
  type BuyBoxLabels,
  type BuyBoxListing,
} from "./buy-box";

export type ListingPurchaseControls = {
  quantity: number;
  decrease: () => void;
  increase: () => void;
  atMin: boolean;
  atMax: boolean;
  adding: boolean;
  addError: string | null;
  addedMessage: string | null;
  handleAddToCart: () => void;
  stockLabel: string;
  maxQuantity: number | null;
};

/**
 * Shared qty + add-to-cart state for the PDP buy box and sticky mobile ATC.
 */
export function useListingPurchase(
  listing: BuyBoxListing | null,
  labels: BuyBoxLabels,
): ListingPurchaseControls | null {
  const t = useTranslations("catalog");
  const listingId = listing?.id ?? null;
  const listingMoq = listing?.moq ?? 1;

  const [quantity, setQuantity] = useState(() =>
    listing ? clampQuantity(listing.moq, listing) : 1,
  );
  const [adding, setAdding] = useState(false);
  const [addedMessage, setAddedMessage] = useState<string | null>(null);
  const [addError, setAddError] = useState<string | null>(null);

  const listingStockMode = listing?.stockMode;
  const listingStockQty = listing?.stockQty;
  const listingInStock = listing?.inStock;

  useEffect(() => {
    if (!listing) {
      return;
    }
    // Intentional identity deps (id / stock bounds) — avoid resetting on new object identity each render.
    setQuantity(clampQuantity(listing.moq, listing));
    setAddError(null);
    setAddedMessage(null);
  }, [listing, listingId, listingMoq, listingStockMode, listingStockQty, listingInStock]);

  const maxQuantity = useMemo(() => (listing ? getMaxQuantity(listing) : null), [listing]);

  const stockLabel = useMemo(() => {
    if (!listing) {
      return "";
    }
    return getStockLabel(listing, {
      ...labels,
      lowStockLabel: (count) => t("pdp.buyBox.lowStock", { count }),
    });
  }, [listing, labels, t]);

  const decrease = useCallback(() => {
    if (!listing) {
      return;
    }
    setQuantity((current) => clampQuantity(current - 1, listing));
  }, [listing]);

  const increase = useCallback(() => {
    if (!listing) {
      return;
    }
    setQuantity((current) => clampQuantity(current + 1, listing));
  }, [listing]);

  const handleAddToCart = useCallback(() => {
    if (!listing || !listing.inStock || adding) {
      return;
    }

    setAdding(true);
    setAddError(null);
    setAddedMessage(null);

    void addCartItem(listing.id, quantity)
      .then(() => {
        setAddedMessage(labels.addToCartLabel);
        setLastAddedMessage(labels.addToCartLabel);
        openMiniCart();
      })
      .catch(() => {
        setAddError(labels.addToCartErrorLabel);
      })
      .finally(() => {
        setAdding(false);
      });
  }, [adding, labels.addToCartErrorLabel, labels.addToCartLabel, listing, quantity]);

  if (!listing) {
    return null;
  }

  const atMin = quantity <= Math.max(1, listing.moq);
  const atMax = maxQuantity !== null && quantity >= maxQuantity;

  return {
    quantity,
    decrease,
    increase,
    atMin,
    atMax,
    adding,
    addError,
    addedMessage,
    handleAddToCart,
    stockLabel,
    maxQuantity,
  };
}
