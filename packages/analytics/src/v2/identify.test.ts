// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CONSENT_COOKIE } from "../consent";

import { __resetIdsMemory, SESSION_KEY_V2 } from "./ids";
import { identifyAnalyticsSession, LINKED_KEY } from "./identify";

const SESSION = "22222222-2222-4222-8222-222222222222";
const ARGS = { apiBaseUrl: "https://api.test/", accessToken: "jwt" };

let fetchMock: ReturnType<typeof vi.fn>;

function setConsent(state: "granted" | "denied" | "unset"): void {
  document.cookie =
    state === "unset"
      ? `${CONSENT_COOKIE}=; path=/; max-age=0`
      : `${CONSENT_COOKIE}=${state}; path=/`;
}

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_ANALYTICS_V2_TRACKING", "1");
  window.localStorage.clear();
  __resetIdsMemory();
  setConsent("granted");
  Object.defineProperty(navigator, "globalPrivacyControl", {
    configurable: true,
    value: undefined,
  });
  window.localStorage.setItem(
    SESSION_KEY_V2,
    JSON.stringify({ id: SESSION, last: Date.now(), seq: 3 }),
  );
  fetchMock = vi.fn().mockResolvedValue({ ok: true });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("identifyAnalyticsSession", () => {
  it("sends only the anonymous session id, with the bearer token", async () => {
    await expect(identifyAnalyticsSession(ARGS)).resolves.toBe(true);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://api.test/analytics/identify");
    expect(JSON.parse(init.body as string)).toEqual({ session_id: SESSION });
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer jwt");
  });

  it("calls once per v2 session", async () => {
    await identifyAnalyticsSession(ARGS);
    await expect(identifyAnalyticsSession(ARGS)).resolves.toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(window.localStorage.getItem(LINKED_KEY)).toBe(SESSION);
  });

  it("does nothing when the visitor opted out", async () => {
    setConsent("denied");
    await expect(identifyAnalyticsSession(ARGS)).resolves.toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does nothing under Global Privacy Control", async () => {
    Object.defineProperty(navigator, "globalPrivacyControl", {
      configurable: true,
      value: true,
    });
    await expect(identifyAnalyticsSession(ARGS)).resolves.toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does nothing when v2 tracking is off or there is no session", async () => {
    vi.stubEnv("NEXT_PUBLIC_ANALYTICS_V2_TRACKING", "0");
    await expect(identifyAnalyticsSession(ARGS)).resolves.toBe(false);
    vi.stubEnv("NEXT_PUBLIC_ANALYTICS_V2_TRACKING", "1");
    window.localStorage.clear();
    __resetIdsMemory();
    await expect(identifyAnalyticsSession(ARGS)).resolves.toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("retries on a later call after a failure and never throws", async () => {
    fetchMock.mockRejectedValueOnce(new Error("offline"));
    await expect(identifyAnalyticsSession(ARGS)).resolves.toBe(false);
    await expect(identifyAnalyticsSession(ARGS)).resolves.toBe(true);
  });
});
