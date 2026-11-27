// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadMenuTree, MENU_TREE_TTL_MS, resetMenuTreeCacheForTests } from "./use-menu-tree";

const requestMock = vi.hoisted(() => vi.fn());
vi.mock("@vergeo/config", () => ({
  createApiClient: () => ({ request: requestMock }),
}));
vi.mock("../../../../../lib/api-base-url", () => ({ getApiBaseUrl: () => "https://api.test" }));

const rows = [
  { id: "1", name: "Fashion", slug: "fashion", position: 1, parent_id: null, prohibited: false },
  { id: "2", name: "Men", slug: "men", position: 1, parent_id: "1", prohibited: false },
];

beforeEach(() => {
  resetMenuTreeCacheForTests();
  requestMock.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("loadMenuTree", () => {
  it("builds the tree from GET /categories and caches it (one request for repeated opens)", async () => {
    requestMock.mockResolvedValue(rows);
    const first = await loadMenuTree({});
    const second = await loadMenuTree({});
    expect(first[0]).toMatchObject({ slug: "fashion", children: [{ slug: "men" }] });
    expect(second).toEqual(first);
    expect(requestMock).toHaveBeenCalledTimes(1);
    expect(requestMock).toHaveBeenCalledWith("/categories");
  });

  it("serves the stale tree immediately after the TTL and refreshes in the background", async () => {
    requestMock.mockResolvedValue(rows);
    await loadMenuTree({});
    requestMock.mockResolvedValue([{ ...rows[0], name: "Fashion & fabric" }, rows[1]]);
    const stale = await loadMenuTree({}, Date.now() + MENU_TREE_TTL_MS + 1);
    expect(stale[0]?.name).toBe("Fashion");
    expect(requestMock).toHaveBeenCalledTimes(2);
    await vi.waitFor(async () => {
      const fresh = await loadMenuTree({}, Date.now());
      expect(fresh[0]?.name).toBe("Fashion & fabric");
    });
  });

  it("falls back to static department roots on API failure and does not cache the fallback", async () => {
    requestMock.mockRejectedValue(new Error("boom"));
    const fallback = await loadMenuTree({ fashion: "Fashion & fabric" });
    expect(fallback.map((root) => root.slug)).toContain("fashion");
    expect(fallback.find((root) => root.slug === "fashion")?.name).toBe("Fashion & fabric");

    requestMock.mockResolvedValue(rows);
    const recovered = await loadMenuTree({});
    expect(recovered[0]?.children).toHaveLength(1);
  });
});
