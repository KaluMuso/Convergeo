// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getFocusableElements, lockBodyScroll, Modal, unlockBodyScroll } from "./modal";

afterEach(() => {
  cleanup();
  document.body.style.overflow = "";
});

describe("Modal", () => {
  it("traps focus and restores on close", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    const { rerender } = render(
      <div>
        <button type="button" data-testid="outside">
          Outside
        </button>
        <Modal open={false} title="Test modal" onClose={onClose}>
          <button type="button" data-testid="inside-a">
            A
          </button>
          <button type="button" data-testid="inside-b">
            B
          </button>
        </Modal>
      </div>,
    );

    const outside = screen.getByTestId("outside");
    outside.focus();

    rerender(
      <div>
        <button type="button" data-testid="outside">
          Outside
        </button>
        <Modal open title="Test modal" onClose={onClose}>
          <button type="button" data-testid="inside-a">
            A
          </button>
          <button type="button" data-testid="inside-b">
            B
          </button>
        </Modal>
      </div>,
    );

    const insideA = screen.getByTestId("inside-a");
    const insideB = screen.getByTestId("inside-b");

    await waitFor(() => {
      expect(document.activeElement).toBe(insideA);
    });

    insideB.focus();
    expect(document.activeElement).toBe(insideB);

    fireEvent.keyDown(document, { key: "Tab", code: "Tab", bubbles: true });
    expect(document.activeElement).toBe(insideA);

    insideA.focus();
    fireEvent.keyDown(document, { key: "Tab", code: "Tab", shiftKey: true, bubbles: true });
    expect(document.activeElement).toBe(insideB);

    rerender(
      <div>
        <button type="button" data-testid="outside">
          Outside
        </button>
        <Modal open={false} title="Test modal" onClose={onClose}>
          <button type="button" data-testid="inside-a">
            A
          </button>
        </Modal>
      </div>,
    );

    await waitFor(() => {
      expect(document.activeElement).toBe(outside);
    });
  });

  it("dismisses on ESC and scrim click", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    const { unmount } = render(
      <Modal open title="Dismiss test" onClose={onClose}>
        <p>Content</p>
      </Modal>,
    );

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);

    unmount();
    onClose.mockClear();

    render(
      <Modal open title="Dismiss test" onClose={onClose}>
        <p>Content</p>
      </Modal>,
    );

    const dialog = screen.getByRole("dialog");
    fireEvent.click(dialog);
    expect(onClose).toHaveBeenCalled();
  });

  it("respects closeOnEscape and closeOnScrimClick suppress flags", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    render(
      <Modal open title="Locked" onClose={onClose} closeOnEscape={false} closeOnScrimClick={false}>
        <p>Content</p>
      </Modal>,
    );

    await user.keyboard("{Escape}");
    const dialog = screen.getByRole("dialog");
    await user.click(dialog);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("locks and unlocks body scroll", () => {
    lockBodyScroll();
    expect(document.body.style.overflow).toBe("hidden");
    unlockBodyScroll();
    expect(document.body.style.overflow).toBe("");
  });

  it("exposes focusable query helper", () => {
    const container = document.createElement("div");
    container.innerHTML = '<button>A</button><button disabled>B</button><a href="/">C</a>';
    const focusables = getFocusableElements(container);
    expect(focusables).toHaveLength(2);
  });
});

describe("Modal reduced motion", () => {
  it("uses token durations in panel animation", () => {
    const matchMediaMock = vi.fn().mockImplementation((query: string) => ({
      matches: query === "(prefers-reduced-motion: reduce)",
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    vi.stubGlobal("matchMedia", matchMediaMock);

    render(
      <Modal open title="Motion" onClose={vi.fn()}>
        <p>Body</p>
      </Modal>,
    );

    const panel = screen.getByRole("dialog").querySelector("div");
    expect(panel).toHaveStyle({ animation: "fadeSlideUp var(--dur) var(--ease-out)" });

    vi.unstubAllGlobals();
  });
});
