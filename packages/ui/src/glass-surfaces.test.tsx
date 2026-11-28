// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { BottomNav } from "./bottom-nav";
import { BottomSheet } from "./bottom-sheet";
import { Modal } from "./modal";

afterEach(() => {
  cleanup();
  document.body.style.overflow = "";
});

describe("glass surfaces applied to shared chrome", () => {
  it("bottom nav uses the bottom glass bar", () => {
    render(<BottomNav items={[]} ariaLabel="Main" />);
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(nav).toHaveClass("v-glass", "v-glass--bar", "v-glass--bar-bottom");
  });

  it("modal panel is glass and the scrim is frosted", () => {
    render(
      <Modal open title="Title" onClose={() => undefined} data-testid="m">
        <p>Body</p>
      </Modal>,
    );
    expect(screen.getByTestId("m")).toHaveClass("v-glass-scrim");
    expect(screen.getByText("Body").closest(".v-glass")).toHaveClass("v-glass--overlay");
  });

  it("bottom sheet is glass and the scrim is frosted", () => {
    render(
      <BottomSheet open title="Sheet" onClose={() => undefined} data-testid="s">
        <p>Body</p>
      </BottomSheet>,
    );
    expect(screen.getByTestId("s")).toHaveClass("v-glass-scrim");
    expect(screen.getByTestId("s-sheet")).toHaveClass("v-glass", "v-glass--overlay");
  });
});
