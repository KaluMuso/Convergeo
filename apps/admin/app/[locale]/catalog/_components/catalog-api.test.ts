import { describe, expect, it, vi } from "vitest";

vi.mock("@vergeo/auth", () => ({ getBrowserAccessToken: () => "token" }));

import { actionsFor, canAccessTab, catalogPath, type CatalogEntity } from "./catalog-api";

const entity = (overrides: Partial<CatalogEntity>): CatalogEntity => ({
  kind: "listing",
  id: "id-1",
  label: "Phone",
  status: "active",
  vendor_id: "v1",
  visible: true,
  href: "/l/id-1",
  hold: null,
  ...overrides,
});

const hold = (action: "hide" | "block") => ({
  id: "h1",
  action,
  from_status: "active",
  reason: "Counterfeit",
  actor: null,
  created_at: null,
});

describe("catalog control actions", () => {
  it("offers hide/block for a live listing, restore once held", () => {
    expect(actionsFor("listings", entity({}))).toEqual(["hide", "block", "edit"]);
    expect(actionsFor("listings", entity({ status: "paused", hold: hold("hide") }))).toEqual([
      "restore",
      "block",
      "edit",
    ]);
    expect(actionsFor("listings", entity({ status: "removed", hold: hold("block") }))).toEqual([
      "restore",
      "edit",
    ]);
  });

  it("never offers hide for vendors and allows reinstating a suspension", () => {
    expect(actionsFor("vendors", entity({ kind: "vendor" }))).toEqual(["block", "edit"]);
    expect(actionsFor("vendors", entity({ kind: "vendor", status: "suspended" }))).toEqual([
      "restore",
      "edit",
    ]);
  });

  it("only hides published events and never acts on cancelled ones", () => {
    expect(actionsFor("events", entity({ kind: "event", status: "published" }))).toEqual([
      "hide",
      "block",
      "edit",
    ]);
    expect(actionsFor("events", entity({ kind: "event", status: "cancelled" }))).toEqual(["edit"]);
  });
});

describe("tab permissions mirror the API inventory", () => {
  const grants = (permissions: string[], unrestricted = false) => ({ permissions, unrestricted });

  it("fails closed without grants", () => {
    expect(canAccessTab("listings", null, "read")).toBe(false);
  });

  it("scopes each tab to its permission; services stay read-only for operators", () => {
    expect(canAccessTab("listings", grants(["products.manage"]), "write")).toBe(true);
    expect(canAccessTab("vendors", grants(["products.manage"]), "read")).toBe(false);
    expect(canAccessTab("services", grants(["services.read"]), "read")).toBe(true);
    expect(canAccessTab("services", grants(["services.read"]), "write")).toBe(false);
    expect(canAccessTab("services", grants([], true), "write")).toBe(true);
  });

  it("builds list paths", () => {
    expect(catalogPath("events", "  gig ", true)).toBe(
      "/admin/catalog/events?q=gig&held_only=true",
    );
    expect(catalogPath("vendors", "", false)).toBe("/admin/catalog/vendors");
  });
});
