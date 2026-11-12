import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CONSENT_COOKIE } from "../consent";
import { __resetSessionMemory } from "../session";
import { __resetQueue, __queueLength, flush, MAX_QUEUE_V2, track, trackPageView } from "../track";

import { __resetIdsMemory, ANON_KEY, SESSION_IDLE_MS } from "./ids";
import { pageKeyFromPath, referrerKind } from "./page-key";

import type { WireBatchV2 } from "./envelope";

const PRODUCT = "11111111-1111-4111-8111-111111111111";
const UUID = /^[0-9a-f-]{36}$/i;

let bodies: string[] = [];

function setConsent(state: "granted" | "denied" | "unset"): void {
  document.cookie =
    state === "unset"
      ? `${CONSENT_COOKIE}=; path=/; max-age=0`
      : `${CONSENT_COOKIE}=${state}; path=/`;
}

function lastBatch(): WireBatchV2 {
  return JSON.parse(bodies[bodies.length - 1]!) as WireBatchV2;
}

beforeEach(() => {
  bodies = [];
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-13T08:00:00Z"));
  window.localStorage.clear();
  __resetIdsMemory();
  __resetSessionMemory();
  __resetQueue();
  setConsent("unset");
  Object.defineProperty(navigator, "globalPrivacyControl", {
    configurable: true,
    value: undefined,
  });
  class CapturingBlob {
    constructor(parts?: BlobPart[]) {
      if (parts && typeof parts[0] === "string") {
        bodies.push(parts[0]);
      }
    }
  }
  vi.stubGlobal("Blob", CapturingBlob);
  Object.defineProperty(navigator, "sendBeacon", {
    configurable: true,
    writable: true,
    value: vi.fn(() => true),
  });
  window.history.replaceState(null, "", "/en/p/some-product-slug?ref=x");
});

afterEach(() => {
  __resetQueue();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.useRealTimers();
});

describe("v2 tracking OFF (default)", () => {
  it("sends the exact v1 body and never touches v2 storage", () => {
    track("product_view", { product_id: PRODUCT });
    trackPageView(); // no-op when off
    expect(__queueLength()).toBe(1);
    flush();
    const body = JSON.parse(bodies[0]!) as Record<string, unknown>;
    expect(Object.keys(body).sort()).toEqual(["events", "session_id"]);
    expect(body.events).toEqual([
      { event: "product_view", props: { product_id: PRODUCT }, ts: Date.now() },
    ]);
    expect(window.localStorage.getItem(ANON_KEY)).toBeNull();
    expect(window.localStorage.getItem("vg_sess2")).toBeNull();
  });

  it("does not schedule a timed flush", () => {
    track("product_view", { product_id: PRODUCT });
    vi.advanceTimersByTime(60_000);
    expect(bodies).toHaveLength(0);
  });
});

