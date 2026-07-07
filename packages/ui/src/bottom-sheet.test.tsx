// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BottomSheet } from "./bottom-sheet";

afterEach(() => {
  cleanup();
  document.body.style.overflow = "";
});

describe("BottomSheet", () => {
  it("opens and closes", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    const { rerender } = render(
      <BottomSheet open title="Sheet" onClose={onClose}>
        <p>Sheet body</p>
      </BottomSheet>,
    );

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Sheet body")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();

    onClose.mockClear();
    rerender(
      <BottomSheet open={false} title="Sheet" onClose={onClose}>
        <p>Sheet body</p>
      </BottomSheet>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("dismisses when dragged past threshold", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    render(
      <BottomSheet open title="Drag sheet" onClose={onClose} data-testid="sheet">
        <p>Drag me</p>
      </BottomSheet>,
      { container: document.body },
    );

    const sheet = screen.getByTestId("sheet-sheet");

    await user.pointer([
      { keys: "[MouseLeft>]", target: sheet, coords: { clientY: 100 } },
      { coords: { clientY: 220 } },
      { keys: "[/MouseLeft]", coords: { clientY: 220 } },
    ]);

    expect(onClose).toHaveBeenCalled();
  });

  it("snaps back when drag is below threshold", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    render(
      <BottomSheet open title="Snap sheet" onClose={onClose} data-testid="sheet">
        <p>Content</p>
      </BottomSheet>,
      { container: document.body },
    );

    const sheet = screen.getByTestId("sheet-sheet");

    await user.pointer([
      { keys: "[MouseLeft>]", target: sheet, coords: { clientY: 100 } },
      { coords: { clientY: 130 } },
      { keys: "[/MouseLeft]", coords: { clientY: 130 } },
    ]);

    expect(onClose).not.toHaveBeenCalled();
    expect(sheet.style.transform).toBe("");
  });

  it("applies snapHeight when provided", () => {
    render(
      <BottomSheet open title="Tall" onClose={vi.fn()} snapHeight="50vh" data-testid="sheet">
        <p>Tall content</p>
      </BottomSheet>,
    );

    const sheet = screen.getByTestId("sheet-sheet");
    expect(sheet).toHaveStyle({ height: "50vh", maxHeight: "50vh" });
  });

  it("dismisses on scrim click", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    render(
      <BottomSheet open title="Scrim" onClose={onClose}>
        <p>Body</p>
      </BottomSheet>,
    );

    const dialog = screen.getByRole("dialog");
    await user.click(dialog);
    expect(onClose).toHaveBeenCalled();
  });

  it("uses fadeSlideUp animation token", async () => {
    render(
      <BottomSheet open title="Animate" onClose={vi.fn()} data-testid="sheet">
        <p>Animated</p>
      </BottomSheet>,
    );

    await waitFor(() => {
      const sheet = screen.getByTestId("sheet-sheet");
      expect(sheet).toHaveStyle({ animation: "fadeSlideUp var(--dur) var(--ease-out)" });
    });
  });
});
