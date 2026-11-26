// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminDensityProvider, useAdminDensity } from "./admin-density";
import { AdminDensityToggle } from "./admin-density-toggle";

import type { Root } from "react-dom/client";

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string>) =>
    values?.mode ? `${key}:${values.mode}` : key,
}));

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

let root: Root | undefined;
let container: HTMLDivElement | undefined;

afterEach(async () => {
  await act(async () => root?.unmount());
  container?.remove();
  root = undefined;
  container = undefined;
});

function Probe() {
  const { density } = useAdminDensity();
  return <span data-testid="density">{density}</span>;
}

describe("AdminDensityProvider", () => {
  it("toggles compact density", async () => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(
        <AdminDensityProvider>
          <AdminDensityToggle />
          <Probe />
        </AdminDensityProvider>,
      );
    });
    const toggle = container.querySelector(
      "[data-testid='admin-density-toggle']",
    ) as HTMLButtonElement;
    expect(container.querySelector("[data-testid='density']")?.textContent).toBe("comfortable");
    await act(async () => {
      toggle.click();
    });
    expect(container.querySelector("[data-testid='density']")?.textContent).toBe("compact");
    expect(document.documentElement.dataset.adminDensity).toBe("compact");
  });
});
