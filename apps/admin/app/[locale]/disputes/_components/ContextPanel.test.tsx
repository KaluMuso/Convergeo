// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";

import { ContextPanel } from "./ContextPanel";
import type { OrderContext } from "./api";

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values?.title !== undefined ? `${key}:${String(values.title)}x${String(values.qty)}` : key,
}));
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

function order(titles: (string | null)[]): OrderContext {
  return {
    id: "o1",
    status: "placed",
    fulfilment: "delivery",
    delivery_fee_ngwee: 0,
    order_total_ngwee: 100,
    vendor_display_name: "V",
    vendor_slug: "v",
    customer_phone: null,
    customer_display_name: null,
    items: titles.map((title_snapshot, i) => ({
      id: `i${i}`,
      item_kind: "product",
      qty: 1,
      unit_price_ngwee: 100,
      title_snapshot,
    })),
    payments: [],
    ledger: [],
  } as unknown as OrderContext;
}

function render(o: OrderContext): string {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  act(() => root.render(<ContextPanel order={o} locale="en" />));
  const text = host.textContent ?? "";
  act(() => root.unmount());
  return text;
}

describe("ContextPanel line titles", () => {
  it("shows the product name when resolved", () => {
    expect(render(order(["Solar lamp"]))).toContain("itemLine:Solar lampx1");
  });

  it("uses the translated untitled label, never the item kind", () => {
    const text = render(order([null, "  "]));
    expect(text).toContain("itemLine:untitledItemx1");
    expect(text).not.toContain("product");
  });
});
