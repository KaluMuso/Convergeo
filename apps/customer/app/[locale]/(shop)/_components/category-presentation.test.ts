import { afterEach, describe, expect, it, vi } from "vitest";

import {
  fetchCategoryPresentations,
  parseCategoryPresentations,
  resolveCategoryBanner,
  type CategoryPresentation,
} from "./category-presentation";

vi.mock("../../../../lib/api-base-url", () => ({
  absoluteApiUrl: (path: string) => `https://api.example.test${path}`,
}));

const groceries: CategoryPresentation = {
  category_id: "c1",
  slug: "groceries-staples",
  icon_public_id: "categories/icons/rice",
  banner_public_id: "categories/banners/rice",
  banner_title_i18n: { en: "Staples for less", bem: "Ifya kulya" },
  banner_description_i18n: { en: "Mealie meal, rice and oil." },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("parseCategoryPresentations", () => {
  it("keeps well-formed rows and drops unsafe public ids", () => {
    const rows = parseCategoryPresentations([
      { ...groceries, icon_public_id: "../etc/passwd" },
      { slug: "no-id" },
      "junk",
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0]?.icon_public_id).toBeNull();
    expect(rows[0]?.banner_public_id).toBe("categories/banners/rice");
  });

  it("returns an empty list for non-arrays", () => {
    expect(parseCategoryPresentations({ error: "x" })).toEqual([]);
  });
});

describe("resolveCategoryBanner", () => {
  it("uses the visitor's locale when the admin wrote one", () => {
    expect(resolveCategoryBanner(groceries, "bem")).toEqual({
      imagePublicId: "categories/banners/rice",
      title: "Ifya kulya",
      description: "Mealie meal, rice and oil.",
    });
  });

  it("falls back to English copy", () => {
    expect(resolveCategoryBanner(groceries, "fr")?.title).toBe("Staples for less");
  });

  it("returns null when there is neither an image nor a title", () => {
    expect(
      resolveCategoryBanner(
        {
          ...groceries,
          banner_public_id: null,
          banner_title_i18n: {},
          banner_description_i18n: {},
        },
        "en",
      ),
    ).toBeNull();
    expect(resolveCategoryBanner(undefined, "en")).toBeNull();
  });
});

describe("fetchCategoryPresentations", () => {
  it("maps rows by slug with a cache tag", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify([groceries]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const map = await fetchCategoryPresentations();
    expect(map.get("groceries-staples")?.icon_public_id).toBe("categories/icons/rice");
    const init = fetchMock.mock.calls[0]?.[1] as { next?: { tags?: string[] } };
    expect(init.next?.tags).toContain("category-presentation");
  });

  it("degrades to an empty map when the API fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    expect((await fetchCategoryPresentations()).size).toBe(0);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 500 })));
    expect((await fetchCategoryPresentations()).size).toBe(0);
  });
});