describe("v2 tracking ON", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_ANALYTICS_V2_TRACKING", "1");
  });

  it("emits session_start first, then the event, with the v2 envelope", () => {
    window.localStorage.setItem("vg_session_id", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
    track("product_view", { product_id: PRODUCT });
    flush();
    const batch = lastBatch();
    expect(batch.v).toBe(2);
    expect(batch.app).toBe("customer");
    // legacy id kept in session_id (v1 meaning) and used to seed the visitor id
    expect(batch.session_id).toBe("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
    expect(batch.anon).toBe("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
    expect(batch.sid).toMatch(UUID);
    expect(batch.events.map((e) => e.event)).toEqual(["session_start", "product_view"]);
    const [start, view] = batch.events;
    expect(start!.props).toEqual({ entry_page_key: "pdp", referrer_kind: "direct" });
    expect(view!.page).toBe("pdp");
    expect(view!.ev).toBe(1);
    expect(view!.id).toMatch(UUID);
    expect(view!.id).not.toBe(start!.id);
    expect(view!.seq).toBeGreaterThan(start!.seq);
    // the raw URL / slug never leaves the browser
    expect(JSON.stringify(batch)).not.toContain("some-product-slug");
  });

  it("keeps the session within 30 min and rotates after inactivity", () => {
    track("product_view", { product_id: PRODUCT });
    flush();
    const first = lastBatch();
    vi.advanceTimersByTime(SESSION_IDLE_MS - 1_000);
    trackPageView();
    flush();
    const second = lastBatch();
    expect(second.sid).toBe(first.sid);
    expect(second.events.map((e) => e.event)).toEqual(["page_view"]);
    expect(second.events[0]!.seq).toBeGreaterThan(first.events[1]!.seq);

    vi.advanceTimersByTime(SESSION_IDLE_MS + 1_000);
    trackPageView();
    flush();
    const third = lastBatch();
    expect(third.sid).not.toBe(first.sid);
    expect(third.anon).toBe(first.anon); // same visitor, new journey
    expect(third.events.map((e) => e.event)).toEqual(["session_start", "page_view"]);
  });

  it("flushes pending events on a 15 s timer", () => {
    trackPageView();
    expect(bodies).toHaveLength(0);
    vi.advanceTimersByTime(15_000);
    expect(bodies).toHaveLength(1);
  });

  it("drops exact repeats within 1 s (StrictMode double effects)", () => {
    trackPageView();
    trackPageView();
    expect(__queueLength()).toBe(2); // session_start + one page_view
    vi.advanceTimersByTime(1_500);
    trackPageView();
    expect(__queueLength()).toBe(3);
  });

  it("bounds the queue", () => {
    const sendBeacon = navigator.sendBeacon as ReturnType<typeof vi.fn>;
    sendBeacon.mockReturnValue(true);
    for (let i = 0; i < 200; i += 1) {
      track("recommendation_impression", { product_id: PRODUCT, slot: "home.rail", rank: i });
    }
    expect(__queueLength()).toBeLessThanOrEqual(MAX_QUEUE_V2);
  });

  it("counts-only on opt-out: no identifiers, visitor id forgotten", () => {
    track("product_view", { product_id: PRODUCT });
    flush();
    const anon = lastBatch().anon;
    expect(window.localStorage.getItem(ANON_KEY)).toBe(anon);

    setConsent("denied");
    trackPageView();
    flush();
    const batch = lastBatch();
    expect(batch.consent).toBe("denied");
    expect(batch.anon).toBeUndefined();
    expect(batch.sid).toBeUndefined();
    expect(batch.session_id).toBeUndefined();
    expect(batch.events[0]!.id).toMatch(UUID); // still deduplicable
    expect(window.localStorage.getItem(ANON_KEY)).toBeNull();

    setConsent("granted");
    window.localStorage.removeItem("vg_session_id");
    vi.advanceTimersByTime(2_000);
    trackPageView();
    flush();
    expect(lastBatch().anon).toMatch(UUID);
    expect(lastBatch().anon).not.toBe(anon); // fresh, unlinked id
  });

  it("honours Global Privacy Control", () => {
    Object.defineProperty(navigator, "globalPrivacyControl", { configurable: true, value: true });
    trackPageView();
    flush();
    expect(lastBatch().consent).toBe("denied");
    expect(lastBatch().anon).toBeUndefined();
  });
});

describe("page keys and referrer kinds", () => {
  it.each([
    ["/", "home"],
    ["/en", "home"],
    ["/bem/p/slug", "pdp"],
    ["/en/c/electronics/phones", "plp"],
    ["/en/v/vendor-slug", "storefront"],
    ["/fr/checkout/card/123", "checkout"],
    ["/en/account/orders/abc", "account"],
    ["/en/search?q=phone", "search"],
    ["/en/unknown-thing", "other"],
    ["/enx/p/slug", "other"],
  ])("%s -> %s", (path, key) => {
    expect(pageKeyFromPath(path)).toBe(key);
  });

  it("classifies referrers without exposing them", () => {
    expect(referrerKind("", "vergeo5.com")).toBe("direct");
    expect(referrerKind("https://vergeo5.com/en", "vergeo5.com")).toBe("internal");
    expect(referrerKind("https://www.google.com/search?q=x", "vergeo5.com")).toBe("search");
    expect(referrerKind("https://l.facebook.com/x", "vergeo5.com")).toBe("social");
    expect(referrerKind("https://example.org", "vergeo5.com")).toBe("other");
    expect(referrerKind("not a url", "vergeo5.com")).toBe("other");
  });
});
