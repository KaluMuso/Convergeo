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
    // Raw access must NOT fall back to English — legal is still absent for bem.
    expect(await loadRawNamespace("bem", "legal")).toBeNull();
  });

  it("returns bem catalog overlay without English merge (Phase-1 file exists)", async () => {
    const raw = await loadRawNamespace("bem", "catalog");
    expect(raw).not.toBeNull();
    expect(raw).toHaveProperty("home");
  });

  it("returns bem events overlay after CCP-03e (no English merge at raw layer)", async () => {
    const raw = await loadRawNamespace("bem", "events");
    expect(raw).not.toBeNull();
    expect(raw).toHaveProperty("ticketPurchase");
  });

  it("returns bem/nya vendor overlays with EN key parity (CCP-03f)", async () => {
    const enKeys = await localeNamespaceKeys("en", "vendor");
    const bemVendor = await localeNamespaceKeys("bem", "vendor");
    const nyaVendor = await localeNamespaceKeys("nya", "vendor");
    expect(bemVendor).toEqual(enKeys);
    expect(nyaVendor).toEqual(enKeys);
  });
});

describe("localeNamespaceKeys", () => {
  it("lists the flat keys a locale defines, or [] when absent", async () => {
    const enKeys = await localeNamespaceKeys("en", "events");
    expect(enKeys).toContain("ticketPurchase.earlyBird");
    const bemEvents = await localeNamespaceKeys("bem", "events");
    expect(bemEvents).toContain("ticketPurchase.earlyBird");
    expect(bemEvents).toEqual(enKeys);
    expect(await localeNamespaceKeys("bem", "legal")).toEqual([]);
    const bemCatalog = await localeNamespaceKeys("bem", "catalog");
    expect(bemCatalog).toContain("home.hero.escrowStep1");
  });
});
