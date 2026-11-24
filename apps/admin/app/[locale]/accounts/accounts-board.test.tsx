// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AccountsBoard } from "./accounts-board";

const mocks = vi.hoisted(() => ({
  request: vi.fn(),
  grants: { user_id: "self", can_manage_roles: true, permissions: [], unrestricted: true },
}));
vi.mock("next-intl", () => ({ useTranslations: (ns: string) => (key: string) => `${ns}.${key}` }));
vi.mock("../../../lib/roles-api", () => ({
  rolesApi: { request: mocks.request },
  useAdminPermissions: () => mocks.grants,
}));
vi.mock("@vergeo/auth", () => ({ getBrowserAccessToken: async () => "t" }));
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
let root: ReturnType<typeof createRoot>;
let host: HTMLDivElement;

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
});
