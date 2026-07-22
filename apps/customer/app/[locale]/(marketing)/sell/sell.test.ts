import { afterEach, describe, expect, it, vi } from "vitest";

import vendorMessages from "../../../../../../packages/i18n/messages/en/vendor.json";

import {
  buildCommissionTableRows,
  COMMISSION_RATES,
  fetchCommissionRates,
  formatCommissionRateLabel,
} from "./_components/commission-rates";

vi.mock("../../../../../lib/api-base-url", () => ({
  absoluteApiUrl: (path: string) =>
    path.startsWith("http") ? path : `https://api.example.test${path}`,
}));

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

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

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
      "en",
      (key) => `label:${key}`,
      (key, values) => `${values?.rate}%`,
    );

    expect(rows).toHaveLength(COMMISSION_RATES.length);
    for (const row of rows) {
      const seed = COMMISSION_RATES.find((r) => r.categoryKey === row.categoryKey);
      expect(seed).toBeDefined();
      expect(row.label).toBe(`label:${row.categoryKey}`);
      expect(row.rateLabel).toBe(`${seed!.ratePct}%`);
    }
  });

  it("formatCommissionRateLabel uses locale-aware decimals for fractional rates", () => {
    const label = formatCommissionRateLabel(6.5, "fr", (key, values) => `${values?.rate} %`);

    expect(label).toBe("6,5 %");
  });

  it("formatCommissionRateLabel keeps whole-number rates compact", () => {
    const label = formatCommissionRateLabel(10, "en", (key, values) => `${values?.rate}%`);

    expect(label).toBe("10%");
  });

  it("fetchCommissionRates renders live endpoint values", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.example.test");

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          rates: [
            { category_key: "electronics", rate_pct: 6.5 },
            { category_key: "home", rate_pct: 8 },
            { category_key: "fashion_beauty", rate_pct: 10 },
            { category_key: "services", rate_pct: 12 },
            { category_key: "event_tickets", rate_pct: 5 },
            { category_key: "supplies", rate_pct: 3 },
            { category_key: "groceries", rate_pct: 5 },
            { category_key: "default", rate_pct: 8 },
            { category_key: "free_events", rate_pct: 0 },
          ],
          updated_at: "2026-07-22T12:00:00+00:00",
        }),
      }),
    );

    const rates = await fetchCommissionRates();
    const electronics = rates.find((rate) => rate.categoryKey === "electronics");

    expect(fetch).toHaveBeenCalledWith(
      "https://api.example.test/public/config/commission-rates",
      expect.objectContaining({ next: { revalidate: 300 } }),
    );
    expect(electronics?.ratePct).toBe(6.5);
    expect(rates).toHaveLength(COMMISSION_RATES.length);
  });

  it("fetchCommissionRates falls back without throwing when the API is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    await expect(fetchCommissionRates()).resolves.toEqual([...COMMISSION_RATES]);
  });

  it("fetchCommissionRates falls back on non-OK responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({ error: { code: "unavailable" } }),
      }),
    );

    await expect(fetchCommissionRates()).resolves.toEqual([...COMMISSION_RATES]);
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
