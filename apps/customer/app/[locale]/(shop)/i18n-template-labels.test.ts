import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * Guards the server→client label contract for the discovery slice
 * (home → search/category → PDP → cart).
 *
 * Labels handed to client components must be serializable strings, so messages
 * whose values are only known on the client travel as literal ICU templates and
 * are interpolated there. next-intl refuses to format a message with unfilled
 * placeholders: it reports a FORMATTING_ERROR and returns the message fallback,
 * which this repo configures as the bare key path (packages/i18n/src/request.ts).
 * Reading such a message with `t("…")` therefore paints `checkout.cart.unitPrice`
 * where a price belongs. `t.raw("…")` returns the template untouched.
 *
 * So: in these producers, a no-values `t("key")` call is only legal when the
 * message carries no `{placeholder}`.
 */

const here = dirname(fileURLToPath(import.meta.url));
const messagesDir = join(here, "../../../../../packages/i18n/messages/en");

/** Producer file → the namespace its no-values `t("…")` calls resolve against. */
const PRODUCERS: ReadonlyArray<readonly [string, string]> = [
  ["page.tsx", "catalog"],
  ["cart/page.tsx", "checkout"],
  ["search/page.tsx", "search"],
  ["c/[...slug]/page.tsx", "catalog"],
  ["p/[slug]/page.tsx", "catalog"],
  ["layout.tsx", "nav"],
  ["_components/cart/lazy-cart-host-slot.tsx", "checkout"],
];

/** Matches `t("key")` / `tCatalog("key")` — a call with no values argument. */
const NO_VALUES_CALL = /\bt[A-Za-z]*\(\s*"([A-Za-z0-9_.]+)"\s*\)/g;

/** ICU placeholder, e.g. `{amount}` or `{count, plural, …}`. */
const HAS_PLACEHOLDER = /\{\s*[A-Za-z_][A-Za-z0-9_]*\s*[,}]/;

function loadNamespaceMessages(namespace: string): Record<string, unknown> {
  return JSON.parse(readFileSync(join(messagesDir, `${namespace}.json`), "utf8")) as Record<
    string,
    unknown
  >;
}

function lookupMessage(namespace: string, key: string): string | undefined {
  let node: unknown = loadNamespaceMessages(namespace);
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null) return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "string" ? node : undefined;
}

describe("discovery slice label producers", () => {
  it.each(PRODUCERS)("%s reads placeholder messages raw, not via t()", (file, namespace) => {
    const source = readFileSync(join(here, file), "utf8");

    const offenders = [...source.matchAll(NO_VALUES_CALL)]
      .map((match) => match[1] as string)
      .filter((key) => {
        const message = lookupMessage(namespace, key);
        return message !== undefined && HAS_PLACEHOLDER.test(message);
      });

    expect([...new Set(offenders)]).toEqual([]);
  });

  it("recognises a placeholder-bearing message when it sees one", () => {
    // Sanity check on the detector itself: these are the messages that used to
    // render as key paths in the cart and on search result tabs.
    expect(HAS_PLACEHOLDER.test(lookupMessage("checkout", "cart.unitPrice") ?? "")).toBe(true);
    expect(HAS_PLACEHOLDER.test(lookupMessage("checkout", "cart.itemCount") ?? "")).toBe(true);
    expect(HAS_PLACEHOLDER.test(lookupMessage("search", "tabs.count") ?? "")).toBe(true);
    expect(HAS_PLACEHOLDER.test(lookupMessage("checkout", "cart.subtotal") ?? "")).toBe(false);
  });
});
