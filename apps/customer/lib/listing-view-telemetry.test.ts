// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  __resetListingViewTelemetry,
  MAX_LISTING_IMPRESSION_BATCH,
  queueListingImpression,
  recordListingPdpView,
} from "./listing-view-telemetry";

const API_ORIGIN = "https://api.example.test";
const SESSION_ID = "10000000-0000-4000-8000-000000000001";
const LISTING_ONE = "20000000-0000-4000-8000-000000000001";
const LISTING_TWO = "20000000-0000-4000-8000-000000000002";

let capturedBodies: string[] = [];

class CapturingBlob {
  constructor(parts?: BlobPart[]) {
    const body = parts?.[0];
    if (typeof body === "string") {
      capturedBodies.push(body);
    }
  }
}

function parsedBodies(): Array<Record<string, unknown>> {
  return capturedBodies.map((body) => JSON.parse(body) as Record<string, unknown>);
}

function setOnline(value: boolean): void {
  Object.defineProperty(navigator, "onLine", {
    configurable: true,
    value,
  });
}

describe("listing view telemetry", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-10T10:00:00Z"));
    capturedBodies = [];
    process.env.NEXT_PUBLIC_API_BASE_URL = API_ORIGIN;
    process.env.NEXT_PUBLIC_DEPLOYMENT_PLANE = "production";
    localStorage.setItem("vg_session_id", SESSION_ID);
    setOnline(true);
    Object.defineProperty(navigator, "sendBeacon", {
      configurable: true,
      writable: true,
      value: vi.fn(() => true),
    });
    vi.stubGlobal("Blob", CapturingBlob);
    __resetListingViewTelemetry();
  });

  afterEach(() => {
    __resetListingViewTelemetry();
    localStorage.clear();
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    delete process.env.NEXT_PUBLIC_DEPLOYMENT_PLANE;
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("sends the exact PDP payload once per listing/session/day", () => {
    expect(recordListingPdpView(LISTING_ONE)).toBe(true);
    expect(recordListingPdpView(LISTING_ONE)).toBe(false);

    expect(navigator.sendBeacon).toHaveBeenCalledTimes(1);
    expect(navigator.sendBeacon).toHaveBeenCalledWith(
      `${API_ORIGIN}/telemetry/views`,
      expect.any(CapturingBlob),
    );
    expect(parsedBodies()).toEqual([
      { session_id: SESSION_ID, listing_id: LISTING_ONE, surface: "pdp" },
    ]);
  });

  it("deduplicates and batches impressions instead of sending per card", () => {
    expect(queueListingImpression(LISTING_ONE)).toBe(true);
    expect(queueListingImpression(LISTING_ONE)).toBe(false);
    expect(queueListingImpression(LISTING_TWO)).toBe(true);
    expect(navigator.sendBeacon).not.toHaveBeenCalled();

    vi.runAllTimers();

    expect(navigator.sendBeacon).toHaveBeenCalledTimes(1);
    expect(parsedBodies()).toEqual([
      { session_id: SESSION_ID, listing_ids: [LISTING_ONE, LISTING_TWO], surface: "unknown" },
    ]);
  });

  it("caps every impression request at the API maximum of 50", () => {
    for (let index = 1; index <= MAX_LISTING_IMPRESSION_BATCH + 1; index += 1) {
      const listingId = `30000000-0000-4000-8000-${String(index).padStart(12, "0")}`;
      expect(queueListingImpression(listingId)).toBe(true);
    }
    vi.runAllTimers();

    expect(navigator.sendBeacon).toHaveBeenCalledTimes(2);
    expect(parsedBodies().map((payload) => (payload.listing_ids as string[]).length)).toEqual([
      MAX_LISTING_IMPRESSION_BATCH,
      1,
    ]);
  });

  it("includes an explicit surface in impression payloads", () => {
    expect(queueListingImpression(LISTING_ONE, "home")).toBe(true);
    vi.runAllTimers();
    expect(parsedBodies()).toEqual([
      { session_id: SESSION_ID, listing_ids: [LISTING_ONE], surface: "home" },
    ]);
  });

  it("drops offline views and never replays them after connectivity returns", () => {
    setOnline(false);
    expect(queueListingImpression(LISTING_ONE)).toBe(false);
    expect(recordListingPdpView(LISTING_ONE)).toBe(false);

    setOnline(true);
    vi.runAllTimers();
    expect(navigator.sendBeacon).not.toHaveBeenCalled();
  });

  it("falls back to a credential-free keepalive fetch when Beacon rejects", () => {
    Object.defineProperty(navigator, "sendBeacon", {
      configurable: true,
      writable: true,
      value: vi.fn(() => false),
    });
    const fetchMock = vi.fn(() => Promise.resolve(new Response(null, { status: 202 })));
    vi.stubGlobal("fetch", fetchMock);

    expect(recordListingPdpView(LISTING_ONE)).toBe(true);

    expect(fetchMock).toHaveBeenCalledWith(
      `${API_ORIGIN}/telemetry/views`,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          session_id: SESSION_ID,
          listing_id: LISTING_ONE,
          surface: "pdp",
        }),
        credentials: "omit",
        keepalive: true,
        referrerPolicy: "no-referrer",
      }),
    );
  });
});
