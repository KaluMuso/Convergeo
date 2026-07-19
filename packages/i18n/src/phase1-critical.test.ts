import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { flattenMessages } from "./catalog";
import {
  extractIcuPlaceholders,
  isUnexpectedEnglishFallback,
  keyMatchesPhase1Prefix,
  PHASE1_CRITICAL_LOCALES,
  PHASE1_CRITICAL_NAMESPACES,
  PHASE1_CRITICAL_PREFIXES,
  type Phase1Namespace,
} from "./phase1-critical";

const messagesRoot = join(fileURLToPath(new URL("../messages", import.meta.url)));

function loadFlat(locale: string, namespace: string): Record<string, string> {
  const raw = JSON.parse(
    readFileSync(join(messagesRoot, locale, `${namespace}.json`), "utf8"),
  ) as Record<string, unknown>;
  return flattenMessages(raw as Parameters<typeof flattenMessages>[0]);
}

describe("CUST-I18N-01 phase-1 completeness gate", () => {
  for (const locale of PHASE1_CRITICAL_LOCALES) {
    for (const namespace of PHASE1_CRITICAL_NAMESPACES) {
      it(`${locale}/${namespace} covers critical keys without English leftovers or broken ICU`, () => {
        const en = loadFlat("en", namespace);
        const loc = loadFlat(locale, namespace);
        const prefixes = PHASE1_CRITICAL_PREFIXES[namespace as Phase1Namespace];
        const critical = Object.keys(en).filter((key) => keyMatchesPhase1Prefix(key, prefixes));

        expect(critical.length).toBeGreaterThan(0);

        const missing: string[] = [];
        const englishLeftovers: string[] = [];
        const icuMismatches: string[] = [];

        for (const key of critical) {
          const enValue = en[key];
          const locValue = loc[key];
          if (enValue === undefined) {
            continue;
          }
          if (locValue === undefined) {
            missing.push(key);
            continue;
          }
          if (isUnexpectedEnglishFallback(enValue, locValue)) {
            englishLeftovers.push(key);
          }
          const enPh = extractIcuPlaceholders(enValue).join(",");
          const locPh = extractIcuPlaceholders(locValue).join(",");
          if (enPh !== locPh) {
            icuMismatches.push(`${key} en=[${enPh}] ${locale}=[${locPh}]`);
          }
        }

        expect({ missing, englishLeftovers, icuMismatches }).toEqual({
          missing: [],
          englishLeftovers: [],
          icuMismatches: [],
        });
      });
    }
  }
});

describe("phase1 helpers", () => {
  it("matches prefixes inclusively", () => {
    expect(keyMatchesPhase1Prefix("home.nav.cart", ["home.nav"])).toBe(true);
    expect(keyMatchesPhase1Prefix("home.hero", ["home.hero"])).toBe(true);
    expect(keyMatchesPhase1Prefix("home.flash", ["home.nav"])).toBe(false);
  });

  it("extracts ICU placeholder names", () => {
    expect(extractIcuPlaceholders("{count, plural, one {# item} other {# items}}")).toEqual([
      "count",
    ]);
    expect(extractIcuPlaceholders("From {price}")).toEqual(["price"]);
  });
});
