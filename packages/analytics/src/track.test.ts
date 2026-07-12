import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CONSENT_COOKIE } from "./consent";
import type { GtagWindow } from "./gtag";
import { __queueLength, __resetQueue, flush, MAX_BATCH, track } from "./track";

function setConsent(state: "granted" | "denied" | "unset"): void {
  if (state === "unset") {
    document.cookie = `${CONSENT_COOKIE}=; path=/; max-age=0`;
    return;
  }
  document.cookie = `${CONSENT_COOKIE}=${state}; path=/`;
}

describe("track", () => {
  beforeEach(() => {
    __resetQueue();
    setConsent("unset");
    process.env.NEXT_PUBLIC_GA4_MEASUREMENT_ID = "G-TESTID";
    (window as GtagWindow).gtag = vi.fn();
    // jsdom has no sendBeacon — provide a spy that reports success.
    Object.defineProperty(navigator, "sendBeacon", {
      configurable: true,
      writable: true,
      value: vi.fn(() => true),
    });
  });

  afterEach(() => {
    __resetQueue();
    vi.restoreAllMocks();
  });

  it("enqueues a server beacon for every event regardless of consent", () => {
    setConsent("denied");
    track("product_view", { product_id: "11111111-1111-1111-1111-111111111111" });
    track("cart_add", {
      listing_id: "22222222-2222-2222-2222-222222222222",
      qty: 1,
      unit_price_ngwee: 10_000,
    });
    expect(__queueLength()).toBe(2);
  });

  it("does NOT mirror to GA4 when consent is not granted", () => {
    const gtag = (window as GtagWindow).gtag as ReturnType<typeof vi.fn>;

    setConsent("denied");
    track("search", { normalized_term: "phones", zero_result: false });
    expect(gtag).not.toHaveBeenCalled();

    setConsent("unset");
    track("search", { normalized_term: "phones", zero_result: false });
    expect(gtag).not.toHaveBeenCalled();
  });

  it("mirrors to GA4 only after consent is granted", () => {
    const gtag = (window as GtagWindow).gtag as ReturnType<typeof vi.fn>;
    setConsent("granted");
    track("payment_start", {
      checkout_group_id: "33333333-3333-3333-3333-333333333333",
      method: "momo",
      total_ngwee: 55_000,
    });
    expect(gtag).toHaveBeenCalledWith(
      "event",
      "payment_start",
      expect.objectContaining({ total_ngwee: 55_000 }),
    );
  });

  it("batches beacons and sends them in one sendBeacon call on flush", () => {
    const sendBeacon = navigator.sendBeacon as ReturnType<typeof vi.fn>;
    setConsent("denied");
    track("search", { normalized_term: "a", zero_result: true });
    track("search", { normalized_term: "b", zero_result: true });
    expect(sendBeacon).not.toHaveBeenCalled(); // no per-event XHR/beacon

    const ok = flush();
    expect(ok).toBe(true);
    expect(sendBeacon).toHaveBeenCalledTimes(1);
    expect(__queueLength()).toBe(0);
  });

  it("auto-flushes once the batch hits MAX_BATCH", () => {
    const sendBeacon = navigator.sendBeacon as ReturnType<typeof vi.fn>;
    setConsent("denied");
    for (let i = 0; i < MAX_BATCH; i += 1) {
      track("search", { normalized_term: `q${i}`, zero_result: false });
    }
    expect(sendBeacon).toHaveBeenCalledTimes(1);
    expect(__queueLength()).toBe(0);
  });

  it("flush is a no-op with an empty queue", () => {
    const sendBeacon = navigator.sendBeacon as ReturnType<typeof vi.fn>;
    expect(flush()).toBe(false);
    expect(sendBeacon).not.toHaveBeenCalled();
  });
});
