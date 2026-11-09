// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  emitToastKey,
  TOAST_DEFAULT_DURATION_MS,
  TOAST_MAX_QUEUE,
  ToastProvider,
  notify,
  useOptionalToast,
  useToast,
} from "./toast";

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

  it("caps queue at 3 with FIFO eviction", () => {
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
    expect(screen.queryByText("Message 3")).not.toBeInTheDocument();
    expect(screen.getByText("Message 4")).toBeInTheDocument();
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

  it("announces errors assertively with role=alert", () => {
    function ErrorHarness() {
      const { error } = useToast();
      return (
        <button type="button" onClick={() => error("Payment failed")}>
          Fail
        </button>
      );
    }
    render(
      <ToastProvider>
        <ErrorHarness />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Fail" }));
    expect(screen.getByTestId("toast-alert-region")).toHaveAttribute("aria-live", "assertive");
    expect(screen.getByRole("alert")).toHaveTextContent("Payment failed");
  });

  it("uses the default ~4s duration", () => {
    expect(TOAST_DEFAULT_DURATION_MS).toBe(4000);
  });

  it("pauses while focused and resumes on blur", async () => {
    render(
      <ToastProvider dismissLabel="Close">
        <ToastHarness />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Show toast" }));
    const close = screen.getByRole("button", { name: "Close" });
    fireEvent.focus(close);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(TOAST_DEFAULT_DURATION_MS + 500);
    });
    expect(screen.getByText("Hello")).toBeInTheDocument();
    fireEvent.blur(close);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(TOAST_DEFAULT_DURATION_MS + 250);
    });
    expect(screen.queryByText("Hello")).not.toBeInTheDocument();
  });

  it("dismisses via the close button and Escape", async () => {
    render(
      <ToastProvider dismissLabel="Close">
        <MultiToastHarness count={2} />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Burst" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Close" })[0]!);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250);
    });
    expect(screen.queryByText("Message 1")).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByText("Message 2"), { key: "Escape" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250);
    });
    expect(screen.queryByText("Message 2")).not.toBeInTheDocument();
  });

  it("dismisses on a horizontal touch swipe", async () => {
    if (typeof window.PointerEvent === "undefined") {
      class PointerEventPolyfill extends MouseEvent {
        pointerType: string;
        constructor(type: string, init: PointerEventInit = {}) {
          super(type, init);
          this.pointerType = init.pointerType ?? "mouse";
        }
      }
      (window as unknown as { PointerEvent: unknown }).PointerEvent = PointerEventPolyfill;
    }
    render(
      <ToastProvider>
        <ToastHarness />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Show toast" }));
    const el = screen.getByRole("status");
    fireEvent.pointerDown(el, { pointerType: "touch", clientX: 10 });
    fireEvent.pointerMove(el, { pointerType: "touch", clientX: 120 });
    fireEvent.pointerUp(el, { pointerType: "touch", clientX: 120 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250);
    });
    expect(screen.queryByText("Hello")).not.toBeInTheDocument();
  });

  it("useOptionalToast is a no-op outside a provider", () => {
    function Loose() {
      const { success } = useOptionalToast();
      return (
        <button type="button" onClick={() => success("x")}>
          Loose
        </button>
      );
    }
    render(<Loose />);
    expect(() => fireEvent.click(screen.getByRole("button", { name: "Loose" }))).not.toThrow();
  });

  it("notify bridge raises toasts through the mounted provider", () => {
    render(
      <ToastProvider>
        <span />
      </ToastProvider>,
    );
    act(() => {
      notify.success("Saved");
    });
    expect(screen.getByRole("status")).toHaveTextContent("Saved");
    expect(screen.getByRole("status")).toHaveAttribute("data-toast-type", "success");
  });

  it("emitToastKey resolves provider copy and fills placeholders", () => {
    render(
      <ToastProvider copy={{ following: "Following {name}", nested: { x: 1 } }}>
        <span />
      </ToastProvider>,
    );
    act(() => {
      emitToastKey("following", { type: "success", values: { name: "Mwila Crafts" } });
      emitToastKey("missingKey");
      emitToastKey("nested");
    });
    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(screen.getByRole("status")).toHaveTextContent("Following Mwila Crafts");
  });

  it("renders an optional action link", () => {
    render(
      <ToastProvider>
        <span />
      </ToastProvider>,
    );
    act(() => {
      notify.success("Following Shop", { action: { label: "See feed", href: "/en/account/following" } });
    });
    expect(screen.getByTestId("toast-action")).toHaveAttribute("href", "/en/account/following");
  });

  it("throws when useToast is outside provider", () => {
    const Bad = () => {
      useToast();
      return null;
    };
    expect(() => render(<Bad />)).toThrow("useToast must be used within ToastProvider");
  });
});
