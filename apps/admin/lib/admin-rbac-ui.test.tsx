// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminShell } from "../app/[locale]/_components/admin-shell";
import { OversightList } from "../app/[locale]/_components/oversight-list";
import { ModerationDestinations } from "../app/[locale]/moderation/moderation-destinations";
import { RolesBoard } from "../app/[locale]/roles/roles-board";

import {
  AdminPermissionsContext,
  type AdminPermissions,
  type AdminRole,
  type AdminRoleAssignment,
} from "./roles-api";

const fixture = vi.hoisted(() => ({
  pathname: "/en/roles",
  account: "manager",
  authChange: undefined as (() => void) | undefined,
}));
vi.mock("next/navigation", () => ({ usePathname: () => fixture.pathname }));
vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));
vi.mock("next/link", () => ({ default: "a" }));
vi.mock("@vergeo/ui/src/theme-toggle", () => ({ ThemeToggle: () => null }));
vi.mock("../app/[locale]/_components/sign-out-button", () => ({
  SignOutButton: () => null,
}));
vi.mock("@vergeo/auth", () => ({
  getBrowserAccessToken: () => `fixture-${fixture.account}-unchanged-token`,
}));
vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({
    auth: {
      onAuthStateChange: (callback: () => void) => {
        fixture.authChange = callback;
        return { data: { subscription: { unsubscribe: () => {} } } };
      },
    },
  }),
}));
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

const targetId = "00000000-0000-4000-8000-000000000002";
const manager: AdminPermissions = {
  permissions: [],
  unrestricted: true,
  can_manage_roles: true,
};
const legacy: AdminPermissions = { ...manager, can_manage_roles: false };
const restricted = (permissions: string[]): AdminPermissions => ({
  permissions,
  unrestricted: false,
  can_manage_roles: false,
});
const destinations = [
  {
    key: "products",
    href: "/en/moderation/products",
    title: "Fixture products",
    body: "Fixture moderation",
  },
  {
    key: "canonical",
    href: "/en/moderation/products#canonical",
    title: "Fixture canonical",
    body: "Fixture canonical review",
  },
  {
    key: "flags",
    href: "/en/moderation/flags",
    title: "Fixture flags",
    body: "Fixture global controls",
  },
];

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
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

let root: Root | undefined;
let container: HTMLDivElement;
let roles: AdminRole[];
let assignments: AdminRoleAssignment[];
let managerGrants: AdminPermissions;
let calls: { path: string; method: string; init: RequestInit }[];
let overrides: { path: string; method: string; response: Promise<Response> }[];
let failMutation: boolean;

function currentGrants() {
  if (fixture.account === "manager") return managerGrants;
  const assigned = assignments.filter((row) => row.user_id === targetId).map((row) => row.role);
  return restricted([
    ...new Set(
      roles.filter((role) => assigned.includes(role.key)).flatMap((role) => role.permissions),
    ),
  ]);
}

