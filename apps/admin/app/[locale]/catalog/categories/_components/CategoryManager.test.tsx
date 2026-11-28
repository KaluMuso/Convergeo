// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminPermissionsContext, type AdminPermissions } from "../../../../../lib/roles-api";

const api = vi.hoisted(() => ({
  listNodes: vi.fn(),
  setStatus: vi.fn(),
  reorderNodes: vi.fn(),
  deleteNode: vi.fn(),
  createNode: vi.fn(),
  updateNode: vi.fn(),
  moveNode: vi.fn(),
  uploadNodeImage: vi.fn(),
}));
vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));
vi.mock("../../../../../lib/access-token", () => ({
  getBrowserAccessToken: () => "token",
}));
vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: async () => ({}),
}));
vi.mock("@vergeo/ui/src/toast", () => ({
  notify: { success: vi.fn(), error: vi.fn() },
}));
vi.mock("./taxonomy-api", () => api);

import { CategoryManager } from "./CategoryManager";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

const base = {
  umbrella: "product",
  sort_order: 10,
  image_public_id: null,
  image_alt: null,
  icon: null,
  show_in_customer: true,
  show_in_vendor: true,
  path: null,
  commission_key: null,
  child_count: 0,
  parent_id: null,
};
const fashion = {
  ...base,
  id: "c1",
  slug: "fashion",
  name: "Fashion",
  status: "published",
  image_url: "https://res.cloudinary.com/demo/image/upload/fashion.jpg",
  image_alt: "Fashion",
};
const toys = {
  ...base,
  id: "c2",
  slug: "toys",
  name: "Toys",
  status: "blocked",
  sort_order: 20,
  image_url: null,
};

const writer: AdminPermissions = {
  permissions: ["products.manage"],
  unrestricted: false,
  can_manage_roles: false,
};

let container: HTMLDivElement;
let root: Root;

async function render(grants: AdminPermissions = writer) {
  await act(async () => {
    root.render(
      <AdminPermissionsContext.Provider value={grants}>
        <CategoryManager />
      </AdminPermissionsContext.Provider>,
    );
  });
}

function button(label: string): HTMLButtonElement {
  const found = Array.from(document.querySelectorAll("button")).find(
    (node) => node.textContent === label || node.getAttribute("aria-label") === label,
  );
  if (!found) throw new Error(`button ${label} not found`);
  return found as HTMLButtonElement;
}

beforeEach(() => {
  Object.values(api).forEach((mock) => mock.mockReset());
  api.listNodes.mockResolvedValue([fashion, toys]);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  document.body.innerHTML = "";
});

describe("CategoryManager", () => {
  it("lists the tree with image, status chips and umbrella tabs", async () => {
    await render();
    expect(api.listNodes).toHaveBeenCalledWith("product", "");
    expect(container.textContent).toContain("Fashion");
    expect(container.textContent).toContain("admin.catalog.categories.status.published");
    expect(container.textContent).toContain("admin.catalog.categories.status.blocked");
    expect(container.querySelector("img")?.getAttribute("src")).toContain("fashion.jpg");
    for (const tab of ["product", "service", "event", "wholesale"]) {
      expect(container.textContent).toContain(`admin.catalog.categories.tabs.${tab}`);
    }
  });

  it("switching tab reloads that umbrella", async () => {
    await render({
      permissions: [],
      unrestricted: true,
      can_manage_roles: true,
    });
    await act(async () => button("admin.catalog.categories.tabs.event").click());
    expect(api.listNodes).toHaveBeenLastCalledWith("event", "");
  });

  it("shows a permission failure for umbrellas the operator cannot manage", async () => {
    await render();
    await act(async () => button("admin.catalog.categories.tabs.event").click());
    expect(container.textContent).toContain("admin.catalog.categories.permissionDenied");
    expect(api.listNodes).toHaveBeenCalledTimes(1);
  });

  it("publishes a blocked category through the status endpoint (unblock)", async () => {
    api.setStatus.mockResolvedValue({ ...toys, status: "published" });
    await render();
    await act(async () => button("admin.catalog.categories.actions.unblock").click());
    expect(api.setStatus).toHaveBeenCalledWith("product", "c2", "published");
  });

  it("moves a row with the arrows via one reorder call", async () => {
    api.reorderNodes.mockResolvedValue([]);
    await render();
    await act(async () => button("admin.catalog.categories.moveDown").click());
    expect(api.reorderNodes).toHaveBeenCalledWith("product", null, ["c2", "c1"]);
  });

  it("blocking needs a reason", async () => {
    api.setStatus.mockResolvedValue({ ...fashion, status: "blocked" });
    await render();
    await act(async () => button("admin.catalog.categories.actions.block").click());
    const confirm = document.querySelector(
      '[data-testid="taxonomy-block-confirm"]',
    ) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    const input = document.querySelector(
      '[data-testid="taxonomy-block"] input',
    ) as HTMLInputElement;
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      setter?.call(input, "Policy review");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(confirm.disabled).toBe(false);
    await act(async () => confirm.click());
    expect(api.setStatus).toHaveBeenCalledWith("product", "c1", "blocked", "Policy review");
  });

  it("hides write controls without permission", async () => {
    await render({
      permissions: ["vendors.manage"],
      unrestricted: false,
      can_manage_roles: false,
    });
    expect(container.textContent).toContain("admin.catalog.categories.permissionDenied");
    expect(container.textContent).not.toContain("admin.catalog.categories.add");
  });
});
