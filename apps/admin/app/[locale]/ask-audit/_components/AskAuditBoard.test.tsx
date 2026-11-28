// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
  useLocale: () => "en",
}));
vi.mock("@vergeo/auth", () => ({ getBrowserAccessToken: () => "token" }));
vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, askAuditApi: { request: api.request } };
});

import { AskAuditBoard } from "./AskAuditBoard";

import type { AskAuditAnswer, AskAuditPage } from "./api";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

const flagged: AskAuditAnswer = {
  id: "ans-1",
  created_at: "2026-11-27T09:00:00+00:00",
  query: "google pixel 10 pro",
  answer_text: "Google Pixel 10 Pro for K5.00.",
  model: "moonshotai/kimi-k2",
  source: "ai",
  intent: null,
  cached: false,
  refused: false,
  locale: "en",
  asker: "guest",
  audit_status: "flagged",
  audit_severity: "critical",
  audited_at: "2026-11-27T09:00:05+00:00",
  citations: [
    {
      kind: "listing",
      id: "lst-1",
      title: "Google Pixel 10 Pro",
      price_ngwee: 500,
      price_max_ngwee: 500,
      href: "/p/pixel-10-pro?listing=lst-1",
      vendor_id: "ven-1",
      vendor_name: "Pixel Hub",
      vendor_href: "/v/pixel-hub",
    },
  ],
  findings: [
    {
      id: "f-1",
      rule: "price_below_category_floor",
      severity: "critical",
      reason: "Google Pixel 10 Pro is priced at K5.00, below the minimum.",
      entity_kind: "listing",
      entity_id: "lst-1",
      entity_href: "/p/pixel-10-pro?listing=lst-1",
      vendor_id: "ven-1",
      vendor_name: "Pixel Hub",
      vendor_href: "/v/pixel-hub",
      details: {},
    },
  ],
};

let container: HTMLDivElement;
let root: Root;

async function render() {
  await act(async () => {
    root.render(<AskAuditBoard />);
  });
}

beforeEach(() => {
  api.request.mockReset();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  document.body.innerHTML = "";
});

describe("AskAuditBoard", () => {
  it("lists flagged answers by default with links to the listing and the vendor", async () => {
    api.request.mockResolvedValue({
      items: [flagged],
      next_before: null,
      next_before_id: null,
    } satisfies AskAuditPage);
    await render();

    expect(api.request.mock.calls[0]?.[0]).toContain("flagged_only=true");
    expect(container.textContent).toContain("google pixel 10 pro");
    expect(container.textContent).toContain("admin.askAudit.rules.price_below_category_floor");
    expect(container.textContent).toContain("below the minimum");

    const item = container.querySelector<HTMLAnchorElement>('[data-testid="ask-audit-item-link"]');
    const vendor = container.querySelector<HTMLAnchorElement>(
      '[data-testid="ask-audit-vendor-link"]',
    );
    expect(item?.href).toBe("http://localhost:3000/en/p/pixel-10-pro?listing=lst-1");
    expect(vendor?.href).toBe("http://localhost:3000/en/v/pixel-hub");
    expect(item?.target).toBe("_blank");
    expect(item?.rel).toContain("noopener");
  });

  it("refetches every answer when 'flagged only' is unticked", async () => {
    api.request.mockResolvedValue({ items: [], next_before: null, next_before_id: null });
    await render();
    const box = container.querySelector<HTMLInputElement>('[data-testid="ask-audit-flagged-only"]');
    await act(async () => {
      box?.click();
    });
    const urls = api.request.mock.calls.map((call) => String(call[0]));
    expect(urls.at(-1)).not.toContain("flagged_only");
  });

  it("shows the empty state and a retryable error", async () => {
    api.request.mockResolvedValue({ items: [], next_before: null, next_before_id: null });
    await render();
    expect(container.textContent).toContain("admin.askAudit.emptyFlagged");

    api.request.mockRejectedValue(new Error("boom"));
    await act(async () => {
      root.render(<AskAuditBoard key="again" />);
    });
    expect(container.textContent).toContain("admin.askAudit.error");
  });
});
