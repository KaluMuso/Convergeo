import { afterEach, describe, expect, it, vi } from "vitest";

import { mapResolvedMerchSlot } from "./merch-data";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchMerchSlotsFromApi", () => {
  it("maps resolved API slots and passes preview token in the query", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.example.test");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        {
          id: "slot-1",
          slot_key: "hero",
          variant_key: "editorial-light",
          payload: { title_key: "home.hero.title" },
          schedule_from: null,
          schedule_to: null,
          position: 0,
          active: true,
          is_preview: true,
        },
      ],
    });
    vi.stubGlobal("fetch", fetchMock);

    const { fetchMerchSlotsFromApi } = await import("./merch-data");
    const slots = await fetchMerchSlotsFromApi("draft");

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/merch/slots?merch_preview=draft",
      expect.objectContaining({ next: { revalidate: 0 } }),
    );
    expect(slots).toHaveLength(1);
    expect(slots[0]?.slot_key).toBe("hero");
    expect(slots[0]?.payload.title_key).toBe("home.hero.title");
  });
});

describe("mapResolvedMerchSlot", () => {
  it("normalizes malformed payloads to an empty object", () => {
    const row = mapResolvedMerchSlot({
      id: "x",
      slot_key: "banner_row",
      variant_key: "default",
      payload: null as unknown as Record<string, unknown>,
      schedule_from: null,
      schedule_to: null,
      position: 1,
      active: true,
    });

    expect(row.payload).toEqual({});
  });
});
