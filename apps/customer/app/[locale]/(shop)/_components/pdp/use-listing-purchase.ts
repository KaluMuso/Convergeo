"use client";

import { ApiError } from "@vergeo/config";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { catalogSaleUnitLabels, formatListingQuantity, resolveSaleUnit } from "../sale-quantity";

import {
  clampQuantity,
  getMaxQuantity,
  getMinimumQuantity,
  getStockLabel,
  type BuyBoxLabels,
  type BuyBoxListing,
} from "./buy-box";
import { usePickupLocationSelection } from "./use-pickup-location-selection";

import type { PickupLocation } from "./pickup-locations";

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
  /** null while unknown (loading/error) — the picker/gate must never treat null as "not required". */
  pickupBranchTracked: boolean | null;
  pickupLocations: PickupLocation[];
  pickupLocationsLoading: boolean;
  pickupLocationsLoadError: boolean;
  selectedPickupLocationId: string | null;
  selectPickupLocation: (locationId: string) => void;
  /** False while the listing has options and the buyer hasn't completed them. */
  variantSatisfied: boolean;
  /** True after an add-to-cart was blocked for missing options (highlight them). */
  showMissingOptions: boolean;
};

/** API variant refusals that deserve a specific message instead of the generic one. */
const VARIANT_ERROR_KEYS: Record<string, string> = {
  "cart.variant_out_of_stock": "pdp.variants.errors.outOfStock",
  "cart.variant_unavailable": "pdp.variants.errors.unavailable",
  "cart.variant_invalid": "pdp.variants.errors.unavailable",
  "cart.variant_conflict": "pdp.variants.errors.conflict",
};

export type ListingPurchaseVariant = {
  /** Listing has option groups — a complete choice is needed to buy. */
  required: boolean;
  /** Resolved variant for the current picks, or null while incomplete. */
  variantId: string | null;
  /** Message shown when add-to-cart is blocked for missing options. */
  missingLabel: string;
};

/**
 * Shared qty + add-to-cart state for the PDP buy box and sticky mobile ATC.
 */
export function useListingPurchase(
  listing: BuyBoxListing | null,
  labels: BuyBoxLabels,
  locale = "en",
  variant?: ListingPurchaseVariant,
): ListingPurchaseControls | null {
  const t = useTranslations("catalog");
  const listingId = listing?.id ?? null;
  const listingMoq = listing?.moq ?? 1;
  const listingMinSteps = listing?.minSteps ?? 1;

  const [quantity, setQuantity] = useState(() =>
    listing ? clampQuantity(getMinimumQuantity(listing), listing) : 1,
  );
  const [adding, setAdding] = useState(false);
  const addingRef = useRef(false);
  const [addedMessage, setAddedMessage] = useState<string | null>(null);
  const [addError, setAddError] = useState<string | null>(null);
  const [showMissingOptions, setShowMissingOptions] = useState(false);
  const variantRequired = variant?.required ?? false;
  const variantId = variant?.variantId ?? null;
  const variantMissingLabel = variant?.missingLabel ?? "";
  const variantSatisfied = !variantRequired || variantId !== null;
  const pickup = usePickupLocationSelection(listingId);

  const listingStockMode = listing?.stockMode;
  const listingStockQty = listing?.stockQty;
  const listingInStock = listing?.inStock;

  useEffect(() => {
    if (!listing) {
      return;
    }
    // Stock bounds or a refreshed listing object only re-clamp the quantity;
    // the add-to-cart outcome stays visible (e.g. after a cart add refreshes stock).
    setQuantity(clampQuantity(getMinimumQuantity(listing), listing));
  }, [
    listing,
    listingId,
    listingMoq,
    listingMinSteps,
    listingStockMode,
    listingStockQty,
    listingInStock,
  ]);

  useEffect(() => {
    // A different listing starts with a clean purchase state.
    setAddError(null);
    setAddedMessage(null);
    setShowMissingOptions(false);
  }, [listingId]);

  const maxQuantity = useMemo(() => (listing ? getMaxQuantity(listing) : null), [listing]);
  const unitLabels = useMemo(() => catalogSaleUnitLabels(t), [t]);

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
    if (!listing || adding || addingRef.current) {
      return;
    }
    // Options first: a buyer must be told what to pick even when the listing
    // as a whole reads out of stock for their current partial choice.
    if (!variantSatisfied) {
      setAddError(variantMissingLabel);
      setShowMissingOptions(true);
      return;
    }
    if (!listing.inStock) {
      return;
    }
    // Fail closed: never send add-to-cart while branch-tracking status is
    // unknown (loading/error) or known-tracked with no branch chosen yet —
    // the server would reject it as cart.pickup_location_required anyway,
    // but this never silently omits pickup_location_id for a real user click.
    if (pickup.branchTracked !== false && !pickup.selectedLocationId) {
      setAddError(t("pdp.buyBox.pickup.required"));
      return;
    }

    addingRef.current = true;
    setAdding(true);
    setAddError(null);
    setAddedMessage(null);

    void (async () => {
      const { addCartItem, openMiniCart, setLastAddedMessage } =
        await import("../cart/mini-cart-drawer");
      await addCartItem(
        listing.id,
        quantity,
        undefined,
        pickup.selectedLocationId || variantId
          ? {
              ...(pickup.selectedLocationId
                ? { pickupLocationId: pickup.selectedLocationId, fulfilment: "pickup" as const }
                : {}),
              ...(variantId ? { listingVariantId: variantId } : {}),
            }
          : undefined,
      );
      setAddedMessage(labels.addToCartLabel);
      setLastAddedMessage(labels.addToCartLabel);
      openMiniCart();
    })()
      .catch((error: unknown) => {
        const variantErrorKey =
          error instanceof ApiError ? VARIANT_ERROR_KEYS[error.code] : undefined;
        setAddError(variantErrorKey ? t(variantErrorKey) : labels.addToCartErrorLabel);
      })
      .finally(() => {
        addingRef.current = false;
        setAdding(false);
      });
  }, [
    adding,
    labels.addToCartErrorLabel,
    labels.addToCartLabel,
    listing,
    pickup.branchTracked,
    pickup.selectedLocationId,
    quantity,
    t,
    variantId,
    variantMissingLabel,
    variantSatisfied,
  ]);

  // Clear the "missing options" highlight once the choice is complete.
  useEffect(() => {
    if (variantSatisfied) {
      setShowMissingOptions(false);
      setAddError((current) => (current === variantMissingLabel ? null : current));
    }
  }, [variantSatisfied, variantMissingLabel]);

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
    pickupBranchTracked: pickup.branchTracked,
    pickupLocations: pickup.locations,
    pickupLocationsLoading: pickup.loading,
    pickupLocationsLoadError: pickup.loadError,
    selectedPickupLocationId: pickup.selectedLocationId,
    selectPickupLocation: pickup.selectLocation,
    maxQuantity,
    variantSatisfied,
    showMissingOptions,
  };
}
