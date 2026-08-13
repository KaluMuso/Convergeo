"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { addCartItem, openMiniCart, setLastAddedMessage } from "../cart/mini-cart-drawer";
import { formatListingQuantity, resolveSaleUnit, type SaleUnitLabels } from "../sale-quantity";

import {
  clampQuantity,
  getMaxQuantity,
  getMinimumQuantity,
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
  locale = "en",
): ListingPurchaseControls | null {
  const t = useTranslations("catalog");
  const listingId = listing?.id ?? null;
  const listingMoq = listing?.moq ?? 1;
  const listingMinSteps = listing?.minSteps ?? 1;

  const [quantity, setQuantity] = useState(() =>
    listing ? clampQuantity(getMinimumQuantity(listing), listing) : 1,
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
    setQuantity(clampQuantity(getMinimumQuantity(listing), listing));
    setAddError(null);
    setAddedMessage(null);
  }, [
    listing,
    listingId,
    listingMoq,
    listingMinSteps,
    listingStockMode,
    listingStockQty,
    listingInStock,
  ]);

  const maxQuantity = useMemo(() => (listing ? getMaxQuantity(listing) : null), [listing]);
  const unitLabels: SaleUnitLabels = useMemo(
    () => ({
      each: t("pdp.buyBox.units.each"),
      metre: t("pdp.buyBox.units.metre"),
      kg: t("pdp.buyBox.units.kg"),
      litre: t("pdp.buyBox.units.litre"),
      bag: t("pdp.buyBox.units.bag"),
      sqm: t("pdp.buyBox.units.sqm"),
    }),
    [t],
  );

  const stockLabel = useMemo(() => {
    if (!listing) {
      return "";
    }
    return getStockLabel(listing, {
      ...labels,
      lowStockLabel: (count) =>
        resolveSaleUnit(listing.saleUnit) === "each"
          ? t("pdp.buyBox.lowStock", { count })
          : t("pdp.buyBox.lowStockQuantity", {
              quantity: formatListingQuantity(
                count,
                listing.saleUnit,
                listing.unitStepMilli,
                locale,
                unitLabels,
              ),
            }),
    });
  }, [listing, labels, locale, t, unitLabels]);

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

  const atMin = quantity <= getMinimumQuantity(listing);
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
