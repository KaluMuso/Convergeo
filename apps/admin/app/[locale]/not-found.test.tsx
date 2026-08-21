// @vitest-environment jsdom
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import NotFound from "./not-found";

// Regression for the live production bug: this file is reached whenever an
// ancestor layout's `notFound()` fires (e.g. an invalid-locale request that
// bypasses middleware) — before that layout's own NextIntlClientProvider adds
// `nav`. `getTranslations("nav")` reads only the ambient request-config
// messages, which ship `common` alone (packages/i18n/src/request.ts), so it
// must never be used here. `loadNamespace` is the only namespace source this
// component may depend on for `nav`.
//
// No component-rendering test infrastructure (@testing-library/react,
// jest-dom) exists elsewhere in apps/admin, so this renders to a static HTML
// string with react-dom/server instead of adding that dependency for one test.
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
    return (key: string) => (key === "app.name" ? "Vergeo5 Admin" : key);
  }),
}));

afterEach(() => {
  vi.restoreAllMocks();
});

describe("admin not-found page", () => {
  it('renders without calling getTranslations("nav")', async () => {
    const html = renderToStaticMarkup(await NotFound());

    expect(html).toContain("Vergeo5 Admin");
    expect(html).toContain("Home");
  });
});
