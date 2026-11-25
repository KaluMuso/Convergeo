// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { AdminPage } from "./admin-page";

import type { Root } from "react-dom/client";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

let root: Root | undefined;
let container: HTMLDivElement | undefined;

afterEach(async () => {
  await act(async () => root?.unmount());
  container?.remove();
  root = undefined;
  container = undefined;
});

describe("AdminPage", () => {
  it("renders title and child content", async () => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(
        <AdminPage title="Dashboard" subtitle="Overview">
          <p>Body</p>
        </AdminPage>,
      );
    });
    expect(container.textContent).toContain("Dashboard");
    expect(container.textContent).toContain("Overview");
    expect(container.textContent).toContain("Body");
  });
});
