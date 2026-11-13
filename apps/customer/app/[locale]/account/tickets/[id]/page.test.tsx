import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import events from "../../../../../../../packages/i18n/messages/en/events.json";

const session = vi.hoisted(() => ({ token: vi.fn() }));
vi.mock("../../_components/account-server", () => ({ getAccountAccessToken: session.token }));
vi.mock("../../../../../lib/api-base-url", () => ({ getApiBaseUrl: () => "http://wallet.test" }));
vi.mock("next-intl/server", () => ({ getMessages: async () => ({}), setRequestLocale: vi.fn() }));
vi.mock("@vergeo/i18n", () => ({ LOCALES: ["en"], loadNamespace: async () => events }));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("not found");
  },
}));
vi.mock("./_components/ticket-actions", () => ({ TicketActions: () => null }));

import Page from "./page";

const windowNumber = 30000000;
const entry = (window = windowNumber) => ({
  window,
  code: "123456",
  qr_payload: `ticket-a:${window}:test-signature`,
});
const detail = (status = "issued") => ({
  id: "ticket-a",
  status,
  holder_name: "Test Holder",
  pin: "654321",
  pin_available: true,
  qr: { ...entry(), seconds_remaining: 30 },
  event: { id: "event-a", title: "Local test event", venue: "Test venue", slug: "test" },
  instance: { id: "instance-a", starts_at: "2027-01-01T12:00:00Z" },
  ticket_type: { id: "type-a", name: "Standard", kind: "fixed" },
});
const horizon = () => ({
  ticket_id: "ticket-a",
  from_window: windowNumber,
  last_window: windowNumber + 1,
  pin: "654321",
  entries: [entry(), entry(windowNumber + 1)],
});
const request = vi.fn();
const key = "vergeo5:ticket-horizon:ticket-a";

function responses(ticket = detail(), optional: unknown = horizon()) {
  request.mockImplementation(async (url: string) => {
    if (url.endsWith("/horizon")) {
      if (optional instanceof Error) throw optional;
      return { ok: true, json: async () => optional };
    }
    return { ok: true, json: async () => ticket };
  });
}
async function component(id = "ticket-a") {
  return Page({ params: Promise.resolve({ locale: "en", id }) });
}
async function mount() {
  const result = render(await component());
  return result;
}
function visible(container: HTMLElement) {
  return [...container.querySelectorAll<HTMLElement>("[data-ticket-qr-window]")]
    .filter((node) => !node.hidden)
    .map((node) => Number(node.dataset.ticketQrWindow));
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] });
  vi.setSystemTime((windowNumber * 60 + 30) * 1000);
  vi.stubGlobal("fetch", request);
  vi.spyOn(window, "addEventListener");
  session.token.mockResolvedValue("local-test-session");
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
  localStorage.clear();
  responses();
});
afterEach(async () => {
  cleanup();
  await Promise.resolve();
  window.dispatchEvent(new PageTransitionEvent("pagehide"));
  // Isolate listeners even when a cleanup regression makes a test fail.
  for (const [type, handler] of vi.mocked(window.addEventListener).mock.calls) {
    if (["online", "offline", "pagehide"].includes(type)) window.removeEventListener(type, handler);
  }
  vi.clearAllTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  request.mockReset();
});

