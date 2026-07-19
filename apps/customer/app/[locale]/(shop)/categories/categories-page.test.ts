import { afterEach, describe, expect, it, vi } from "vitest";

import { buildCategoryTree, isMalformedCategoryPayload } from "../_components/category-tree";
import { classifyCategoriesQueryError, logCategoriesLoadFailure } from "../_components/merch-data";

import { resolveCategoriesBrowseView } from "./categories-view";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("categories browse tree (CUST-03)", () => {
  it("exposes Phase-1 roots with navigable children", () => {
    const tree = buildCategoryTree([
      {
        id: "electronics",
        name: "Electronics",
        slug: "electronics",
        position: 1,
        parent_id: null,
        prohibited: false,
      },
      {
        id: "phones",
        name: "Phones",
        slug: "phones",
        position: 1,
        parent_id: "electronics",
        prohibited: false,
      },
      {
        id: "banned",
        name: "Banned",
        slug: "banned",
        position: 2,
        parent_id: null,
        prohibited: true,
      },
    ]);

    expect(tree).toHaveLength(1);
    expect(tree[0]?.slug).toBe("electronics");
    expect(tree[0]?.children.map((child) => child.slug)).toEqual(["phones"]);
  });

  it("returns an empty tree honestly when there are no public categories", () => {
    expect(buildCategoryTree([])).toEqual([]);
  });

  it("does not promote orphans or follow parent cycles into infinite nests", () => {
    const tree = buildCategoryTree([
      {
        id: "a",
        name: "A",
        slug: "a",
        position: 0,
        parent_id: "missing",
        prohibited: false,
      },
      {
        id: "b",
        name: "B",
        slug: "b",
        position: 1,
        parent_id: "b",
        prohibited: false,
      },
      {
        id: "root",
        name: "Root",
        slug: "root",
        position: 2,
        parent_id: null,
        prohibited: false,
      },
    ]);

    expect(tree.map((node) => node.slug)).toEqual(["root"]);
    expect(tree[0]?.children).toEqual([]);
  });
});

describe("resolveCategoriesBrowseView", () => {
  it("maps a populated catalogue to a populated view", () => {
    const view = resolveCategoriesBrowseView({
      ok: true,
      categories: [
        {
          id: "electronics",
          name: "Electronics",
          slug: "electronics",
          path: "electronics",
          position: 1,
          parent_id: null,
          prohibited: false,
        },
        {
          id: "phones",
          name: "Phones",
          slug: "phones",
          path: "electronics.phones",
          position: 1,
          parent_id: "electronics",
          prohibited: false,
        },
      ],
    });

    expect(view.kind).toBe("populated");
    if (view.kind === "populated") {
      expect(view.tree).toHaveLength(1);
      expect(view.tree[0]?.children).toHaveLength(1);
    }
  });

  it("maps a valid empty catalogue to an honest empty view", () => {
    expect(resolveCategoriesBrowseView({ ok: true, categories: [] })).toEqual({
      kind: "empty",
    });
  });

  it("maps unauthorized failures distinctly from empty", () => {
    expect(
      resolveCategoriesBrowseView({ ok: false, reason: "unauthorized", code: "PGRST301" }),
    ).toEqual({ kind: "unavailable", reason: "unauthorized" });
  });

  it("maps upstream failures distinctly from empty", () => {
    expect(resolveCategoriesBrowseView({ ok: false, reason: "upstream", status: 503 })).toEqual({
      kind: "unavailable",
      reason: "upstream",
    });
  });

  it("maps config failures distinctly from empty", () => {
    expect(resolveCategoriesBrowseView({ ok: false, reason: "config" })).toEqual({
      kind: "unavailable",
      reason: "config",
    });
  });

  it("maps malformed payloads distinctly from empty", () => {
    expect(resolveCategoriesBrowseView({ ok: false, reason: "malformed" })).toEqual({
      kind: "unavailable",
      reason: "malformed",
    });
  });
});

describe("categories load classification + logging", () => {
  it("classifies JWT / permission errors as unauthorized", () => {
    expect(classifyCategoriesQueryError({ code: "PGRST301", status: 401 })).toBe("unauthorized");
    expect(classifyCategoriesQueryError({ message: "JWT expired", status: 401 })).toBe(
      "unauthorized",
    );
    expect(classifyCategoriesQueryError({ message: "permission denied", code: "42501" })).toBe(
      "unauthorized",
    );
  });

  it("classifies missing Supabase env as config", () => {
    expect(
      classifyCategoriesQueryError({
        message: "Missing required environment variable: NEXT_PUBLIC_SUPABASE_URL",
      }),
    ).toBe("config");
  });

  it("classifies other query failures as upstream", () => {
    expect(classifyCategoriesQueryError({ code: "PGRST002", status: 500 })).toBe("upstream");
    expect(classifyCategoriesQueryError({ message: "connection reset" })).toBe("upstream");
  });

  it("detects wholly malformed payloads", () => {
    expect(isMalformedCategoryPayload([{ foo: "bar" }, null, 12])).toBe(true);
    expect(
      isMalformedCategoryPayload([
        {
          id: "electronics",
          name: "Electronics",
          slug: "electronics",
          position: 1,
          parent_id: null,
          prohibited: false,
        },
      ]),
    ).toBe(false);
    expect(isMalformedCategoryPayload([])).toBe(false);
  });

  it("emits structured failure logs without secrets or row payloads", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);

    logCategoriesLoadFailure({ reason: "upstream", code: "PGRST002", status: 503 });

    expect(errorSpy).toHaveBeenCalledTimes(1);
    const payload = JSON.parse(String(errorSpy.mock.calls[0]?.[0]));
    expect(payload).toEqual({
      level: "error",
      event: "customer.categories.load_failed",
      reason: "upstream",
      code: "PGRST002",
      status: 503,
    });
    expect(JSON.stringify(payload)).not.toMatch(/supabase|service_role|anon|cookie|Bearer/i);
  });
});

describe("browseCategories i18n distinguishes empty vs unavailable", () => {
  it("keeps English empty and unavailable copy distinct", async () => {
    const catalog = await import("../../../../../../packages/i18n/messages/en/catalog.json");
    const browse = catalog.default.browseCategories;
    expect(browse.emptyTitle).not.toEqual(browse.unavailableTitle);
    expect(browse.emptyBody).not.toEqual(browse.unavailableBody);
    expect(browse.emptyTitle.toLowerCase()).toContain("no categories");
    expect(browse.unavailableTitle.toLowerCase()).toContain("unavailable");
  });

  it("keeps French empty and unavailable copy distinct", async () => {
    const catalog = await import("../../../../../../packages/i18n/messages/fr/catalog.json");
    const browse = catalog.default.browseCategories;
    expect(browse.emptyTitle).not.toEqual(browse.unavailableTitle);
    expect(browse.emptyBody).not.toEqual(browse.unavailableBody);
  });
});
