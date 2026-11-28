// @vitest-environment jsdom
import { getRolesFromClaims } from "@vergeo/auth/roles";
import { NextRequest, NextResponse } from "next/server";
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { filterAdminNavGroups } from "../app/[locale]/_components/admin-nav-config";
import { AdminShell } from "../app/[locale]/_components/admin-shell";
import { OrderDetailView } from "../app/[locale]/orders/_components/OrderDetailView";
import middleware from "../middleware";

import { resolveAdminNavCapabilities } from "./admin-nav-capabilities";
import { ADMIN_GRANTS_REUSE_MS, loadAdminPermissions, type AdminPermissions } from "./roles-api";

const fixture = vi.hoisted(() => ({
  pathname: "/en/orders",
  translate: (key: string) => key,
  token: "local-unchanged-token",
  authChange: undefined as (() => void) | undefined,
  unsubscribe: vi.fn(),
  claims: {} as unknown,
  signedIn: true,
}));
vi.mock("next-intl/middleware", () => ({
  default: () => () => NextResponse.next(),
}));
vi.mock("@vergeo/auth/middleware", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@vergeo/auth/middleware")>();
  return {
    ...actual,
    updateSession: async () => ({
      response: NextResponse.next(),
      user: fixture.signedIn ? { id: "local-user" } : null,
      roles: getRolesFromClaims(fixture.claims),
    }),
  };
});
vi.mock("next/navigation", () => ({ usePathname: () => fixture.pathname }));
vi.mock("next-intl", () => ({ useTranslations: () => fixture.translate }));
vi.mock("next/link", () => ({ default: "a" }));
vi.mock("@vergeo/ui/src/theme-toggle", () => ({ ThemeToggle: () => null }));
// The notification bell polls its own API; these suites assert permission-shell fetches only.
vi.mock("../app/[locale]/_components/admin-notification-bell", () => ({
  AdminNotificationBell: () => null,
}));
vi.mock("../app/[locale]/_components/sign-out-button", () => ({
  SignOutButton: () => null,
}));
vi.mock("./access-token", () => ({ getBrowserAccessToken: () => fixture.token }));
vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({
    auth: {
      onAuthStateChange: (callback: () => void) => {
        fixture.authChange = callback;
        return { data: { subscription: { unsubscribe: fixture.unsubscribe } } };
      },
    },
  }),
}));

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

function visible(
  permissions: readonly string[] = [],
  unrestricted = false,
  canManageRoles = false,
) {
  return filterAdminNavGroups(
    resolveAdminNavCapabilities(permissions, unrestricted, canManageRoles),
  ).flatMap((group) => group.items.map((item) => item.key));
}

