// @vitest-environment jsdom
import { NextIntlClientProvider } from "next-intl";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import admin from "../../../../../../packages/i18n/messages/en/admin.json";

vi.mock("../../_components/api", () => ({ dashboardApi: { request: vi.fn() } }));
vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

import { TabBody } from "./analytics-view";

import type { OverviewData, SearchDemandData } from "./analytics-data";

function render(node: React.ReactNode): string {
  return renderToStaticMarkup(
    <NextIntlClientProvider locale="en" messages={{ admin }} timeZone="UTC">
      {node}
    </NextIntlClientProvider>,
  );
}

const behaviour = {
  sessions: 12,
  visitor_days: 9,
  bounce_rate_bps: null,
  avg_active_span_seconds: null,
  searches: 4,
  zero_result_share_bps: null,
};

const commercial = {
  checkouts_started: 3,
  orders_placed: 3,
  orders_cancelled: 0,
  orders_paid: 2,
  paid_checkouts: 2,
  gmv_paid_ngwee: 123_456,
  aov_ngwee: 61_728,
  payments_reconciled: true,
  payment_mismatch_days: [],
};

describe("analytics tab bodies", () => {
  it("overview shows ngwee as kwacha and withholds rates below the minimum sample", () => {
    const data: OverviewData = {
      range: { from: "2026-11-13", to: "2026-11-19" },
      previous_range: { from: "2026-11-06", to: "2026-11-12" },
      data_through: "2026-11-19",
      min_sample_n: 20,
      behaviour,
      previous_behaviour: behaviour,
      commercial,
      previous_commercial: { ...commercial, gmv_paid_ngwee: 0, orders_paid: 0 },
      daily: [{ day: "2026-11-19", sessions: 12, orders_paid: 2, gmv_paid_ngwee: 123_456 }],
    };
    const html = render(<TabBody tab="overview" data={data} locale="en" />);
    expect(html).toContain("K1,234.56");
    expect(html).toContain("Not enough data (needs 20+)");
    expect(html).toContain("A session ends after 30 minutes without activity.");
    expect(html).not.toContain('role="alert"');
  });

  it("overview flags unreconciled payments", () => {
    const data = {
      range: { from: "2026-11-13", to: "2026-11-19" },
      previous_range: { from: "2026-11-06", to: "2026-11-12" },
      data_through: null,
      min_sample_n: 20,
      behaviour,
      previous_behaviour: behaviour,
      commercial: {
        ...commercial,
        payments_reconciled: false,
        payment_mismatch_days: ["2026-11-18"],
      },
      previous_commercial: commercial,
      daily: [],
    } satisfies OverviewData;
    const html = render(<TabBody tab="overview" data={data} locale="en" />);
    expect(html).toContain('role="alert"');
    expect(html).toContain("2026-11-18");
    expect(html).toContain("Behaviour data has not been rolled up yet.");
  });

  it("search tab states the k-threshold and lists only returned terms", () => {
    const data: SearchDemandData = {
      range: { from: "2026-11-13", to: "2026-11-19" },
      data_through: "2026-11-19",
      k: 5,
      min_sample_n: 20,
      totals: { searches: 40, zero_results: 10, zero_result_share_bps: 2500 },
      top_terms: [{ normalized_term: "solar panel", searches: 9, zero_results: 1 }],
      zero_result_terms: [{ normalized_term: "chitenge", searches: 6, zero_results: 6 }],
      other: { terms: 3, searches: 7, zero_results: 2 },
    };
    const html = render(<TabBody tab="search" data={data} locale="en" />);
    expect(html).toContain("fewer than 5 times");
    expect(html).toContain("solar panel");
    expect(html).toContain("chitenge");
    expect(html).toContain("Other: 3 terms, 7 searches");
    expect(html).toContain("25%");
  });
});
