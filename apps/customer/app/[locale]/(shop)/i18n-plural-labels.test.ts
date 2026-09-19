import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { createTranslator, type AbstractIntlMessages } from "next-intl";
import { describe, expect, it } from "vitest";

type LooseTranslator = (key: string, values?: Record<string, string | number>) => string;

/**
 * Regression guard for the ICU-plural class of bug this branch fixed
 * (raw `{count, plural, …}` / unfilled placeholders leaking to the UI,
 * see i18n-template-labels.test.ts). That fix targeted `checkout.cart.itemCount`
 * specifically; this file renders the real catalogue entries through the real
 * next-intl formatter for every shipping locale, at both plural forms, so a
 * future catalogue edit that reintroduces the bug fails here instead of in
 * production.
 */

const here = dirname(fileURLToPath(import.meta.url));
const messagesDir = join(here, "../../../../../packages/i18n/messages");

const LOCALES = ["en", "bem", "nya"] as const;

const RAW_ICU_SYNTAX = /[{}]|plural|#/;

function loadNamespace(locale: string, namespace: string): Record<string, unknown> {
  return JSON.parse(readFileSync(join(messagesDir, locale, `${namespace}.json`), "utf8")) as Record<
    string,
    unknown
  >;
}

describe.each(LOCALES)("plural labels — %s", (locale) => {
  it.each([1, 5])(
    "checkout.cart.itemCount renders for count=%i, no raw ICU or key path",
    (count) => {
      const checkout = loadNamespace(locale, "checkout");
      const messages = { checkout } as AbstractIntlMessages;
      const t = createTranslator({
        locale,
        messages,
        namespace: "checkout",
      }) as unknown as LooseTranslator;

      const output = t("cart.itemCount", { count });

      expect(output).not.toBe("cart.itemCount");
      expect(output).not.toBe("checkout.cart.itemCount");
      expect(output).not.toMatch(RAW_ICU_SYNTAX);
      expect(output).toContain(String(count));
    },
  );

  it.each([1, 5])("search.results.count renders for count=%i, no raw ICU or key path", (count) => {
    const search = loadNamespace(locale, "search");
    const messages = { search } as AbstractIntlMessages;
    const t = createTranslator({
      locale,
      messages,
      namespace: "search",
    }) as unknown as LooseTranslator;

    const output = t("results.count", { count });

    expect(output).not.toBe("results.count");
    expect(output).not.toBe("search.results.count");
    expect(output).not.toMatch(RAW_ICU_SYNTAX);
    expect(output).toContain(String(count));
  });
});

describe("plural word actually changes between one and many", () => {
  it.each(LOCALES)("%s: itemCount singular and plural forms differ", (locale) => {
    const checkout = loadNamespace(locale, "checkout");
    const messages = { checkout } as AbstractIntlMessages;
    const t = createTranslator({
      locale,
      messages,
      namespace: "checkout",
    }) as unknown as LooseTranslator;

    const one = t("cart.itemCount", { count: 1 }).replace("1", "#");
    const many = t("cart.itemCount", { count: 5 }).replace("5", "#");

    expect(one).not.toBe(many);
  });
});
