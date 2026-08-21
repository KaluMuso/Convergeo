// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import NotFound from "./not-found";

// Regression for the live production bug: this file is reached whenever an
// ancestor layout's `notFound()` fires (e.g. an invalid-locale request that
// bypasses middleware) — before that layout's own NextIntlClientProvider adds
// `nav`. `getTranslations("nav")` reads only the ambient request-config
// messages, which ship `common` alone (packages/i18n/src/request.ts), so it
// must never be used here. `loadNamespace` is the only namespace source this
// component may depend on for `nav`.
vi.mock("@vergeo/i18n", () => ({
  loadNamespace: vi.fn(async (_locale: string, namespace: string) =>
    namespace === "nav" ? { shop: { home: "Home" } } : {},
  ),
  DEFAULT_LOCALE: "en",
}));

vi.mock("next-intl", () => ({
  createTranslator:
    ({ messages, namespace }: { messages: Record<string, unknown>; namespace: string }) =>
    (key: string) => {
      const ns = messages[namespace] as Record<string, unknown> | undefined;
      const value = key.split(".").reduce<unknown>((acc, part) => {
        return acc && typeof acc === "object" ? (acc as Record<string, unknown>)[part] : undefined;
      }, ns);
      return typeof value === "string" ? value : key;
    },
}));

vi.mock("next-intl/server", () => ({
  getLocale: vi.fn().mockResolvedValue("en"),
  getTranslations: vi.fn(async (namespace: string) => {
    if (namespace === "nav") {
      throw new Error("MISSING_MESSAGE: nav (en) — nav is not in the ambient request messages");
    }
    return (key: string) => (key === "app.name" ? "Vergeo5 Vendor" : key);
  }),
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("vendor not-found page", () => {
  it('renders without calling getTranslations("nav")', async () => {
    render(await NotFound());

    expect(screen.getByText("Vergeo5 Vendor")).toBeInTheDocument();
    expect(screen.getAllByText("Home").length).toBeGreaterThan(0);
  });
});
