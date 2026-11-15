// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminShell } from "./admin-shell";

import type { Root } from "react-dom/client";

let pathname = "/en";
let holdPermissions: Promise<void> | null = null;

vi.mock("@vergeo/auth", () => ({ getBrowserAccessToken: () => "local-only-token" }));
vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({
    auth: {
      getSession: async () => ({
        data: {
          session: {
            user: { email: "amina@example.com", user_metadata: { full_name: "Amina Banda" } },
          },
        },
      }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: vi.fn() } } }),
    },
  }),
}));
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));
vi.mock("next-intl", () => ({
  useTranslations: (namespace?: string) => (key: string) =>
    namespace && namespace !== "admin" ? `${namespace}.${key}` : key,
}));
vi.mock("next/link", () => ({ default: "a" }));
vi.mock("@vergeo/ui/src/theme-toggle", () => ({ ThemeToggle: () => null }));
vi.mock("./admin-notification-bell", () => ({ AdminNotificationBell: () => null }));
vi.mock("./sign-out-button", () => ({ SignOutButton: () => null }));

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

let root: Root | undefined;
let container: HTMLDivElement | undefined;

beforeEach(() => {
  holdPermissions = null;
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      await holdPermissions;
      return new Response(
        JSON.stringify({ permissions: [], unrestricted: true, can_manage_roles: true }),
        { headers: { "content-type": "application/json" } },
      );
    }),
  );
});

afterEach(async () => {
  await act(async () => root?.unmount());
  container?.remove();
  root = undefined;
  container = undefined;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function render(path: string) {
  pathname = path;
  if (!container) {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
  }
  await act(async () => {
    root?.render(
      <AdminShell locale="en">
        <p>Route content</p>
      </AdminShell>,
    );
  });
}

describe("AdminShell account chip", () => {
  it("shows the signed-in admin's name and role", async () => {
    await render("/en");
    const name = container?.querySelector('[data-testid="admin-account-name"]');
    const role = container?.querySelector('[data-testid="admin-account-role"]');
    expect(name?.textContent).toBe("Amina Banda");
    expect(role?.textContent).toBe("admin.shell.account.roles.superadmin");
  });
});

describe("AdminShell sidebar", () => {
  it("is its own scroll container and marks the active item", async () => {
    await render("/en/kyc");
    const nav = container?.querySelector<HTMLElement>('[data-testid="admin-sidebar"]');
    expect(nav?.className).toContain("overflow-y-auto");
    const main = container?.querySelector<HTMLElement>('[data-testid="admin-main"]');
    expect(main?.className).toContain("overflow-y-auto");
    const current = nav?.querySelectorAll('[aria-current="page"]');
    expect(current?.length).toBe(1);
    expect(current?.[0]?.textContent).toBe("nav.kyc");
  });

  it("keeps the nav mounted and its scroll position while permissions reload on navigation", async () => {
    await render("/en/kyc");
    const nav = container?.querySelector<HTMLElement>('[data-testid="admin-sidebar"]');
    expect(nav).toBeTruthy();
    if (!nav) return;
    nav.scrollTop = 120;
    await act(async () => {
      nav.dispatchEvent(new Event("scroll", { bubbles: true }));
    });

    let release: () => void = () => {};
    holdPermissions = new Promise<void>((resolve) => {
      release = resolve;
    });
    await render("/en/orders");

    const navDuring = container?.querySelector<HTMLElement>('[data-testid="admin-sidebar"]');
    expect(navDuring).toBe(nav);
    expect(navDuring?.querySelectorAll("a").length).toBeGreaterThan(5);
    expect(navDuring?.querySelector('[aria-current="page"]')?.textContent).toBe("nav.orders");
    expect(navDuring?.scrollTop).toBe(120);

    await act(async () => release());
    expect(container?.querySelector('[data-testid="admin-sidebar"]')).toBe(nav);
    expect(nav.scrollTop).toBe(120);
  });
});
