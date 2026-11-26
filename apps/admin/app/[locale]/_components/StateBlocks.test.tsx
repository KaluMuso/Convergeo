// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { EmptyBlock, LoadingBlock } from "./StateBlocks";

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

describe("StateBlocks", () => {
  it("renders skeleton loading rows", async () => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(<LoadingBlock label="Loading" rows={2} />);
    });
    expect(container.querySelectorAll("[data-testid='admin-loading-row']").length).toBe(2);
  });

  it("renders empty state test id", async () => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(<EmptyBlock title="All caught up" body="Nothing pending" />);
    });
    expect(container.querySelector("[data-testid='admin-empty']")).toBeTruthy();
  });
});
