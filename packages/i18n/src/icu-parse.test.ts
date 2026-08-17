import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { createTranslator } from "next-intl";
import { describe, expect, it } from "vitest";

import { flattenMessages } from "./catalog";
import { extractIcuPlaceholders } from "./phase1-critical";
import { NAMESPACES } from "./request";

const messagesRoot = join(fileURLToPath(new URL("../messages", import.meta.url)));

function loadFlat(locale: string, namespace: string): Record<string, string> {
  const raw = JSON.parse(
    readFileSync(join(messagesRoot, locale, `${namespace}.json`), "utf8"),
  ) as Record<string, unknown>;
  return flattenMessages(raw as Parameters<typeof flattenMessages>[0]);
}

type IcuTestValue = string | number | ((chunks: string) => string);
type IcuTestValues = Record<string, IcuTestValue>;
type TranslatorValues = Record<string, string | number | Date>;

function dummyValues(placeholders: string[]): Record<string, string | number> {
  return Object.fromEntries(
    placeholders.map((name, index) => [name, name === "count" || name === "qty" ? 2 : `v${index}`]),
  );
}

function richTextTags(template: string): Record<string, (chunks: string) => string> {
  const tags = new Set<string>();
  for (const match of template.matchAll(/<\/?([A-Za-z][\w]*)\b[^>]*>/g)) {
    if (match[1]) {
      tags.add(match[1]);
    }
  }
  return Object.fromEntries([...tags].map((tag) => [tag, (chunks: string) => chunks]));
}

function translatorValues(template: string, placeholders: string[]): TranslatorValues {
  const values: IcuTestValues = {
    ...dummyValues(placeholders),
    ...richTextTags(template),
  };
  // next-intl accepts rich-text tag functions at runtime; createTranslator's
  // public values type only lists primitives.
  return values as unknown as TranslatorValues;
}

function bracesAreBalanced(template: string): boolean {
  let depth = 0;
  for (const char of template) {
    if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
      if (depth < 0) {
        return false;
      }
    }
  }
  return depth === 0;
}

describe("ICU message parsing coverage", () => {
  for (const namespace of NAMESPACES) {
    it(`en/${namespace} templates parse without INVALID_MESSAGE`, () => {
      const messages = loadFlat("en", namespace);
      const failures: string[] = [];

      for (const [key, template] of Object.entries(messages)) {
        if (!bracesAreBalanced(template)) {
          failures.push(`${key}: unbalanced braces`);
          continue;
        }
        try {
          const placeholders = extractIcuPlaceholders(template);
          const translator = createTranslator({
            locale: "en",
            messages: { ns: { leaf: template } },
            namespace: "ns",
            onError(error) {
              throw error;
            },
          });
          translator("leaf", translatorValues(template, placeholders));
        } catch (error) {
          failures.push(`${key}: ${error instanceof Error ? error.message : String(error)}`);
        }
      }

      expect(failures).toEqual([]);
    });
  }
});
