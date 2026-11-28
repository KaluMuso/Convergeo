// @vitest-environment jsdom
import { NextIntlClientProvider } from "next-intl";
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import admin from "../../../../../../packages/i18n/messages/en/admin.json";
import { AdminPermissionsContext, type AdminPermissions } from "../../../../lib/roles-api";

const requestMock = vi.fn();

vi.mock("../../_components/api", () => ({
  dashboardApi: {
    request: (...args: unknown[]) => requestMock(...args),
  },
}));
vi.mock("../../../../lib/access-token", () => ({ getBrowserAccessToken: async () => "t" }));
vi.mock("../../../../lib/api-base-url", () => ({
  getApiBaseUrl: () => "http://127.0.0.1:8000",
}));
vi.mock("../../../../lib/analytics-export", () => ({
  AnalyticsExportError: class AnalyticsExportError extends Error {},
  downloadAnalyticsCsv: vi.fn(),
}));
vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock("../../_components/use-analytics-nav", () => ({
  useAnalyticsNavEnabled: () => false,
}));

import { DashboardsView } from "./dashboards-view";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

const usersPayload = {
  range: { period: "7d", from: "2026-11-01", to: "2026-11-07" },
  previous_range: { from: "2026-10-25", to: "2026-10-31" },
  totals: { customers: 0, vendors: 0, active_vendors: 0 },
  new: { customers: 0, vendors: 0 },
  previous_new: { customers: 0, vendors: 0 },
  daily: [],
  activity: { enabled: false as const },
  cohorts: [],
};

const analyticsGrants: AdminPermissions = {
  permissions: ["analytics.read"],
  unrestricted: false,
  can_manage_roles: false,
};

describe("DashboardsView grants gate", () => {
  let container: HTMLDivElement;
  let root: Root | null;

  beforeEach(() => {
    requestMock.mockReset();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root?.unmount();
    });
    container.remove();
    root = null;
  });

  function renderWithGrants(grants: AdminPermissions | null) {
    act(() => {
      root?.render(
        <NextIntlClientProvider locale="en" messages={{ admin }} timeZone="UTC">
          <AdminPermissionsContext.Provider value={grants}>
            <DashboardsView locale="en" tab="users" />
          </AdminPermissionsContext.Provider>
        </NextIntlClientProvider>,
      );
    });
  }

  it("shows loading and skips the API until admin grants are known", async () => {
    requestMock.mockReturnValue(new Promise(() => {}));
    renderWithGrants(null);

    expect(requestMock).not.toHaveBeenCalled();
    expect(container.textContent).toContain("Loading analytics");
    expect(container.textContent).not.toContain("Only platform admins can view analytics.");
  });

  it("fetches the users report once grants include analytics.read", async () => {
    requestMock.mockResolvedValue(usersPayload);

    renderWithGrants(analyticsGrants);
    await act(async () => {
      await Promise.resolve();
    });

    expect(requestMock).toHaveBeenCalledTimes(1);
    expect(requestMock.mock.calls[0]?.[0]).toBe("/admin/analytics/users?period=7d");
    expect(container.textContent).toContain("Registered customers");
  });
});
