"use client";

import { useCallback, useEffect, useState } from "react";

import { fetchPickupLocations, type PickupLocation } from "./pickup-locations";

export type PickupLocationSelection = {
  /**
   * true/false once known; null while loading or after a failed fetch — the
   * caller must never treat null as "no branch needed". Add to Cart is only
   * safe to enable when `branchTracked === false` (no selection required) or
   * `branchTracked === true && selectedLocationId` is set — never on null.
   */
  branchTracked: boolean | null;
  locations: PickupLocation[];
  loading: boolean;
  loadError: boolean;
  selectedLocationId: string | null;
  selectLocation: (locationId: string) => void;
};

/**
 * Shared by the PDP buy box (via useListingPurchase) and the standalone-
 * listing buy box (BuyBox's own internal fallback state) so both real
 * add-to-cart surfaces enforce the same required-branch-selection contract
 * instead of duplicating the fetch/fail-closed logic.
 */
export function usePickupLocationSelection(listingId: string | null): PickupLocationSelection {
  const [branchTracked, setBranchTracked] = useState<boolean | null>(null);
  const [locations, setLocations] = useState<PickupLocation[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null);

  useEffect(() => {
    setSelectedLocationId(null);
    setBranchTracked(null);
    setLocations([]);
    setLoadError(false);
    setLoading(false);

    if (!listingId) {
      return;
    }

    let cancelled = false;
    setLoading(true);

    fetchPickupLocations(listingId)
      .then((result) => {
        if (cancelled) {
          return;
        }
        setBranchTracked(result.branchTracked);
        setLocations(result.locations);
      })
      .catch(() => {
        if (cancelled) {
          return;
        }
        // branchTracked stays null (unknown) — the caller's gate treats that
        // as "cannot add yet", never as "no branch needed".
        setLoadError(true);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [listingId]);

  const selectLocation = useCallback((locationId: string) => {
    setSelectedLocationId(locationId);
  }, []);

  return { branchTracked, locations, loading, loadError, selectedLocationId, selectLocation };
}
