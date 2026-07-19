import { describe, expect, it } from "vitest";

import { flattenMessages, loadRawNamespace, localeNamespaceKeys } from "./catalog";

describe("flattenMessages", () => {
  it("flattens nested messages to dotted keys", () => {
    expect(flattenMessages({ a: "1", b: { c: "2", d: { e: "3" } } })).toEqual({
      a: "1",
      "b.c": "2",
      "b.d.e": "3",
    });
  });

  it("returns an empty object for empty input", () => {
    expect(flattenMessages({})).toEqual({});
  });
});

describe("loadRawNamespace", () => {
  it("returns a locale's own messages when the file exists", async () => {
    const raw = await loadRawNamespace("en", "events");
    expect(raw).not.toBeNull();
    expect(typeof raw).toBe("object");
  });

  it("returns null when the locale has no file for the namespace (no fallback)", async () => {
    // Raw access must NOT fall back to English — events is still absent for bem.
    expect(await loadRawNamespace("bem", "events")).toBeNull();
  });

  it("returns bem catalog overlay without English merge (Phase-1 file exists)", async () => {
    const raw = await loadRawNamespace("bem", "catalog");
    expect(raw).not.toBeNull();
    expect(raw).toHaveProperty("home");
  });
});

describe("localeNamespaceKeys", () => {
  it("lists the flat keys a locale defines, or [] when absent", async () => {
    const enKeys = await localeNamespaceKeys("en", "events");
    expect(enKeys).toContain("ticketPurchase.earlyBird");
    expect(await localeNamespaceKeys("bem", "events")).toEqual([]);
    const bemCatalog = await localeNamespaceKeys("bem", "catalog");
    expect(bemCatalog).toContain("home.hero.escrowStep1");
  });
});