describe("admin navigation from current API permissions", () => {
  it("fails closed before grants or when permissions are unknown", () => {
    expect(visible()).toEqual([]);
    expect(visible(["payments.transfer", "admin", "rbac_finance"])).toEqual([]);
  });

  it.each([
    // Analytics: revenue dashboards need finance (D3), the rest analytics.read.
    ["finance.read", ["analytics", "orders"]],
    ["events.manage", ["catalog", "events"]],
    ["products.manage", ["moderation", "catalog"]],
    [
      "vendors.manage",
      [
        "kyc",
        "branches",
        "catalog",
        "intake",
        "business",
        "extras",
        "importRequests",
        "madeInZambia",
      ],
    ],
    ["ads.manage", ["merch", "homeFeed", "advertising", "offers"]],
    ["analytics.read", ["home", "analytics"]],
    ["services.read", ["services"]],
    ["inventory.read", ["inventory"]],
    // 2026-11 governance permissions.
    ["finance.operate", ["analytics", "disputes", "orders"]],
    ["support.manage", ["disputes", "support"]],
    ["services.manage", ["services"]],
    ["audit.read", ["auditLog"]],
    ["logistics.manage", ["dispatch"]],
  ])("bounds %s to its current destinations", (permission, expected) => {
    expect(visible([permission as string])).toEqual(expected);
  });

  it("combines multiple role permissions without adding global controls", () => {
    expect(visible(["finance.read", "products.manage", "vendors.manage", "finance.read"])).toEqual([
      "analytics",
      "kyc",
      "branches",
      "moderation",
      "catalog",
      "intake",
      "orders",
      "business",
      "extras",
      "importRequests",
      "madeInZambia",
    ]);
    const caps = resolveAdminNavCapabilities(["finance.read", "analytics.read"]);
    expect(caps.disputes).toBe(false);
    expect(caps.config).toBe(false);
    expect(caps.support).toBe(false);
    expect(caps.clips).toBe(false);
  });

  it("keeps legacy tools available to unrestricted admins independently of public flags", () => {
    const keys = visible([], true);
    expect(keys).toContain("clips");
    expect(keys).toContain("intake");
    expect(keys).toContain("config");
    expect(keys).toContain("disputes");
    expect(keys).toContain("coupons");
    expect(keys).toContain("askAudit");
    expect(keys).toContain("importRequests");
    expect(keys).toHaveLength(30);
    expect(keys).not.toContain("roles");
    expect(visible([], true, true)).toContain("roles");
  });

  it("never shows the audit log to unrestricted admins without audit.read", () => {
    expect(visible([], true)).not.toContain("auditLog");
    expect(visible([], true)).not.toContain("accounts");
    const superadmin = visible(["audit.read"], true, true);
    expect(superadmin).toContain("auditLog");
    expect(superadmin).toContain("accounts");
    expect(superadmin).toContain("roles");
  });

  it("removes previously visible items on role update and revocation", () => {
    expect(visible(["finance.read"])).toEqual(["analytics", "orders"]);
    expect(visible(["products.manage"])).toEqual(["moderation", "catalog"]);
    expect(visible([])).toEqual([]);
  });

  it("exposes read-only oversight while omitting empty groups and unauthorized role management", () => {
    expect(
      filterAdminNavGroups(resolveAdminNavCapabilities(["services.read", "inventory.read"])),
    ).toEqual([
      {
        key: "commerce",
        items: [
          { key: "services", href: "services" },
          { key: "inventory", href: "inventory" },
        ],
      },
    ]);
    const caps = resolveAdminNavCapabilities([], true);
    const groups = filterAdminNavGroups({
      ...caps,
      home: false,
      analytics: false,
    });
    expect(groups.some((group) => group.key === "overview")).toBe(false);
    expect(groups.length).toBeGreaterThan(0);
  });
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

function reply(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function grants(permissions: string[] = ["finance.read"], unrestricted = false): AdminPermissions {
  return { permissions, unrestricted, can_manage_roles: unrestricted };
}

let root: Root | undefined;
let container: HTMLDivElement;
let current: AdminPermissions;
let nextReply: Promise<Response> | undefined;
let calls: { path: string; init: RequestInit }[];

beforeEach(() => {
  fixture.pathname = "/en/orders";
  fixture.token = "local-unchanged-token";
  fixture.authChange = undefined;
  fixture.unsubscribe.mockClear();
  fixture.claims = {};
  fixture.signedIn = true;
  current = grants();
  nextReply = undefined;
  calls = [];
  container = document.createElement("div");
  document.body.append(container);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init: RequestInit = {}) => {
      calls.push({ path: input, init });
      if (input === "/admin/me/permissions") {
        const result = nextReply;
        nextReply = undefined;
        return result ?? reply(current);
      }
      if (input.startsWith("/admin/products/canonical")) {
        return reply([]);
      }
      if (input === "/admin/orders/local-order") {
        return reply({
          id: "local-order",
          status: "processing",
          fulfilment: "delivery",
          cod: false,
          delivery_fee_ngwee: 0,
          checkout_group_id: "local-group",
          vendor_id: "local-vendor",
          vendor_display_name: "Local vendor",
          vendor_slug: "local-vendor",
          customer_id: "local-customer",
          customer_phone: null,
          customer_display_name: null,
          created_at: "2026-10-12T00:00:00Z",
          items: [],
          payments: [
            {
              id: "local-payment",
              rail: "mtn",
              amount_ngwee: 0,
              status: "success",
              lenco_reference: "pay-local",
              created_at: "2026-10-12T00:00:00Z",
            },
          ],
          ledger: [],
          timeline: [],
        });
      }
      throw new Error("Forbidden external/resource operation in mounted fixture");
    }),
  );
});

