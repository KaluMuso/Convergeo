import { describe, expect, it } from "vitest";

import { buildMenuModel, tileInitial, tileTint } from "./nav-model";
import { TEST_LABELS, TEST_TREE } from "./test-fixtures";

describe("nav model", () => {
  it("builds product, service and event departments with locale-prefixed hrefs", () => {
    const model = buildMenuModel(TEST_TREE, TEST_LABELS, "fr");
    expect(model.products[0]).toMatchObject({
      group: "products",
      href: "/fr/c/dept-1",
      children: [{ href: "/fr/c/dept-1-phones" }, { href: "/fr/c/dept-1-laptops" }],
    });
    expect(model.services.group).toBe("services");
    expect(model.services.children).toHaveLength(8);
    expect(model.services.children[0]?.href).toBe("/fr/services?category=beauty");
    expect(model.events.children[0]?.href).toBe("/fr/events?category=workshops");
  });

  it("derives a stable token tint and an uppercase initial for placeholder tiles", () => {
    expect(tileTint("phones")).toBe(tileTint("phones"));
    expect(tileTint("phones")).toMatch(/^var\(--cat-/);
    expect(tileInitial("  électronique")).toBe("É");
    expect(tileInitial("")).toBe("•");
  });
});
