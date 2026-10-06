import { act, cleanup, render } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TicketWalletRuntime } from "./ticket-wallet-runtime";

const current = 30000000;
const labels = {
  refreshInTemplate: "Refresh __SEC__",
  offlineBody: "Offline",
  offlineExpired: "Expired",
};
function wallet(ticketId = "a", active = true, offset = 0) {
  return (
    <TicketWalletRuntime ticketId={ticketId} active={active} horizon={null} labels={labels}>
      <p data-ticket-countdown />
      <div data-ticket-offline-banner>
        <p data-ticket-offline-body />
      </div>
      <div data-ticket-qr-window={current + offset} hidden>
        current {ticketId}
      </div>
      <div data-ticket-qr-window={current + offset + 1} hidden>
        next {ticketId}
      </div>
      <div data-ticket-qr-expired hidden>
        Expired
      </div>
    </TicketWalletRuntime>
  );
}
function visible(container: HTMLElement) {
  return container.querySelector<HTMLElement>("[data-ticket-qr-window]:not([hidden])")?.textContent;
}
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] });
  vi.setSystemTime((current * 60 + 30) * 1000);
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("React-managed ticket wallet lifecycle", () => {
  it("initializes on client insertion, leaves and re-enters without script evaluation", () => {
    const view = render(<div>Ticket index</div>);
    for (let i = 0; i < 3; i++) {
      view.rerender(wallet());
      expect(visible(view.container)).toBe("current a");
      expect(vi.getTimerCount()).toBe(1);
      view.rerender(<div>Ticket index</div>);
      expect(vi.getTimerCount()).toBe(0);
    }
  });
  it("rotates and expires through its interval", () => {
    const view = render(wallet());
    act(() => vi.advanceTimersByTime(30000));
    expect(visible(view.container)).toBe("next a");
    act(() => vi.advanceTimersByTime(60000));
    expect(visible(view.container)).toBeUndefined();
    expect(view.container.querySelector<HTMLElement>("[data-ticket-qr-expired]")?.hidden).toBe(
      false,
    );
  });
  it("replaces the effect on ticket ID changes and isolates old nodes", () => {
    const view = render(wallet());
    view.rerender(wallet("b", true, 1));
    expect(vi.getTimerCount()).toBe(1);
    expect(visible(view.container)).toBeUndefined();
    act(() => vi.advanceTimersByTime(30000));
    expect(visible(view.container)).toBe("current b");
    expect(view.container.textContent).not.toContain("current a");
  });
  it("cleans all listeners and timers, including Strict Mode's setup-cleanup-setup", () => {
    const add = vi.spyOn(window, "addEventListener");
    const remove = vi.spyOn(window, "removeEventListener");
    const docAdd = vi.spyOn(document, "addEventListener");
    const docRemove = vi.spyOn(document, "removeEventListener");
    const view = render(<StrictMode>{wallet()}</StrictMode>);
    expect(vi.getTimerCount()).toBe(1);
    act(() => vi.advanceTimersByTime(30000));
    expect(visible(view.container)).toBe("next a");
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
    for (const type of ["online", "offline", "focus", "pageshow", "pagehide"]) {
      const calls = add.mock.calls.filter(([event]) => event === type);
      expect(calls).toHaveLength(2);
      for (const [, handler] of calls) expect(remove).toHaveBeenCalledWith(type, handler);
    }
    for (const [type, handler] of docAdd.mock.calls.filter(
      ([type]) => type === "visibilitychange",
    )) {
      expect(docRemove).toHaveBeenCalledWith(type, handler);
    }
  });
  it("handles repeated focus, pageshow and visibility without duplicating timers", () => {
    const view = render(wallet());
    vi.setSystemTime((current + 1) * 60000);
    for (let i = 0; i < 5; i++) {
      window.dispatchEvent(new Event("focus"));
      window.dispatchEvent(new PageTransitionEvent("pageshow"));
      document.dispatchEvent(new Event("visibilitychange"));
    }
    expect(visible(view.container)).toBe("next a");
    expect(vi.getTimerCount()).toBe(1);
  });
  it("catches up on bfcache restoration and disposes on ordinary pagehide", () => {
    const view = render(wallet());
    window.dispatchEvent(new PageTransitionEvent("pagehide", { persisted: true }));
    vi.setSystemTime((current + 1) * 60000);
    window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
    expect(visible(view.container)).toBe("next a");
    expect(vi.getTimerCount()).toBe(1);
    window.dispatchEvent(new PageTransitionEvent("pagehide"));
    expect(vi.getTimerCount()).toBe(0);
  });
  it("disposes when a server render makes the ticket inactive", () => {
    const view = render(wallet());
    view.rerender(wallet("a", false));
    expect(vi.getTimerCount()).toBe(0);
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
