// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./pickup-locations", () => ({
  fetchPickupLocations: vi.fn(),
}));

import { fetchPickupLocations } from "./pickup-locations";
import { usePickupLocationSelection } from "./use-pickup-location-selection";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("usePickupLocationSelection", () => {
  it("starts unknown (null) and never null-as-not-required", () => {
    vi.mocked(fetchPickupLocations).mockReturnValue(new Promise(() => {})); // never resolves
    const { result } = renderHook(() => usePickupLocationSelection("listing-1"));
    expect(result.current.branchTracked).toBeNull();
    expect(result.current.loading).toBe(true);
  });

  it("resolves branchTracked=false and an empty list for a legacy pooled listing", async () => {
    vi.mocked(fetchPickupLocations).mockResolvedValue({ branchTracked: false, locations: [] });
    const { result } = renderHook(() => usePickupLocationSelection("listing-legacy"));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.branchTracked).toBe(false);
    expect(result.current.locations).toEqual([]);
  });

  it("resolves branchTracked=true with the active branches for a tracked listing", async () => {
    vi.mocked(fetchPickupLocations).mockResolvedValue({
      branchTracked: true,
      locations: [{ id: "branch-1", landmark: "East Park Mall", lat: -15.4, lng: 28.3 }],
    });
    const { result } = renderHook(() => usePickupLocationSelection("listing-tracked"));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.branchTracked).toBe(true);
    expect(result.current.locations).toHaveLength(1);
  });

  it("fails closed on a fetch error — branchTracked stays null, never false", async () => {
    vi.mocked(fetchPickupLocations).mockRejectedValue(new Error("network error"));
    const { result } = renderHook(() => usePickupLocationSelection("listing-1"));

    await waitFor(() => expect(result.current.loadError).toBe(true));
    expect(result.current.branchTracked).toBeNull();
    expect(result.current.locations).toEqual([]);
  });

  it("never auto-selects — selectedLocationId stays null until selectLocation is called", async () => {
    vi.mocked(fetchPickupLocations).mockResolvedValue({
      branchTracked: true,
      locations: [{ id: "branch-1", landmark: "East Park Mall", lat: -15.4, lng: 28.3 }],
    });
    const { result } = renderHook(() => usePickupLocationSelection("listing-1"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.selectedLocationId).toBeNull();

    act(() => {
      result.current.selectLocation("branch-1");
    });
    await waitFor(() => expect(result.current.selectedLocationId).toBe("branch-1"));
  });

  it("resets selection and status when the listing id changes", async () => {
    vi.mocked(fetchPickupLocations).mockResolvedValue({
      branchTracked: true,
      locations: [{ id: "branch-1", landmark: "East Park Mall", lat: -15.4, lng: 28.3 }],
    });
    const { result, rerender } = renderHook(
      ({ listingId }: { listingId: string | null }) => usePickupLocationSelection(listingId),
      { initialProps: { listingId: "listing-1" } },
    );
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.selectLocation("branch-1"));
    await waitFor(() => expect(result.current.selectedLocationId).toBe("branch-1"));

    vi.mocked(fetchPickupLocations).mockResolvedValue({ branchTracked: false, locations: [] });
    rerender({ listingId: "listing-2" });

    await waitFor(() => expect(result.current.branchTracked).toBe(false));
    expect(result.current.selectedLocationId).toBeNull();
  });

  it("returns a stable not-required state for a null listingId without fetching", () => {
    const { result } = renderHook(() => usePickupLocationSelection(null));
    expect(fetchPickupLocations).not.toHaveBeenCalled();
    expect(result.current.branchTracked).toBeNull();
    expect(result.current.loading).toBe(false);
  });
});