describe("ticket wallet optional storage and horizon", () => {
  it.each(["SecurityError", "QuotaExceededError"])(
    "rotates the mounted wallet with %s storage writes",
    async (name) => {
      vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
        throw new DOMException("unavailable", name);
      });
      const page = await mount();
      expect(visible(page.container)).toEqual([windowNumber]);
      vi.advanceTimersByTime(30000);
      expect(visible(page.container)).toEqual([windowNumber + 1]);
      expect(vi.getTimerCount()).toBe(1);
    },
  );
  it("works when accessing storage itself is denied", async () => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    const page = await mount();
    vi.advanceTimersByTime(30000);
    expect(visible(page.container)).toEqual([windowNumber + 1]);
  });
  it.each(["{broken", JSON.stringify({ ...horizon(), ticket_id: "other" })])(
    "ignores malformed or wrong-ticket cache: %s",
    async (cache) => {
      localStorage.setItem(key, cache);
      vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {});
      const page = await mount();
      vi.advanceTimersByTime(30000);
      expect(visible(page.container)).toEqual([windowNumber + 1]);
    },
  );
  it("uses the current detail in memory when there is no horizon and expires it", async () => {
    responses(detail(), null);
    const page = await mount();
    expect(visible(page.container)).toEqual([windowNumber]);
    expect(page.container.querySelector<HTMLElement>("[data-ticket-qr-expired]")?.hidden).toBe(
      true,
    );
    vi.advanceTimersByTime(30000);
    expect(visible(page.container)).toEqual([]);
    expect(page.container.querySelector<HTMLElement>("[data-ticket-qr-expired]")?.hidden).toBe(
      false,
    );
  });
  it("does not revive expired payloads from storage", async () => {
    localStorage.setItem(
      key,
      JSON.stringify({
        ...horizon(),
        last_window: windowNumber + 100,
        entries: [entry(windowNumber + 2)],
      }),
    );
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {});
    const page = await mount();
    vi.advanceTimersByTime(90000);
    expect(visible(page.container)).toEqual([]);
    expect(page.container.querySelector<HTMLElement>("[data-ticket-qr-expired]")?.hidden).toBe(
      false,
    );
  });
  it.each(["checked_in", "transferred", "void"])(
    "does not initialize inactive %s tickets",
    async (status) => {
      responses(detail(status));
      localStorage.setItem(key, JSON.stringify(horizon()));
      const page = await mount();
      expect(page.container.querySelector("script")).toBeNull();
      expect(vi.getTimerCount()).toBe(0);
      expect(visible(page.container)).toEqual([]);
      expect(request).toHaveBeenCalledTimes(1);
    },
  );
  it("does not request a horizon when detail has no active QR", async () => {
    responses({ ...detail(), qr: null } as unknown as ReturnType<typeof detail>);
    const page = await mount();
    expect(visible(page.container)).toEqual([]);
    expect(request).toHaveBeenCalledTimes(1);
  });
  it("keeps the valid view on horizon transport failure", async () => {
    responses(detail(), new TypeError("network unavailable"));
    const page = await mount();
    expect(visible(page.container)).toEqual([windowNumber]);
  });
  it("keeps the valid view on horizon JSON failure", async () => {
    request.mockImplementation(async (url: string) => ({
      ok: true,
      json: async () => {
        if (url.endsWith("/horizon")) throw new SyntaxError("bad JSON");
        return detail();
      },
    }));
    const page = await mount();
    expect(visible(page.container)).toEqual([windowNumber]);
  });
  it.each([
    null,
    {},
    { ...horizon(), entries: [null] },
    { ...horizon(), ticket_id: "ticket-b" },
    {
      ...horizon(),
      entries: [entry(windowNumber - 10)],
      from_window: windowNumber - 10,
      last_window: windowNumber - 10,
    },
  ])("isolates malformed, wrong-ticket or stale horizon %j", async (optional) => {
    responses(detail(), optional);
    const page = await mount();
    expect(visible(page.container)).toEqual([windowNumber]);
    vi.advanceTimersByTime(30000);
    expect(visible(page.container)).toEqual([]);
  });
  it.each([401, 403, 404, 410, 500])(
    "does not replace detail denial %s with cached authorization",
    async (status) => {
      localStorage.setItem(key, JSON.stringify(horizon()));
      request.mockResolvedValue({ ok: false, status });
      await expect(component()).rejects.toThrow();
      expect(request).toHaveBeenCalledTimes(1);
    },
  );
  it("requires a session before requesting detail", async () => {
    session.token.mockRejectedValue(new Error("login required"));
    await expect(component()).rejects.toThrow("login required");
    expect(request).not.toHaveBeenCalled();
  });
  it("cleans timers and online/offline listeners on repeated navigation", async () => {
    const add = vi.spyOn(window, "addEventListener");
    const remove = vi.spyOn(window, "removeEventListener");
    for (let i = 0; i < 3; i++) {
      const page = await mount();
      expect(vi.getTimerCount()).toBe(1);
      page.unmount();
      await Promise.resolve();
      expect(vi.getTimerCount()).toBe(0);
    }
    for (const event of ["online", "offline", "pagehide"]) {
      const handlers = add.mock.calls
        .filter(([type]) => type === event)
        .map(([, handler]) => handler);
      expect(handlers).toHaveLength(3);
      for (const handler of handlers) expect(remove).toHaveBeenCalledWith(event, handler);
    }
  });
  it("keeps the timer across a persisted pagehide (back/forward cache)", async () => {
    const page = await mount();
    window.dispatchEvent(new PageTransitionEvent("pagehide", { persisted: true }));
    vi.advanceTimersByTime(30000);
    expect(visible(page.container)).toEqual([windowNumber + 1]);
    expect(vi.getTimerCount()).toBe(1);
  });
  it("updates connectivity without recreating the timer", async () => {
    const page = await mount();
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
    window.dispatchEvent(new Event("online"));
    expect(
      page.container.querySelector("[data-ticket-offline-banner]")?.classList.contains("hidden"),
    ).toBe(true);
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    window.dispatchEvent(new Event("offline"));
    expect(
      page.container.querySelector("[data-ticket-offline-banner]")?.classList.contains("hidden"),
    ).toBe(false);
    expect(vi.getTimerCount()).toBe(1);
  });
  it.each([403, 500])("keeps detail on optional horizon HTTP %s", async (status) => {
    request.mockImplementation(async (url: string) =>
      url.endsWith("/horizon") ? { ok: false, status } : { ok: true, json: async () => detail() },
    );
    expect(visible((await mount()).container)).toEqual([windowNumber]);
  });
  it("cleans on pagehide", async () => {
    await mount();
    window.dispatchEvent(new PageTransitionEvent("pagehide"));
    expect(vi.getTimerCount()).toBe(0);
  });
  it("starts replacement ticket rotation after disposing the old ticket", async () => {
    const old = await mount();
    old.unmount();
    expect(vi.getTimerCount()).toBe(0);
    responses({ ...detail(), id: "ticket-b" }, { ...horizon(), ticket_id: "ticket-b" });
    const replacement = render(await component("ticket-b"));
    expect(vi.getTimerCount()).toBe(1);
    vi.advanceTimersByTime(30000);
    expect(visible(replacement.container)).toEqual([windowNumber + 1]);
    expect(vi.getTimerCount()).toBe(1);
  });
});