beforeEach(() => {
  fixture.pathname = "/en/roles";
  fixture.account = "manager";
  fixture.authChange = undefined;
  managerGrants = manager;
  roles = [];
  assignments = [];
  calls = [];
  overrides = [];
  failMutation = false;
  container = document.createElement("div");
  document.body.append(container);
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init: RequestInit = {}) => {
      const method = init.method ?? "GET";
      calls.push({ path, method, init });
      const index = overrides.findIndex((value) => value.path === path && value.method === method);
      if (index >= 0) return overrides.splice(index, 1)[0]!.response;
      if (path === "/admin/me/permissions" && method === "GET") return reply(currentGrants());
      if (path === "/admin/services" || path === "/admin/inventory") {
        if (method !== "GET") throw new Error("Read-only oversight mutation forbidden");
        return reply({ items: [] });
      }
      if (!path.startsWith("/admin/roles"))
        throw new Error("Unexpected external operation in local fixture");
      if (!currentGrants().can_manage_roles) return reply({ detail: "forbidden" }, 403);
      if (path === "/admin/roles" && method === "GET") return reply({ roles, assignments });
      if (failMutation) return reply({ detail: "fixture_sensitive_backend_error" }, 409);
      if (path === "/admin/roles" && method === "POST") {
        roles.push(JSON.parse(String(init.body)) as AdminRole);
        return reply({ ok: true }, 201);
      }
      const parts = path.split("/");
      const roleKey = parts[3]!;
      if (parts[4] === "users" && (method === "PUT" || method === "DELETE")) {
        const userId = parts[5]!;
        assignments = assignments.filter(
          (row) => !(row.role === roleKey && row.user_id === userId),
        );
        if (method === "PUT") assignments.push({ role: roleKey, user_id: userId });
        return reply({ ok: true });
      }
      if (method === "PATCH") {
        roles = roles.map((role) =>
          role.key === roleKey ? { ...role, ...JSON.parse(String(init.body)) } : role,
        );
        return reply({ ok: true });
      }
      if (method === "DELETE") {
        roles = roles.filter((role) => role.key !== roleKey);
        return reply({ ok: true });
      }
      throw new Error("Unexpected role operation in local fixture");
    }),
  );
});
afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  container.remove();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function render(node: React.ReactNode) {
  root ??= createRoot(container);
  await act(async () => root?.render(node));
}
async function shell(path = "/en/roles", child: React.ReactNode = <RolesBoard />) {
  fixture.pathname = path;
  await render(<AdminShell locale="en">{child}</AdminShell>);
}
async function standalone(node: React.ReactNode, grants: AdminPermissions | null = manager) {
  await render(
    <AdminPermissionsContext.Provider value={grants}>{node}</AdminPermissionsContext.Provider>,
  );
}
function button(key: string) {
  const result = Array.from(container.querySelectorAll("button")).find(
    (node) => node.textContent === key,
  );
  if (!result) throw new Error(`Missing button ${key}`);
  return result;
}
function form(key: string) {
  const result = container.querySelector<HTMLFormElement>(
    `form[aria-label="admin.rolesUi.${key}"]`,
  );
  if (!result) throw new Error(`Missing form ${key}`);
  return result;
}
async function change(node: HTMLInputElement | HTMLSelectElement, value: string) {
  await act(async () => {
    const proto =
      node instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(node, value);
    node.dispatchEvent(
      new Event(node instanceof HTMLSelectElement ? "change" : "input", {
        bubbles: true,
      }),
    );
  });
}
async function click(node: HTMLElement) {
  await act(async () => node.click());
}
async function submit(node: HTMLFormElement) {
  await act(async () =>
    node.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
  );
}
async function fillRole(key: string, name: string, permissions: string[]) {
  const create = form("createHeading");
  const inputs = create.querySelectorAll<HTMLInputElement>('input:not([type="checkbox"])');
  await change(inputs[0]!, key);
  await change(inputs[1]!, name);
  for (const permission of permissions) {
    const label = Array.from(create.querySelectorAll("label")).find(
      (node) => node.textContent === permission,
    )!;
    await click(label.querySelector("input")!);
  }
}
async function assign(roleKey: string) {
  const assignForm = form("assignHeading");
  await change(assignForm.querySelector("input")!, targetId);
  await change(assignForm.querySelector("select")!, roleKey);
  await submit(assignForm);
}
const mutations = () => calls.filter((call) => call.method !== "GET");
const permissionCalls = () => calls.filter((call) => call.path === "/admin/me/permissions");
const nav = () =>
  Array.from(container.querySelectorAll("nav a"), (node) => node.getAttribute("href"));

