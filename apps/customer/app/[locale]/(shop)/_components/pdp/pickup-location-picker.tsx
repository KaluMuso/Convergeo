"use client";

import type { PickupLocation } from "./pickup-locations";

export type PickupLocationPickerLabels = {
  heading: string;
  selectAria: string;
  placeholder: string;
  loading: string;
  loadError: string;
  unavailable: string;
};

export type PickupLocationPickerProps = {
  locations: PickupLocation[];
  loading: boolean;
  loadError: boolean;
  selectedLocationId: string | null;
  onSelect: (locationId: string) => void;
  labels: PickupLocationPickerLabels;
};

/**
 * Explicit branch selection for a branch-tracked listing — never
 * auto-selects. Rendered only when the listing is known branch-tracked
 * (see use-pickup-location-selection.ts); a legacy pooled listing never
 * shows this at all.
 */
export function PickupLocationPicker({
  locations,
  loading,
  loadError,
  selectedLocationId,
  onSelect,
  labels,
}: PickupLocationPickerProps) {
  if (loading) {
    return (
      <p
        className="text-sm text-text-2"
        data-testid="pdp-pickup-location-loading"
        aria-live="polite"
      >
        {labels.loading}
      </p>
    );
  }

  if (loadError) {
    return (
      <p className="text-sm text-danger" role="alert" data-testid="pdp-pickup-location-load-error">
        {labels.loadError}
      </p>
    );
  }

  if (locations.length === 0) {
    return (
      <p className="text-sm text-danger" data-testid="pdp-pickup-location-unavailable">
        {labels.unavailable}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm font-medium text-text" htmlFor="pdp-pickup-location">
        {labels.heading}
      </label>
      <select
        id="pdp-pickup-location"
        data-testid="pdp-pickup-location-select"
        aria-label={labels.selectAria}
        className="min-h-11 rounded border border-border bg-bg px-3 text-sm"
        value={selectedLocationId ?? ""}
        onChange={(event) => onSelect(event.target.value)}
      >
        <option value="" disabled>
          {labels.placeholder}
        </option>
        {locations.map((location) => (
          <option key={location.id} value={location.id}>
            {location.landmark || location.id}
          </option>
        ))}
      </select>
    </div>
  );
}
