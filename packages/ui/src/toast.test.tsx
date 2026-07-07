// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TOAST_DEFAULT_DURATION_MS, TOAST_MAX_QUEUE, ToastProvider, useToast } from "./toast";

function ToastHarness() {
  const { toast } = useToast();
  return (
    <button type="button" onClick={() => toast("Hello")}>
      Show toast
    </button>
  );
}

function MultiToastHarness({ count }: { count: number }) {
  const { toast } = useToast();
  return (
    <button
      type="button"
      onClick={() => {
        for (let i = 0; i < count; i += 1) {
          toast(`Message ${i + 1}`);
        }
      }}
    >
      Burst
    </button>
  );
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("Toast", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("renders live region and shows toast", () => {
    render(
      <ToastProvider>
        <ToastHarness />
      </ToastProvider>,
    );

    expect(screen.getByTestId("toast-live-region")).toHaveAttribute("aria-live", "polite");

    fireEvent.click(screen.getByRole("button", { name: "Show toast" }));
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("caps queue at 4 with FIFO eviction", () => {
    render(
      <ToastProvider>
        <MultiToastHarness count={6} />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Burst" }));

    const toasts = screen.getAllByRole("status");
    expect(toasts).toHaveLength(TOAST_MAX_QUEUE);
    expect(screen.queryByText("Message 1")).not.toBeInTheDocument();
    expect(screen.queryByText("Message 2")).not.toBeInTheDocument();
    expect(screen.getByText("Message 3")).toBeInTheDocument();
    expect(screen.getByText("Message 6")).toBeInTheDocument();
  });

  it("auto-dismisses after default duration", async () => {
    render(
      <ToastProvider>
        <ToastHarness />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Show toast" }));
    expect(screen.getByText("Hello")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(TOAST_DEFAULT_DURATION_MS + 250);
    });
    expect(screen.queryByText("Hello")).not.toBeInTheDocument();
  });

  it("pauses auto-dismiss on hover", async () => {
    render(
      <ToastProvider>
        <ToastHarness />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Show toast" }));
    const toast = screen.getByText("Hello");
    fireEvent.mouseEnter(toast);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(TOAST_DEFAULT_DURATION_MS + 500);
    });
    expect(screen.getByText("Hello")).toBeInTheDocument();

    fireEvent.mouseLeave(toast);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(TOAST_DEFAULT_DURATION_MS + 250);
    });
    expect(screen.queryByText("Hello")).not.toBeInTheDocument();
  });

  it("throws when useToast is outside provider", () => {
    const Bad = () => {
      useToast();
      return null;
    };
    expect(() => render(<Bad />)).toThrow("useToast must be used within ToastProvider");
  });
});
