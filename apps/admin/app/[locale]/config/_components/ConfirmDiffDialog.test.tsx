// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmDiffDialog } from "./ConfirmDiffDialog";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));

let root: Root | undefined;
let container: HTMLDivElement | undefined;

afterEach(async () => {
  await act(async () => root?.unmount());
  container?.remove();
});

describe("ConfirmDiffDialog", () => {
  it("paints the dialog as a frosted overlay surface and keeps its dialog semantics", async () => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    await act(async () =>
      root?.render(
        <ConfirmDiffDialog
          open
          fromLabel="From"
          toLabel="To"
          fromValue="1"
          toValue="2"
          onCancel={() => undefined}
          onConfirm={async () => undefined}
        />,
      ),
    );
    const dialog = container.querySelector('[role="dialog"]')!;
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.className).toContain("v-glass");
    expect(dialog.className).toContain("v-glass--overlay");
    // The opaque surface utilities are gone: they would fight the translucent glass tint.
    expect(dialog.className).not.toContain("bg-surface");
  });
});
