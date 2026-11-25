// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DocViewer } from "./DocViewer";

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));

let container: HTMLDivElement;
let root: ReturnType<typeof createRoot>;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

describe("DocViewer", () => {
  it("shows skeleton placeholders while loading", () => {
    act(() => {
      root.render(<DocViewer documents={[]} docsAvailable loading />);
    });
    expect(container.querySelectorAll("[data-testid='kyc-doc-skeleton']").length).toBe(2);
  });
});
