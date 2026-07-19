import { describe, expect, it } from "vitest";

import vendorMessages from "../../../../../../packages/i18n/messages/en/vendor.json";

import { buildCommissionTableRows, COMMISSION_RATES } from "./_components/commission-rates";

/** Mirrors `0008_config.sql` commission_rates seed (rate_bps / 100). */
const SEED_RATES: Record<string, number> = {
  electronics: 5,
  home: 8,
  fashion_beauty: 10,
  services: 12,
  event_tickets: 5,
  supplies: 3,
  groceries: 5,
  default: 8,
  free_events: 0,
};

describe("commission-rates", () => {
  it("matches D4 / 0008_config.sql seed values", () => {
    expect(COMMISSION_RATES).toHaveLength(9);
    for (const rate of COMMISSION_RATES) {
      expect(SEED_RATES[rate.categoryKey]).toBe(rate.ratePct);
    }
  });

  it("buildCommissionTableRows maps every seeded category", () => {
    const rows = buildCommissionTableRows(
      COMMISSION_RATES,
      (key) => `label:${key}`,
      (pct) => `${pct}%`,
    );

    expect(rows).toHaveLength(COMMISSION_RATES.length);
    for (const row of rows) {
      const seed = COMMISSION_RATES.find((r) => r.categoryKey === row.categoryKey);
      expect(seed).toBeDefined();
      expect(row.label).toBe(`label:${row.categoryKey}`);
      expect(row.rateLabel).toBe(`${seed!.ratePct}%`);
    }
  });
});

function collectLeafKeys(node: Record<string, unknown>, prefix = ""): string[] {
  const keys: string[] = [];
  for (const [key, value] of Object.entries(node)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") {
      keys.push(path);
    } else if (value && typeof value === "object") {
      keys.push(...collectLeafKeys(value as Record<string, unknown>, path));
    }
  }
  return keys;
}

const REQUIRED_PITCH_KEYS = [
  "meta.title",
  "meta.description",
  "hero.headline",
  "hero.headlineEmphasis",
  "hero.primaryCta",
  "inviteOnlyNotice",
  "signupUnavailable",
  "commission.heading",
  "commission.categories.electronics",
  "howItWorks.heading",
  "kyc.heading",
  "payout.promise",
  "faq.heading",
  "faq.items.fees.question",
  "cta.button",
] as const;

describe("vendor.pitch i18n", () => {
  it("uses nested pitch keys (no flat dotted keys under pitch)", () => {
    const pitch = vendorMessages.pitch as Record<string, unknown>;
    expect(pitch).toBeDefined();
    expect(typeof pitch).toBe("object");
    expect("meta.title" in pitch).toBe(false);

    const leaves = collectLeafKeys(pitch);
    expect(leaves.length).toBeGreaterThan(30);
    for (const required of REQUIRED_PITCH_KEYS) {
      expect(leaves).toContain(required);
    }
  });

  it("has a commission label for every rate categoryKey", () => {
    const pitch = vendorMessages.pitch as Record<string, unknown>;
    const commission = pitch.commission as Record<string, unknown>;
    const categoryLabels = commission.categories as Record<string, unknown>;

    for (const rate of COMMISSION_RATES) {
      expect(typeof categoryLabels[rate.categoryKey]).toBe("string");
    }
  });
});

describe("sell page SEO metadata keys", () => {
  it("exposes title and description for generateMetadata", () => {
    const pitch = vendorMessages.pitch as Record<string, unknown>;
    const meta = pitch.meta as Record<string, unknown>;
    expect(meta.title).toMatch(/Sell on Vergeo5/i);
    expect(String(meta.description).length).toBeGreaterThan(40);
  });
});
