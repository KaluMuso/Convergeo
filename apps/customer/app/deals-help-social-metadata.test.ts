import { describe, expect, it, vi } from "vitest";

import catalogEn from "../../../packages/i18n/messages/en/catalog.json";
import marketingEn from "../../../packages/i18n/messages/en/marketing.json";

vi.mock("@vergeo/i18n", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@vergeo/i18n")>();
  return {
    ...actual,
    loadNamespace: vi.fn(async (_locale: string, ns: string) =>
      ns === "catalog" ? catalogEn : marketingEn,
    ),
  };
});

vi.mock("next-intl", () => ({
  createTranslator: ({
    namespace,
    messages,
  }: {
    namespace?: string;
    messages?: Record<string, unknown>;
  }) => {
    const root =
      namespace === "catalog"
        ? catalogEn
        : namespace === "marketing.help"
          ? ((messages?.marketing as { help: Record<string, unknown> })?.help ?? marketingEn.help)
          : {};
    return (key: string) => {
      const parts = key.split(".");
      let node: unknown = root;
      for (const part of parts) {
        if (node && typeof node === "object" && part in (node as object)) {
          node = (node as Record<string, unknown>)[part];
        } else {
          return key;
        }
      }
      return typeof node === "string" ? node : key;
    };
  },
}));

vi.mock("next-intl/server", () => ({
  getMessages: vi.fn(async () => ({})),
  getRequestConfig: (config: unknown) => config,
  setRequestLocale: vi.fn(),
}));

import { generateMetadata as helpArticleMeta } from "./[locale]/(marketing)/help/[slug]/page";
import { generateMetadata as helpIndexMeta } from "./[locale]/(marketing)/help/page";
import { generateMetadata as dealsMeta } from "./[locale]/(shop)/deals/page";

describe("deals and help social metadata", () => {
  it("deals", async () => {
    const metadata = await dealsMeta({ params: Promise.resolve({ locale: "en" }) });
    expect(metadata.openGraph?.title).toBe("Today's deals");
    expect(String(metadata.openGraph?.url)).toContain("/en/deals");
  });

  it("help index", async () => {
    const metadata = await helpIndexMeta({ params: Promise.resolve({ locale: "en" }) });
    expect(metadata.openGraph?.title).toBe("Help Centre");
    expect(String(metadata.openGraph?.url)).toContain("/en/help");
  });

  it("help article", async () => {
    const metadata = await helpArticleMeta({
      params: Promise.resolve({ locale: "en", slug: "how-escrow-works" }),
    });
    expect(metadata.openGraph?.title).toBe("How escrow protects your money on Vergeo5");
    expect(String(metadata.openGraph?.url)).toContain("/en/help/how-escrow-works");
  });
});