describe("role forms and mutation lifecycle through the current permission shell", () => {
  it("shows loading without actionable forms, then distinct empty roles and assignments", async () => {
    const pending = deferred<Response>();
    overrides.push({
      path: "/admin/roles",
      method: "GET",
      response: pending.promise,
    });
    await shell();
    expect(container.querySelector('[role="status"]')?.textContent).toBe("admin.rolesUi.loading");
    expect(container.querySelector("form")).toBeNull();
    expect(container.textContent).not.toContain("admin.rolesUi.emptyRoles");
    await act(async () => pending.resolve(reply({ roles: [], assignments: [] })));
    expect(container.textContent).toContain("admin.rolesUi.emptyRoles");
    expect(container.textContent).toContain("admin.rolesUi.emptyAssignments");
    expect(form("createHeading")).toBeTruthy();
    expect(button("admin.rolesUi.create").disabled).toBe(true);
  });

  it.each(["network", "forbidden", "malformed"])(
    "fails closed on %s role loading and retries safely",
    async (failure) => {
      const response =
        failure === "network"
          ? Promise.reject(new Error("fixture_sensitive_transport_error")).catch((error) => {
              throw error;
            })
          : Promise.resolve(
              reply(
                failure === "forbidden"
                  ? { detail: "fixture_sensitive_backend_error" }
                  : { roles: null, assignments: [] },
                failure === "forbidden" ? 403 : 200,
              ),
            );
      void response.catch(() => {});
      overrides.push({ path: "/admin/roles", method: "GET", response });
      await shell();
      expect(container.querySelector('[role="alert"]')?.textContent).toBe(
        "admin.rolesUi.loadFailed",
      );
      expect(container.querySelector("form")).toBeNull();
      expect(container.textContent).not.toContain("fixture_sensitive");
      await click(button("admin.rolesUi.retry"));
      expect(form("createHeading")).toBeTruthy();
      expect(container.querySelector('[role="alert"]')).toBeNull();
      expect(mutations()).toEqual([]);
    },
  );

  it("creates two independent roles, assigns both, then reads their API union and same-token revocation", async () => {
    await shell();
    await fillRole("finance", "Fixture finance", ["finance.read"]);
    await submit(form("createHeading"));
    await fillRole("catalog", "Fixture catalog", ["products.manage", "services.read"]);
    await submit(form("createHeading"));
    expect(roles).toEqual([
      {
        key: "rbac_finance",
        name: "Fixture finance",
        permissions: ["finance.read"],
      },
      {
        key: "rbac_catalog",
        name: "Fixture catalog",
        permissions: ["products.manage", "services.read"],
      },
    ]);
    await assign("rbac_finance");
    await assign("rbac_catalog");
    expect(assignments).toHaveLength(2);
    expect(mutations().map((call) => call.method)).toEqual(["POST", "POST", "PUT", "PUT"]);
    expect(permissionCalls()).toHaveLength(5);
    expect(permissionCalls().every((call) => call.init.cache === "no-store")).toBe(true);
    expect(
      mutations().every(
        (call) =>
          new Headers(call.init.headers).get("authorization") ===
          "Bearer fixture-manager-unchanged-token",
      ),
    ).toBe(true);

    fixture.account = "target";
    await shell("/en/orders", <p data-target-content>Fixture order read</p>);
    expect(nav()).toEqual(["/en/moderation", "/en/orders", "/en/services"]);
    expect(container.querySelector("[data-target-content]")).not.toBeNull();
    // A separately authorized actor revokes the synthetic row in this fixture.
    // The restricted browser performs only its normal permission recheck.
    assignments = assignments.filter((row) => row.role !== "rbac_finance");
    const before = mutations().length;
    await act(async () => window.dispatchEvent(new Event("focus")));
    expect(nav()).toEqual(["/en/moderation", "/en/services"]);
    expect(container.querySelector("[data-target-content]")).toBeNull();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe(
      "admin.shell.permissionDenied",
    );
    expect(new Headers(permissionCalls().at(-1)?.init.headers).get("authorization")).toBe(
      "Bearer fixture-target-unchanged-token",
    );
    expect(mutations()).toHaveLength(before);
  });

  it("invalidates grants immediately after a revoke, then reloads assignments with the same JWT", async () => {
    roles = [
      {
        key: "rbac_finance",
        name: "Fixture finance",
        permissions: ["finance.read"],
      },
    ];
    assignments = [{ user_id: targetId, role: "rbac_finance" }];
    await shell();
    const pending = deferred<Response>();
    overrides.push({
      path: "/admin/me/permissions",
      method: "GET",
      response: pending.promise,
    });
    await click(button("admin.rolesUi.revoke"));
    expect(mutations()).toHaveLength(1);
    expect(mutations()[0]?.path).toBe(`/admin/roles/rbac_finance/users/${targetId}`);
    expect(container.querySelector('[role="status"]')?.textContent).toBe(
      "admin.shell.permissionChecking",
    );
    expect(container.querySelector("form")).toBeNull();
    expect(nav()).toEqual([]);
    expect(assignments).toEqual([]);
    await act(async () => pending.resolve(reply(manager)));
    expect(container.textContent).toContain("admin.rolesUi.emptyAssignments");
    expect(container.textContent).not.toContain(targetId);
    expect(permissionCalls()).toHaveLength(2);
    expect(new Headers(permissionCalls()[1]!.init.headers).get("authorization")).toBe(
      "Bearer fixture-manager-unchanged-token",
    );
  });

  it("removes the board when mutation refresh returns revoked role-management authority", async () => {
    roles = [
      {
        key: "rbac_finance",
        name: "Fixture finance",
        permissions: ["finance.read"],
      },
    ];
    assignments = [{ user_id: targetId, role: "rbac_finance" }];
    await shell();
    overrides.push({
      path: "/admin/me/permissions",
      method: "GET",
      response: Promise.resolve(reply(legacy)),
    });
    await click(button("admin.rolesUi.revoke"));
    expect(container.querySelector("form")).toBeNull();
    expect(nav()).not.toContain("/en/roles");
    expect(container.querySelector('[role="alert"]')?.textContent).toBe(
      "admin.shell.permissionDenied",
    );
    expect(
      calls.filter((call) => call.path === "/admin/roles" && call.method === "GET"),
    ).toHaveLength(1);
  });

  it("holds a synchronous mutation guard across duplicate submissions and delayed responses", async () => {
    await shell();
    await fillRole("finance", "Fixture finance", ["finance.read"]);
    const pending = deferred<Response>();
    overrides.push({
      path: "/admin/roles",
      method: "POST",
      response: pending.promise,
    });
    const create = form("createHeading");
    await act(async () => {
      create.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      create.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    expect(mutations()).toHaveLength(1);
    expect(button("admin.rolesUi.create").disabled).toBe(true);
    expect(form("assignHeading").querySelector("select")?.disabled).toBe(true);
    await act(async () => pending.resolve(reply({ ok: true }, 201)));
    expect(permissionCalls()).toHaveLength(2);
    expect(mutations()).toHaveLength(1);
  });

  it.each(["create", "edit", "assign", "delete", "revoke"])(
    "keeps confirmed state and exposes a localized %s failure without refreshing grants",
    async (operation) => {
      roles = [
        {
          key: "rbac_finance",
          name: "Fixture finance",
          permissions: ["finance.read"],
        },
      ];
      assignments = [{ user_id: targetId, role: "rbac_finance" }];
      await shell();
      failMutation = true;
      if (operation === "create") {
        await fillRole("catalog", "Fixture catalog", ["products.manage"]);
        await submit(form("createHeading"));
      } else if (operation === "edit") {
        await click(button("admin.rolesUi.edit"));
        const editing = container.querySelector<HTMLFormElement>(
          'form[aria-label="admin.rolesUi.editHeading"]',
        )!;
        await change(
          editing.querySelectorAll<HTMLInputElement>('input:not([type="checkbox"])')[1]!,
          "Changed fixture name",
        );
        await submit(editing);
      } else if (operation === "assign") await assign("rbac_finance");
      else await click(button(`admin.rolesUi.${operation}`));
      expect(container.querySelector('[role="alert"]')?.textContent).toBe(
        "admin.rolesUi.mutationFailed",
      );
      expect(container.textContent).not.toContain("fixture_sensitive_backend_error");
      expect(roles).toEqual([
        {
          key: "rbac_finance",
          name: "Fixture finance",
          permissions: ["finance.read"],
        },
      ]);
      expect(assignments).toEqual([{ user_id: targetId, role: "rbac_finance" }]);
      expect(permissionCalls()).toHaveLength(1);
      expect(mutations()).toHaveLength(1);
      expect(button("admin.rolesUi.delete").disabled).toBe(false);
    },
  );

  it("retains edit, cancel, deletion, and superadmin confirmation contracts", async () => {
    roles = [
      {
        key: "rbac_finance",
        name: "Fixture finance",
        permissions: ["finance.read"],
      },
    ];
    await shell();
    await click(button("admin.rolesUi.edit"));
    const editing = container.querySelector<HTMLFormElement>(
      'form[aria-label="admin.rolesUi.editHeading"]',
    )!;
    expect(editing.querySelector("input")?.disabled).toBe(true);
    await change(
      editing.querySelectorAll<HTMLInputElement>('input:not([type="checkbox"])')[1]!,
      "Updated fixture finance",
    );
    await submit(editing);
    expect(roles[0]?.name).toBe("Updated fixture finance");
    await click(button("admin.rolesUi.edit"));
    await click(button("admin.rolesUi.cancel"));
    expect(form("createHeading").querySelector("input")?.value).toBe("");
    vi.mocked(window.confirm).mockReturnValue(false);
    await click(button("admin.rolesUi.delete"));
    await assign("superadmin");
    expect(mutations()).toHaveLength(1);
    expect(window.confirm).toHaveBeenCalledWith("admin.rolesUi.confirmDelete");
    expect(window.confirm).toHaveBeenCalledWith("admin.rolesUi.confirmSuperadmin");
    vi.mocked(window.confirm).mockReturnValue(true);
    await click(button("admin.rolesUi.delete"));
    expect(roles).toEqual([]);
  });

  it.each([null, legacy, restricted(["finance.read", "products.manage"])])(
    "exposes no role forms or requests to an unauthorized snapshot %j",
    async (grants) => {
      await standalone(<RolesBoard />, grants);
      expect(container.querySelector('[role="alert"]')?.textContent).toBe(
        "admin.rolesUi.permissionDenied",
      );
      expect(container.querySelector("form")).toBeNull();
      expect(calls).toEqual([]);
    },
  );

  it("denies role-management navigation to legacy admins with broad unrelated access", async () => {
    managerGrants = legacy;
    await shell();
    expect(nav()).not.toContain("/en/roles");
    expect(nav()).toContain("/en/config");
    expect(container.querySelector("form")).toBeNull();
    expect(calls.filter((call) => call.path === "/admin/roles")).toEqual([]);
  });

  it("ignores an old role response after permission loss and a newer response wins", async () => {
    const old = deferred<Response>();
    overrides.push({
      path: "/admin/roles",
      method: "GET",
      response: old.promise,
    });
    await standalone(<RolesBoard />);
    await standalone(<RolesBoard />, legacy);
    roles = [
      {
        key: "rbac_catalog",
        name: "New fixture catalog",
        permissions: ["products.manage"],
      },
    ];
    await standalone(<RolesBoard />);
    await act(async () =>
      old.resolve(
        reply({
          roles: [{ key: "rbac_stale", name: "Old fixture role", permissions: [] }],
          assignments: [],
        }),
      ),
    );
    expect(container.textContent).toContain("New fixture catalog");
    expect(container.textContent).not.toContain("Old fixture role");
  });
});

describe("read-only oversight and moderation destinations", () => {
  it.each(["services", "inventory"] as const)(
    "distinguishes %s loading, errors, retry, and empty results",
    async (kind) => {
      const pending = deferred<Response>();
      overrides.push({
        path: `/admin/${kind}`,
        method: "GET",
        response: pending.promise,
      });
      await shell(`/en/${kind}`, <OversightList kind={kind} />);
      expect(container.querySelector('[role="status"]')?.textContent).toBe(
        "admin.oversightUi.loading",
      );
      expect(container.textContent).not.toContain("admin.oversightUi.empty");
      await act(async () => pending.resolve(reply({ detail: "fixture_sensitive_error" }, 500)));
      expect(container.querySelector('[role="alert"]')?.textContent).toBe(
        "admin.oversightUi.loadFailed",
      );
      await click(button("admin.oversightUi.retry"));
      expect(container.textContent).toContain("admin.oversightUi.empty");
      expect(container.querySelector('[role="alert"]')).toBeNull();
      expect(mutations()).toEqual([]);
      expect(
        calls
          .filter((call) => call.path === `/admin/${kind}`)
          .every((call) => call.init.cache === "no-store"),
      ).toBe(true);
    },
  );

  it("rejects an old kind's response and clears its error before showing the new read-only records", async () => {
    const old = deferred<Response>();
    overrides.push({
      path: "/admin/services",
      method: "GET",
      response: old.promise,
    });
    await standalone(<OversightList kind="services" />);
    overrides.push({
      path: "/admin/inventory",
      method: "GET",
      response: Promise.resolve(
        reply({
          items: [
            {
              id: "fixture-stock",
              vendor_id: "fixture-vendor",
              status: "active",
              title_override: "Fixture inventory item",
              stock_qty: 0,
            },
          ],
        }),
      ),
    });
    await standalone(<OversightList kind="inventory" />);
    await act(async () => old.resolve(reply({ detail: "old fixture failure" }, 500)));
    expect(container.textContent).toContain("Fixture inventory item");
    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(container.querySelector("button")).toBeNull();
    expect(mutations()).toEqual([]);
  });

  it.each(["services", "inventory"] as const)(
    "makes no %s request without the matching read grant",
    async (kind) => {
      await standalone(<OversightList kind={kind} />, restricted(["products.manage"]));
      expect(container.querySelector('[role="alert"]')?.textContent).toBe(
        "admin.oversightUi.permissionDenied",
      );
      expect(calls).toEqual([]);
    },
  );

  it("uses the shell snapshot to remove global flags and all destinations after revocation", async () => {
    await shell("/en/moderation", <ModerationDestinations destinations={destinations} />);
    expect(container.querySelector('a[href="/en/moderation/flags"]')).not.toBeNull();
    managerGrants = restricted(["products.manage"]);
    await act(async () => window.dispatchEvent(new Event("focus")));
    expect(container.querySelector('a[href="/en/moderation/flags"]')).toBeNull();
    expect(container.querySelector('a[href="/en/moderation/products"]')).not.toBeNull();
    managerGrants = restricted([]);
    await act(async () => window.dispatchEvent(new Event("focus")));
    expect(container.querySelector('a[href="/en/moderation/products"]')).toBeNull();
    expect(calls.every((call) => call.path === "/admin/me/permissions")).toBe(true);
    expect(permissionCalls()).toHaveLength(3);
  });
});
