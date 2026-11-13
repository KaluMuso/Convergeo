import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { setAnalyticsConsent } from "./consent";
import { searchSessionHeaders } from "./search-session";
import { __resetIdsMemory, SESSION_KEY_V2, touchSession } from "./v2/ids";

const ID = "3f1c2a4e-1111-4222-8333-444455556666";

function seed(): void {
  window.localStorage.setItem(SESSION_KEY_V2, JSON.stringify({ id: ID, last: Date.now(), seq: 1 }));
}

describe("searchSessionHeaders", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.cookie = "vg_analytics_consent=; max-age=0; path=/";
    __resetIdsMemory();
    process.env.NEXT_PUBLIC_ANALYTICS_V2_TRACKING = "1";
    Object.defineProperty(navigator, "globalPrivacyControl", {
      value: undefined,
      configurable: true,
    });
  });
  afterEach(() => {
    delete process.env.NEXT_PUBLIC_ANALYTICS_V2_TRACKING;
  });

  it("sends the v2 session id when tracking is on and not counts-only", () => {
    seed();
    expect(searchSessionHeaders()).toEqual({ "X-Analytics-Session": ID });
  });

  it("sends nothing when v2 tracking is off", () => {
    seed();
    process.env.NEXT_PUBLIC_ANALYTICS_V2_TRACKING = "0";
    expect(searchSessionHeaders()).toEqual({});
  });

  it("sends nothing when consent is denied", () => {
    seed();
    setAnalyticsConsent("denied");
    expect(searchSessionHeaders()).toEqual({});
  });

  it("sends nothing under Global Privacy Control", () => {
    seed();
    Object.defineProperty(navigator, "globalPrivacyControl", { value: true, configurable: true });
    expect(searchSessionHeaders()).toEqual({});
  });

  it("sends nothing when no v2 session exists yet (and does not create one)", () => {
    expect(searchSessionHeaders()).toEqual({});
    expect(window.localStorage.getItem(SESSION_KEY_V2)).toBeNull();
  });

  it("sends the id when consent is granted", () => {
    touchSession(Date.now());
    setAnalyticsConsent("granted");
    expect(Object.keys(searchSessionHeaders())).toEqual(["X-Analytics-Session"]);
  });
});
