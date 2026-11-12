// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminPermissionsContext, type AdminPermissions } from "../../../../lib/roles-api";

const api = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));
vi.mock("@vergeo/auth", () => ({ getBrowserAccessToken: () => "token" }));
vi.mock("@vergeo/auth/browser-client-lazy", () => ({ getBrowserClient: async () => ({}) }));
vi.mock("@vergeo/ui/src/toast", () => ({ notify: { success: vi.fn(), error: vi.fn() } }));
vi.mock("./catalog-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./catalog-api")>();
  return { ...actual, catalogApi: { request: api.request } };
});

import { CatalogControlBoard } from "./CatalogControlBoard";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

const listing = {
  kind: "listing",
  id: "11111111-1111-4111-8111-111111111111",
  label: "Phone",
  status: "active",
  vendor_id: "v1",
  visible: true,
  href: "/l/11111111-1111-4111-8111-111111111111",
  hold: null,
};

let container: HTMLDivElement;
let root: Root;

async function render(grants: AdminPermissions) {
  await act(async () => {
    root.render(
      <AdminPermissionsContext.Provider value={grants}>
        <CatalogControlBoard locale="en" />
      </AdminPermissionsContext.Provider>,
    );
  });
}

function button(label: string): HTMLButtonElement {
  const found = Array.from(document.querySelectorAll("button")).find(
    (node) => node.textContent === label,
  );
  if (!found) throw new Error(`button ${label} not found`);
  return found as HTMLButtonElement;
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

describe("CatalogControlBoard", () => {
  it("hides a listing only after a reason is given, via the guarded moderate endpoint", async () => {
    api.request.mockResolvedValue([listing]);
    await render({
      permissions: ["products.manage"],
      unrestricted: false,
      can_manage_roles: false,
    });
    expect(api.request).toHaveBeenCalledWith("/admin/catalog/listings", { cache: "no-store" });
    expect(container.textContent).toContain("Phone");
    expect(container.textContent).toContain("admin.catalog.visible");

    await act(async () => button("admin.catalog.actions.hide").click());
    const confirm = document.querySelector(
      '[data-testid="catalog-confirm-confirm"]',
    ) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);

    const reason = document.querySelector("textarea") as HTMLTextAreaElement;
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
      setter?.call(reason, "Counterfeit report confirmed");
      reason.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(confirm.disabled).toBe(false);
    await act(async () => confirm.click());
    expect(api.request).toHaveBeenCalledWith(`/admin/catalog/listings/${listing.id}/moderate`, {
      method: "POST",
      body: JSON.stringify({ action: "hide", reason: "Counterfeit report confirmed" }),
    });
  });

  it("shows no mutation controls on a read-only tab and a permission panel elsewhere", async () => {
    api.request.mockResolvedValue([{ ...listing, kind: "service" }]);
    await render({ permissions: ["services.read"], unrestricted: false, can_manage_roles: false });
    // Default tab (listings) needs products.manage.
    expect(container.querySelector('[data-testid="admin-permission-denied"]')).not.toBeNull();
    expect(api.request).not.toHaveBeenCalled();

    await act(async () => button("admin.catalog.tabs.services").click());
    expect(container.textContent).toContain("Phone");
    expect(container.textContent).not.toContain("admin.catalog.actions.hide");
  });

  it("explains a hold and offers restore", async () => {
    api.request.mockResolvedValue([
      {
        ...listing,
        status: "paused",
        visible: false,
        hold: {
          id: "h",
          action: "hide",
          from_status: "active",
          reason: "Review",
          actor: null,
          created_at: null,
        },
      },
    ]);
    await render({ permissions: [], unrestricted: true, can_manage_roles: false });
    expect(container.textContent).toContain("admin.catalog.notVisible");
    expect(container.textContent).toContain("admin.catalog.heldBy");
    expect(() => button("admin.catalog.actions.restore")).not.toThrow();
  });
});
