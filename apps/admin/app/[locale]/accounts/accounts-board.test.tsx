// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AccountsBoard, accountsQuery } from "./accounts-board";

const mocks = vi.hoisted(() => ({
  request: vi.fn(),
  grants: { user_id: "self", can_manage_roles: true, permissions: [], unrestricted: true },
}));
vi.mock("next-intl", () => ({ useTranslations: (ns: string) => (key: string) => `${ns}.${key}` }));
vi.mock("../../../lib/roles-api", () => ({
  rolesApi: { request: mocks.request },
  useAdminPermissions: () => mocks.grants,
}));
vi.mock("../../../lib/access-token", () => ({ getBrowserAccessToken: async () => "t" }));
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
let root: ReturnType<typeof createRoot>;
let host: HTMLDivElement;

const TARGET = "00000000-0000-4000-8000-0000000000b2";
const chanda = {
  user_id: TARGET,
  display_name: "Chanda Mwale",
  email: "chanda@example.test",
  roles: ["admin"],
};

function setValue(el: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const proto =
    el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

beforeEach(() => {
  mocks.request.mockReset();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  document.body.innerHTML = "";
});

describe("AccountsBoard", () => {
  it("shows empty state when no accounts hold admin roles", async () => {
    mocks.request.mockResolvedValue({ accounts: [] });
    await act(async () => root.render(<AccountsBoard locale="en" />));
    await vi.waitFor(() =>
      expect(host.querySelector('[data-testid="accounts-board-empty"]')).toBeTruthy(),
    );
    expect(host.textContent).toContain("admin.boards.states.accounts.emptyTitle");
  });

  it("lists names and emails without printing account UUIDs", async () => {
    mocks.request.mockResolvedValue({ accounts: [chanda], total: 1, next_offset: null });
    await act(async () => root.render(<AccountsBoard locale="en" />));
    await vi.waitFor(() =>
      expect(host.querySelector('[data-testid="accounts-table"]')).toBeTruthy(),
    );
    expect(host.textContent).toContain("Chanda Mwale");
    expect(host.textContent).toContain("chanda@example.test");
    expect(host.textContent).not.toContain(TARGET);
    expect(mocks.request.mock.calls[0]![0]).toBe("/admin/accounts?limit=25");
  });

  it("searches on the server and pages with next_offset", async () => {
    mocks.request.mockResolvedValue({ accounts: [chanda], total: 30, next_offset: 25 });
    await act(async () => root.render(<AccountsBoard locale="en" />));
    await vi.waitFor(() =>
      expect(host.querySelector('[data-testid="accounts-table"]')).toBeTruthy(),
    );
    await act(async () => {
      setValue(host.querySelector<HTMLInputElement>('[data-testid="accounts-search"]')!, "chanda");
      await new Promise((resolve) => setTimeout(resolve, 350));
    });
    expect(mocks.request).toHaveBeenLastCalledWith("/admin/accounts?limit=25&q=chanda", {
      cache: "no-store",
    });
    const more = Array.from(host.querySelectorAll("button")).find(
      (node) => node.textContent === "admin.accountsUi.more",
    )!;
    await act(async () => more.click());
    expect(mocks.request).toHaveBeenLastCalledWith("/admin/accounts?limit=25&q=chanda&offset=25", {
      cache: "no-store",
    });
  });

  it("deactivates through a confirmation dialog that requires a reason", async () => {
    mocks.request.mockResolvedValue({ accounts: [chanda], total: 1, next_offset: null });
    await act(async () => root.render(<AccountsBoard locale="en" />));
    await vi.waitFor(() =>
      expect(host.querySelector('[data-testid="accounts-table"]')).toBeTruthy(),
    );
    const deactivate = Array.from(host.querySelectorAll("button")).find(
      (node) => node.textContent === "admin.accountsUi.deactivate",
    )!;
    await act(async () => deactivate.click());
    const confirm = document.querySelector<HTMLButtonElement>(
      '[data-testid="accounts-deactivate-confirm"]',
    )!;
    expect(confirm.disabled).toBe(true);
    await act(async () =>
      setValue(
        document.querySelector<HTMLTextAreaElement>('[data-testid="accounts-deactivate-reason"]')!,
        "Left the company",
      ),
    );
    expect(confirm.disabled).toBe(false);
    await act(async () => confirm.click());
    expect(mocks.request).toHaveBeenCalledWith(`/admin/accounts/${TARGET}/deactivate`, {
      method: "POST",
      body: JSON.stringify({ reason: "Left the company", confirmation: "DEACTIVATE" }),
    });
  });

  it("builds the directory query", () => {
    expect(accountsQuery("  ", 0)).toBe("limit=25");
    expect(accountsQuery(" ops ", 50)).toBe("limit=25&q=ops&offset=50");
  });
});
