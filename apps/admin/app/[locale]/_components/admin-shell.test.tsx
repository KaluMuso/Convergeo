// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resolveAdminNavCapabilities } from "../../../lib/admin-nav-capabilities";

import { AdminShell } from "./admin-shell";

import type { Root } from "react-dom/client";

let pathname = "/en";

vi.mock("next/navigation", () => ({ usePathname: () => pathname }));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
vi.mock("next/link", () => ({ default: "a" }));
vi.mock("@vergeo/ui/src/theme-toggle", () => ({ ThemeToggle: () => null }));
vi.mock("./sign-out-button", () => ({ SignOutButton: () => null }));

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

let root: Root | undefined;
let container: HTMLDivElement | undefined;

async function renderRoute(path: string) {
  pathname = path;
  await act(async () => {
    root?.render(
      <AdminShell locale="en" capabilities={resolveAdminNavCapabilities()}>
        <p data-route={path}>Route content</p>
      </AdminShell>,
    );
  });
}

afterEach(async () => {
  await act(async () => root?.unmount());
  container?.remove();
  root = undefined;
  container = undefined;
  vi.restoreAllMocks();
});

describe("AdminShell auth route transitions", () => {
  it("keeps hook order stable and renders chrome only on normal routes in both directions", async () => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});

    for (const path of [
      "/en",
      "/en/reset-password",
      "/en/reset-password/confirm",
      "/en/login",
      "/en",
      "/en/login",
      "/en/reset-password/confirm",
      "/en/reset-password",
      "/en",
    ]) {
      await renderRoute(path);
      expect(container.querySelector(`[data-route="${path}"]`)).not.toBeNull();
      const isAuth = path !== "/en";
      expect(container.querySelector("nav") === null).toBe(isAuth);
      expect(container.querySelector("[aria-controls]") === null).toBe(isAuth);
    }

    expect(errors).not.toHaveBeenCalled();
  });

  it("closes the menu and removes its key listener when entering recovery, then reopens cleanly", async () => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    const addListener = vi.spyOn(window, "addEventListener");
    const removeListener = vi.spyOn(window, "removeEventListener");

    await renderRoute("/en");
    const menuButton = container.querySelector<HTMLButtonElement>("button[aria-controls]");
    expect(menuButton).not.toBeNull();
    await act(async () => menuButton?.click());
    expect(container.querySelector('[role="dialog"]')).not.toBeNull();
    const keyListener = addListener.mock.calls.find(([type]) => type === "keydown")?.[1];
    expect(keyListener).toBeDefined();

    await renderRoute("/en/reset-password");
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(removeListener).toHaveBeenCalledWith("keydown", keyListener);

    await renderRoute("/en/reset-password/confirm");
    await renderRoute("/en/login");
    await renderRoute("/en");
    const returnedButton = container.querySelector<HTMLButtonElement>("button[aria-controls]");
    expect(returnedButton?.getAttribute("aria-expanded")).toBe("false");
    await act(async () => returnedButton?.click());
    expect(container.querySelector('[role="dialog"]')).not.toBeNull();
    await act(async () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(document.activeElement).toBe(returnedButton);
  });
});
