// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReconciliationTile } from "./ReconciliationTile";

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    `${key} ${JSON.stringify(values ?? {})}`,
}));

vi.mock("./api", () => ({}));

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

const roots: ReturnType<typeof createRoot>[] = [];
afterEach(() => {
  act(() => roots.forEach((root) => root.unmount()));
  roots.length = 0;
  document.body.innerHTML = "";
});

describe("immutable reconciliation evidence", () => {
  it("mounts noncertifying evidence as unknown and shows its bound version", () => {
    const host = document.createElement("div");
    document.body.append(host);
    const root = createRoot(host);
    roots.push(root);
    act(() =>
      root.render(
        <ReconciliationTile
          locale="en"
          reconciliation={{
            status: "unknown",
            report_id: "immutable-report-id",
            report_date: "2026-09-30",
            has_mismatch: false,
            certifiable: false,
            version_number: 4,
            evidence_state: "noncertifying",
            provenance: "VERSIONED_ACCOUNT_BOUND",
            provider_account_id: "configured-account",
            currency: "ZMW",
            discrepancies: {},
          }}
        />,
      ),
    );
    expect(host.querySelector("[data-status]")?.getAttribute("data-status")).toBe("unknown");
    expect(host.textContent).toContain('"number":4');
    act(() => host.querySelector("button")!.click());
    expect(host.textContent).toContain("immutable-report-id");
    expect(host.textContent).toContain("configured-account");
    expect(host.textContent).not.toContain("cleanDay");
  });

  it("mounts unresolved movement evidence red and preserves its discrepancy detail", () => {
    const host = document.createElement("div");
    document.body.append(host);
    const root = createRoot(host);
    roots.push(root);
    act(() =>
      root.render(
        <ReconciliationTile
          locale="en"
          reconciliation={{
            status: "red",
            report_id: "unresolved-report-id",
            report_date: "2026-09-30",
            has_mismatch: true,
            certifiable: false,
            version_number: 2,
            evidence_state: "unresolved",
            discrepancies: { provider_unmatched: [{ identity: "movement-7" }] },
          }}
        />,
      ),
    );
    expect(host.querySelector("[data-status]")?.getAttribute("data-status")).toBe("red");
    act(() => host.querySelector("button")!.click());
    expect(host.textContent).toContain("movement-7");
    expect(host.textContent).toContain("unresolved-report-id");
  });
});
