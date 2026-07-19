import { describe, expect, it } from "vitest";

import { searchResultHref } from "./search-result-href";

/**
 * Regression: live search emitted `/en/p/{entity_id}` (UUID) while the PDP
 * looks up `GET /products/{slug}` — producing soft-404 "Product not found"
 * for every real hit (product UUID and listing UUID alike).
 */
describe("searchResultHref identity → PDP lookup", () => {
  it("links a product hit by public slug, never by entity UUID", () => {
    expect(
      searchResultHref("en", {
        entity_kind: "product",
        entity_id: "a0000133-0000-4000-8000-000000000001",
        title: "Itel A70 Smartphone",
        slug: "itel-a70",
      }),
    ).toBe("/en/p/itel-a70");
  });

  it("links a listing hit to the canonical PDP with listing deep-link", () => {
    expect(
      searchResultHref("en", {
        entity_kind: "listing",
        entity_id: "1036bd7b-f861-9ea2-b97c-0ddbf22eb2ed",
        title: "Itel A70 Smartphone",
        slug: "itel-a70",
      }),
    ).toBe("/en/p/itel-a70?listing=1036bd7b-f861-9ea2-b97c-0ddbf22eb2ed");
  });

  it("falls back to a search query when slug enrichment is missing (no UUID PDP)", () => {
    expect(
      searchResultHref("en", {
        entity_kind: "product",
        entity_id: "a0000133-0000-4000-8000-000000000001",
        title: "Itel A70 Smartphone",
        slug: null,
      }),
    ).toBe("/en/search?q=Itel%20A70%20Smartphone");

    expect(
      searchResultHref("en", {
        entity_kind: "listing",
        entity_id: "1036bd7b-f861-9ea2-b97c-0ddbf22eb2ed",
        title: "Itel A70 Smartphone",
      }),
    ).toBe("/en/search?q=Itel%20A70%20Smartphone");
  });

  it("uses slug for vendor/event and UUID slug for services", () => {
    expect(
      searchResultHref("bem", {
        entity_kind: "vendor",
        entity_id: "vendor-uuid",
        title: "Tech Hub",
        slug: "tech-hub-lusaka",
      }),
    ).toBe("/bem/v/tech-hub-lusaka");

    expect(
      searchResultHref("en", {
        entity_kind: "event",
        entity_id: "event-uuid",
        title: "Jazz Night",
        slug: "jazz-night",
      }),
    ).toBe("/en/e/jazz-night");

    expect(
      searchResultHref("en", {
        entity_kind: "service",
        entity_id: "svc-uuid-1",
        title: "Plumbing",
        slug: null,
      }),
    ).toBe("/en/s/svc-uuid-1");
  });
});
