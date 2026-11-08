import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Every locale the customer app ships must define the variant + lightbox
 * strings with the same keys and ICU placeholders as English (bem/nya may be
 * EN passthrough pending native review, but never missing).
 */
const MESSAGES = join(__dirname, "../../../../../../../packages/i18n/messages");
const LOCALES = ["en", "fr", "zh", "bem", "nya"] as const;
const SUBTREES: Array<[namespace: string, path: string[]]> = [
  ["catalog", ["pdp", "variants"]],
  ["catalog", ["pdp", "lightbox"]],
  ["checkout", ["variant"]],
];
const ORDER_KEYS = ["variantOption", "variantSeparator"];

type Tree = { [key: string]: string | Tree };

function load(locale: string, namespace: string): Tree {
  return JSON.parse(readFileSync(join(MESSAGES, locale, `${namespace}.json`), "utf8")) as Tree;
}

function pick(tree: Tree, path: string[]): Tree {
  return path.reduce<Tree>((node, key) => node[key] as Tree, tree);
}

function flatten(tree: Tree, prefix = ""): Record<string, string> {
  return Object.entries(tree).reduce<Record<string, string>>((acc, [key, value]) => {
    const full = prefix ? `${prefix}.${key}` : key;
    return typeof value === "string"
      ? { ...acc, [full]: value }
      : { ...acc, ...flatten(value, full) };
  }, {});
}

function placeholders(message: string): string[] {
  return [...message.matchAll(/\{(\w+)/g)].map((match) => match[1] ?? "").sort();
}

describe("variant + lightbox i18n", () => {
  for (const [namespace, path] of SUBTREES) {
    const english = flatten(pick(load("en", namespace), path));
    for (const locale of LOCALES) {
      it(`${locale}: ${namespace}.${path.join(".")} matches English keys and placeholders`, () => {
        const localized = flatten(pick(load(locale, namespace), path));
        expect(Object.keys(localized).sort()).toEqual(Object.keys(english).sort());
        for (const [key, message] of Object.entries(english)) {
          expect(placeholders(localized[key] ?? ""), `${locale} ${key}`).toEqual(
            placeholders(message),
          );
          expect((localized[key] ?? "").trim().length > 0 || key.endsWith("Separator")).toBe(true);
        }
      });
    }
  }

  for (const locale of LOCALES) {
    it(`${locale}: orders.detail has the variant label keys`, () => {
      const detail = pick(load(locale, "orders"), ["detail"]);
      for (const key of ORDER_KEYS) {
        expect(typeof detail[key]).toBe("string");
      }
    });
  }
});