afterEach(async () => {
  await act(async () => root?.unmount());
  container.remove();
  root = undefined;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function renderRoute(path: string, order = false) {
  fixture.pathname = path;
  root ??= createRoot(container);
  await act(async () => {
    root?.render(
      React.createElement(AdminShell, {
        locale: "en",
        children: order
          ? React.createElement(OrderDetailView, {
              locale: "en",
              orderId: "local-order",
            })
          : React.createElement("p", { "data-protected-route": path }, "Route content"),
      }),
    );
  });
}

async function refocus() {
  await act(async () => {
    window.dispatchEvent(new Event("focus"));
  });
}

function navHrefs() {
  return Array.from(container.querySelectorAll("nav a"), (node) => node.getAttribute("href"));
}

describe("mounted current-permission shell", () => {
  it("hides protected content and links during initial load, then accepts current grants", async () => {
    const request = deferred<Response>();
    nextReply = request.promise;
    await renderRoute("/en/orders");
    expect(container.querySelector('[role="status"]')?.textContent).toBe(
      "shell.permissionChecking",
    );
    expect(container.querySelector("[data-protected-route]")).toBeNull();
    expect(navHrefs()).toEqual([]);
    await act(async () => {
      request.resolve(reply(grants()));
    });
    expect(container.querySelector('[data-protected-route="/en/orders"]')).not.toBeNull();
    expect(navHrefs()).toEqual(["/en/analytics", "/en/orders"]);
    expect(calls[0]?.init.cache).toBe("no-store");
  });

  it.each(["network", "forbidden", "malformed"])(
    "fails closed on %s and recovers without a stale error",
    async (failure) => {
      if (failure === "network") {
        const request = deferred<Response>();
        nextReply = request.promise;
        await renderRoute("/en/orders");
        await act(async () => {
          request.reject(new Error("Local transport failure"));
        });
      } else {
        nextReply = Promise.resolve(
          failure === "forbidden"
            ? reply(
                {
                  error: {
                    code: "forbidden",
                    message: "Denied",
                    request_id: "local-only",
                  },
                },
                403,
              )
            : reply({ permissions: ["finance.read"], unrestricted: "true" }),
        );
        await renderRoute("/en/orders");
      }
      expect(container.querySelector('[role="alert"]')?.textContent).toBe("shell.permissionError");
      expect(container.querySelector("[data-protected-route]")).toBeNull();
      expect(navHrefs()).toEqual([]);
      await refocus();
      expect(container.querySelector('[data-protected-route="/en/orders"]')).not.toBeNull();
      expect(container.querySelector('[role="alert"]')).toBeNull();
    },
  );

  it("reloads updated, union and revoked grants using the unchanged token", async () => {
    await renderRoute("/en/orders");
    current = grants(["finance.read", "products.manage"]);
    await refocus();
    expect(navHrefs()).toEqual(["/en/analytics", "/en/moderation", "/en/catalog", "/en/orders"]);
    current = grants(["products.manage"]);
    await refocus();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("shell.permissionDenied");
    expect(container.querySelector("[data-protected-route]")).toBeNull();
    expect(navHrefs()).toEqual(["/en/moderation", "/en/catalog"]);
    current = grants([]);
    await refocus();
    expect(navHrefs()).toEqual([]);
    expect(
      calls
        .filter((c) => c.path === "/admin/me/permissions")
        .map((c) => new Headers(c.init.headers).get("Authorization")),
    ).toEqual(Array(4).fill("Bearer local-unchanged-token"));
  });

  it("rejects stale responses after navigation or a newer revalidation", async () => {
    const old = deferred<Response>();
    nextReply = old.promise;
    await renderRoute("/en/orders");
    current = grants(["products.manage"]);
    await renderRoute("/en/moderation");
    await act(async () => {
      old.resolve(reply(grants([], true)));
    });
    expect(navHrefs()).toEqual(["/en/moderation", "/en/catalog"]);
    expect(container.querySelector('[data-protected-route="/en/moderation"]')).not.toBeNull();
    const slower = deferred<Response>();
    nextReply = slower.promise;
    await refocus();
    // Refocus rechecks quietly: the page stays while the answer is pending.
    expect(container.querySelector("[data-protected-route]")).not.toBeNull();
    current = grants([]);
    await refocus();
    await act(async () => {
      slower.resolve(reply(grants([], true)));
    });
    expect(navHrefs()).toEqual([]);
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("shell.permissionDenied");
  });

  it("invalidates grants on an auth event before resolving the next account", async () => {
    current = grants([], true);
    await renderRoute("/en/orders");
    const switched = deferred<Response>();
    nextReply = switched.promise;
    await act(async () => {
      fixture.authChange?.();
      await new Promise((resolve) => window.setTimeout(resolve, 0));
    });
    expect(navHrefs()).toEqual([]);
    expect(container.querySelector("[data-protected-route]")).toBeNull();
    await act(async () => {
      switched.resolve(reply(grants([])));
    });
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("shell.permissionDenied");
  });

  it("never mounts unauthorized finance action panels and removes formerly allowed panels", async () => {
    await renderRoute("/en/orders", true);
    expect(container.textContent).toContain("local-order");
    expect(container.querySelector('[data-testid="dispatch-courier"]')).toBeNull();
    expect(container.querySelector('[data-testid="escrow-amount"]')).toBeNull();
    expect(
      container.querySelectorAll("main input, main select, main button:not([data-copy-button])"),
    ).toHaveLength(0);
    current = grants([], true);
    await refocus();
    expect(container.querySelector('[data-testid="dispatch-courier"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="escrow-amount"]')).not.toBeNull();
    current = grants();
    await refocus();
    expect(container.querySelector('[data-testid="dispatch-courier"]')).toBeNull();
    expect(container.querySelector('[data-testid="escrow-amount"]')).toBeNull();
    expect(calls.every((c) => !c.init.method || c.init.method === "GET")).toBe(true);
  });

  it("denies unknown/global-control routes even when another domain was granted", async () => {
    current = grants(["products.manage"]);
    for (const path of ["/en/roles", "/en/config", "/en/moderation/flags", "/en/unlisted"]) {
      await renderRoute(path);
      expect(container.querySelector('[role="alert"]')?.textContent).toBe("shell.permissionDenied");
      expect(container.querySelector("[data-protected-route]")).toBeNull();
    }
  });

  it("lets any admin open their own /notifications page without a nav permission", async () => {
    current = grants(["products.manage"]);
    await renderRoute("/en/notifications");
    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(container.querySelector('[data-protected-route="/en/notifications"]')).not.toBeNull();
    await renderRoute("/en/notifications/extra");
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("shell.permissionDenied");
  });

  it("keeps mounted chrome/login/recovery transitions stable in both directions", async () => {
    current = grants([], true);
    const errors = vi.spyOn(console, "error");
    for (const path of [
      "/en/orders",
      "/en/login",
      "/en/reset-password",
      "/en/reset-password/confirm",
      "/en/orders",
      "/en/reset-password/confirm",
      "/en/reset-password",
      "/en/login",
      "/en/orders",
    ]) {
      const before = calls.length;
      await renderRoute(path);
      expect(container.querySelector(`[data-protected-route="${path}"]`)).not.toBeNull();
      const bare = path !== "/en/orders";
      expect(container.querySelector("nav") === null).toBe(bare);
      expect(container.querySelector("[aria-controls]") === null).toBe(bare);
      if (bare) expect(calls.length).toBe(before);
    }
    expect(errors).not.toHaveBeenCalled();
    expect(fixture.unsubscribe).toHaveBeenCalled();
  });

  it.each(["/en/login", "/en/reset-password", "/en/reset-password/confirm"])(
    "cannot reuse an old unrestricted snapshot after visiting %s",
    async (bare) => {
      current = grants([], true);
      await renderRoute("/en/orders", true);
      expect(container.querySelector('[data-testid="escrow-amount"]')).not.toBeNull();
      await renderRoute(bare);
      const fresh = deferred<Response>();
      nextReply = fresh.promise;
      await renderRoute("/en/orders", true);
      expect(container.querySelector('[role="status"]')).not.toBeNull();
      expect(container.querySelector('[data-testid="escrow-amount"]')).toBeNull();
      expect(navHrefs()).toEqual([]);
      await act(async () => {
        fresh.resolve(reply(grants()));
      });
      expect(container.querySelector('[data-testid="escrow-amount"]')).toBeNull();
    },
  );

  it("closes the mobile dialog and unregisters Escape on recovery, then restores focus", async () => {
    current = grants([], true);
    const remove = vi.spyOn(window, "removeEventListener");
    await renderRoute("/en/orders");
    const button = container.querySelector<HTMLButtonElement>("button[aria-controls]")!;
    await act(async () => {
      button.click();
    });
    expect(container.querySelector('[role="dialog"]')).not.toBeNull();
    await renderRoute("/en/reset-password");
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(remove.mock.calls.some(([type]) => type === "keydown")).toBe(true);
    await renderRoute("/en/orders");
    const returned = container.querySelector<HTMLButtonElement>("button[aria-controls]")!;
    expect(returned.getAttribute("aria-expanded")).toBe("false");
    await act(async () => {
      returned.click();
    });
    await act(async () => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(document.activeElement).toBe(returned);
  });
});

describe("permission response contract", () => {
  it.each([
    null,
    {
      permissions: "finance.read",
      unrestricted: false,
      can_manage_roles: false,
    },
    {
      permissions: ["payments.transfer"],
      unrestricted: true,
      can_manage_roles: true,
    },
    {
      permissions: ["finance.read"],
      unrestricted: "true",
      can_manage_roles: false,
    },
    { permissions: ["finance.read"], unrestricted: false },
  ])("rejects malformed or unknown grants %#", async (value) => {
    nextReply = Promise.resolve(reply(value));
    await expect(loadAdminPermissions()).rejects.toThrow("Invalid admin permissions response");
  });
});

describe("platform shell admission preserves existing auth routes", () => {
  it.each(["admin", "superadmin", "moderator", "rbac_finance"])(
    "admits verified %s claims to the shell without assigning API authority",
    async (role) => {
      fixture.claims = { app_metadata: { roles: [role] } };
      const response = await middleware(new NextRequest("https://admin.example.invalid/en/orders"));
      expect(response.headers.get("location")).toBeNull();
      expect(calls).toEqual([]);
    },
  );

  it.each(["customer", "vendor", "vendor_staff", "rbac_!bad"])(
    "denies %s even with elevated user metadata",
    async (role) => {
      fixture.claims = {
        app_metadata: { roles: [role] },
        user_metadata: { roles: ["superadmin"] },
      };
      const response = await middleware(new NextRequest("https://admin.example.invalid/en/orders"));
      expect(new URL(response.headers.get("location")!).pathname).toBe("/en/permission-denied");
    },
  );

  it.each([
    "/en/login",
    "/en/reset-password",
    "/en/reset-password/confirm",
    "/en/permission-denied",
  ])(
    "keeps existing auth/informational route %s available without platform roles",
    async (path) => {
      fixture.signedIn = path === "/en/permission-denied";
      const response = await middleware(new NextRequest(`https://admin.example.invalid${path}`));
      expect(response.headers.get("location")).toBeNull();
      await renderRoute(path);
      expect(container.querySelector(`[data-protected-route="${path}"]`)).not.toBeNull();
      expect(container.querySelector("nav")).toBeNull();
      expect(calls).toEqual([]);
    },
  );
});

describe("route changes reuse confirmed grants while rechecking", () => {
  const permissionCalls = () => calls.filter((c) => c.path === "/admin/me/permissions");

  it("paints the next permitted route at once and still rechecks the API", async () => {
    current = grants(["finance.read", "products.manage"]);
    await renderRoute("/en/orders");
    expect(permissionCalls()).toHaveLength(1);
    const pending = deferred<Response>();
    nextReply = pending.promise;
    await renderRoute("/en/moderation");
    // No "checking permissions" gap: the page mounts (and can start its own fetch) now.
    expect(container.querySelector('[data-protected-route="/en/moderation"]')).not.toBeNull();
    expect(container.querySelector('[role="status"]')).toBeNull();
    expect(permissionCalls()).toHaveLength(2);
    await act(async () => pending.resolve(reply(current)));
    expect(container.querySelector('[data-protected-route="/en/moderation"]')).not.toBeNull();
  });

  it("still denies a route the reused grants do not cover", async () => {
    await renderRoute("/en/orders");
    const pending = deferred<Response>();
    nextReply = pending.promise;
    await renderRoute("/en/config");
    expect(container.querySelector("[data-protected-route]")).toBeNull();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("shell.permissionDenied");
    await act(async () => pending.resolve(reply(current)));
  });

  it("removes the page when the background recheck reports a revoked grant", async () => {
    current = grants(["finance.read", "products.manage"]);
    await renderRoute("/en/orders");
    current = grants(["finance.read"]);
    await renderRoute("/en/moderation");
    expect(container.querySelector("[data-protected-route]")).toBeNull();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("shell.permissionDenied");
  });

  it("fails closed when the background recheck is definitively refused", async () => {
    current = grants(["finance.read", "products.manage"]);
    await renderRoute("/en/orders");
    nextReply = Promise.resolve(
      reply({ error: { code: "forbidden", message: "Denied", request_id: "local-only" } }, 403),
    );
    await renderRoute("/en/moderation");
    expect(container.querySelector("[data-protected-route]")).toBeNull();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("shell.permissionError");
  });

  it("keeps the page through a transport blip, since the API stays authoritative", async () => {
    current = grants(["finance.read", "products.manage"]);
    await renderRoute("/en/orders");
    const pending = deferred<Response>();
    nextReply = pending.promise;
    await renderRoute("/en/moderation");
    await act(async () => pending.reject(new Error("Local transport failure")));
    expect(container.querySelector('[data-protected-route="/en/moderation"]')).not.toBeNull();
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  it("waits for fresh grants once the confirmation is older than the reuse window", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    try {
      current = grants(["finance.read", "products.manage"]);
      await renderRoute("/en/orders");
      vi.setSystemTime(Date.now() + ADMIN_GRANTS_REUSE_MS + 1_000);
      const pending = deferred<Response>();
      nextReply = pending.promise;
      await renderRoute("/en/moderation");
      expect(container.querySelector("[data-protected-route]")).toBeNull();
      expect(container.querySelector('[role="status"]')?.textContent).toBe(
        "shell.permissionChecking",
      );
      await act(async () => pending.resolve(reply(current)));
      expect(container.querySelector('[data-protected-route="/en/moderation"]')).not.toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("never reuses grants across sign-out or an account change", async () => {
    current = grants(["finance.read", "products.manage"]);
    await renderRoute("/en/orders");
    await renderRoute("/en/login");
    const pending = deferred<Response>();
    nextReply = pending.promise;
    await renderRoute("/en/moderation");
    expect(container.querySelector("[data-protected-route]")).toBeNull();
    expect(container.querySelector('[role="status"]')?.textContent).toBe(
      "shell.permissionChecking",
    );
    await act(async () => pending.resolve(reply(current)));
  });
});

describe("refocus rechecks grants quietly", () => {
  const typed = () => container.querySelector<HTMLInputElement>("input[data-draft]");

  async function renderWithForm(path: string) {
    fixture.pathname = path;
    root ??= createRoot(container);
    await act(async () => {
      root?.render(
        React.createElement(AdminShell, {
          locale: "en",
          children: React.createElement(
            "div",
            { "data-protected-route": path },
            React.createElement("input", { "data-draft": "", defaultValue: "" }),
          ),
        }),
      );
    });
    const input = typed()!;
    input.value = "half-written reject reason";
  }

  it("keeps the page and its form state when the grants are unchanged", async () => {
    current = grants(["finance.read", "products.manage"]);
    await renderWithForm("/en/moderation");
    const pending = deferred<Response>();
    nextReply = pending.promise;
    await refocus();
    expect(typed()?.value).toBe("half-written reject reason");
    await act(async () => pending.resolve(reply(current)));
    expect(typed()?.value).toBe("half-written reject reason");
  });

  it("removes the page when the recheck returns fewer grants", async () => {
    current = grants(["finance.read", "products.manage"]);
    await renderWithForm("/en/moderation");
    current = grants(["finance.read"]);
    await refocus();
    expect(typed()).toBeNull();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("shell.permissionDenied");
  });

  it.each([401, 403])("removes the page on a %s answer", async (status) => {
    current = grants(["finance.read", "products.manage"]);
    await renderWithForm("/en/moderation");
    nextReply = Promise.resolve(
      reply({ error: { code: "forbidden", message: "Denied", request_id: "local-only" } }, status),
    );
    await refocus();
    expect(typed()).toBeNull();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("shell.permissionError");
  });

  it("keeps the page through a network error", async () => {
    current = grants(["finance.read", "products.manage"]);
    await renderWithForm("/en/moderation");
    const pending = deferred<Response>();
    nextReply = pending.promise;
    await refocus();
    await act(async () => pending.reject(new Error("Local transport failure")));
    expect(typed()?.value).toBe("half-written reject reason");
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });
});

describe("logistics.manage reaches the dispatch board and order detail only", () => {
  it("shows a Dispatch nav item and opens /orders/dispatch", async () => {
    current = grants(["logistics.manage"]);
    await renderRoute("/en/orders/dispatch");
    expect(container.querySelector('[data-protected-route="/en/orders/dispatch"]')).not.toBeNull();
    expect(navHrefs()).toEqual(["/en/orders/dispatch"]);
  });

  it("opens an order detail page, but not order search", async () => {
    current = grants(["logistics.manage"]);
    await renderRoute("/en/orders/some-order");
    expect(
      container.querySelector('[data-protected-route="/en/orders/some-order"]'),
    ).not.toBeNull();
    await renderRoute("/en/orders");
    expect(container.querySelector("[data-protected-route]")).toBeNull();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("shell.permissionDenied");
  });

  it("does not hand finance roles the dispatch board the API refuses them", async () => {
    current = grants(["finance.read", "finance.operate"]);
    await renderRoute("/en/orders/dispatch");
    expect(container.querySelector("[data-protected-route]")).toBeNull();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("shell.permissionDenied");
    await renderRoute("/en/orders/some-order");
    expect(
      container.querySelector('[data-protected-route="/en/orders/some-order"]'),
    ).not.toBeNull();
  });

  it("keeps every other destination closed to a logistics-only role", async () => {
    current = grants(["logistics.manage"]);
    for (const path of ["/en", "/en/config", "/en/kyc", "/en/disputes", "/en/analytics"]) {
      await renderRoute(path);
      expect(container.querySelector("[data-protected-route]")).toBeNull();
    }
  });
});

describe("explicit-grant destinations are denied by URL, not only hidden", () => {
  it.each(["/en/roles", "/en/accounts", "/en/audit-log"])(
    "denies %s to an unrestricted admin who lacks the explicit grant",
    async (path) => {
      current = grants([], true);
      current.can_manage_roles = false;
      await renderRoute(path);
      expect(container.querySelector("[data-protected-route]")).toBeNull();
      expect(container.querySelector('[role="alert"]')?.textContent).toBe("shell.permissionDenied");
    },
  );

  it("opens them for a superadmin holding every grant", async () => {
    current = {
      permissions: ["audit.read"],
      unrestricted: true,
      can_manage_roles: true,
    };
    for (const path of ["/en/roles", "/en/accounts", "/en/audit-log"]) {
      await renderRoute(path);
      expect(container.querySelector(`[data-protected-route="${path}"]`)).not.toBeNull();
    }
  });

  it("opens the audit log to a restricted role holding audit.read only", async () => {
    current = grants(["audit.read"]);
    await renderRoute("/en/audit-log");
    expect(container.querySelector('[data-protected-route="/en/audit-log"]')).not.toBeNull();
  });
});
