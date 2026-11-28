import { describe, expect, it } from "vitest";

import {
  canManageUmbrella,
  flattenTree,
  movableParents,
  reorderedIds,
  slugify,
  type TaxonomyNode,
} from "./taxonomy-model";

function node(id: string, parent: string | null, sort: number, name = id): TaxonomyNode {
  return {
    id,
    slug: id,
    parent_id: parent,
    name,
    umbrella: "product",
    status: "published",
    sort_order: sort,
    image_public_id: null,
    image_alt: null,
    image_url: null,
    icon: null,
    show_in_customer: true,
    show_in_vendor: true,
    path: id,
    commission_key: null,
    child_count: 0,
  };
}

describe("taxonomy model", () => {
  it("flattens depth-first ordered by sort", () => {
    const rows = flattenTree([node("b", null, 20), node("a", null, 10), node("a1", "a", 5)]);
    expect(rows.map((r) => [r.node.id, r.depth])).toEqual([
      ["a", 0],
      ["a1", 1],
      ["b", 0],
    ]);
  });

  it("treats nodes whose parent is filtered out as roots", () => {
    const rows = flattenTree([node("child", "missing", 1)]);
    expect(rows).toHaveLength(1);
    expect(rows[0]?.depth).toBe(0);
  });

  it("reorders siblings and refuses to move past the ends", () => {
    const siblings = [node("a", null, 1), node("b", null, 2), node("c", null, 3)];
    expect(reorderedIds(siblings, "b", -1)).toEqual(["b", "a", "c"]);
    expect(reorderedIds(siblings, "a", -1)).toBeNull();
    expect(reorderedIds(siblings, "c", 1)).toBeNull();
  });

  it("never offers a node or its descendants as a new parent", () => {
    const all = [node("a", null, 1), node("a1", "a", 1), node("a2", "a1", 1), node("b", null, 2)];
    expect(movableParents(all, "a").map((n) => n.id)).toEqual(["b"]);
  });

  it("mirrors the API permission scoping per umbrella", () => {
    const products = { permissions: ["products.manage"], unrestricted: false };
    const events = { permissions: ["events.manage"], unrestricted: false };
    expect(canManageUmbrella("product", products)).toBe(true);
    expect(canManageUmbrella("wholesale", products)).toBe(true);
    expect(canManageUmbrella("event", products)).toBe(false);
    expect(canManageUmbrella("event", events)).toBe(true);
    expect(canManageUmbrella("service", events)).toBe(false);
    expect(canManageUmbrella("service", { permissions: [], unrestricted: true })).toBe(true);
    expect(canManageUmbrella("product", null)).toBe(false);
  });

  it("slugifies like the API", () => {
    expect(slugify("Logistics & Delivery!")).toBe("logistics-and-delivery");
  });
});
