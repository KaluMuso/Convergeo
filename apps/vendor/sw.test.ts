import { defaultCache } from "@serwist/next/worker";
import { NetworkFirst, NetworkOnly, StaleWhileRevalidate } from "serwist";
import { beforeAll, describe, expect, it } from "vitest";

import { isScanSyncApiUrl, isScannerPagePathname } from "./sw-scanner";
import {
  cacheRules,
  isApiRequest,
  isNeverCacheRoute,
  runtimeCaching,
  SW_UPDATE_POLICY,
} from "./sw";

const APP_ORIGIN = "https://vendor.vergeo5.com";
const API_ORIGIN = "https://api.vergeo5.com";

beforeAll(() => {
  process.env.NEXT_PUBLIC_API_BASE_URL = API_ORIGIN;
  process.env.NEXT_PUBLIC_DEPLOYMENT_PLANE = "production";
});

type MatchOpts = {
  origin?: string;
  destination?: string;
  method?: string;
  sameOrigin?: boolean;
};

function matchingRules(pathname: string, opts: MatchOpts = {}) {
  const {
    origin = APP_ORIGIN,
    destination = "",
    method = "GET",
    sameOrigin = origin === APP_ORIGIN,
  } = opts;
  const url = new URL(pathname, origin);
  const request = { destination, method, headers: new Headers() } as unknown as Request;
  const param = { url, request, sameOrigin } as unknown as Parameters<
    (typeof cacheRules)[number]["matcher"]
  >[0];
  return cacheRules.filter((rule) => rule.matcher(param));
}

function firstRuleName(pathname: string, opts: MatchOpts = {}): string | undefined {
  return matchingRules(pathname, opts)[0]?.name;
}

function ruleByName(name: string) {
  const rule = cacheRules.find((r) => r.name === name);
  if (!rule) throw new Error(`missing rule ${name}`);
  return rule;
}

describe("vendor service-worker runtime-cache rules", () => {
  it("HARD INVARIANT: payment and auth routes are NetworkOnly", () => {
    for (const path of [
      "/en/login",
      "/en/signup",
      "/en/otp",
      "/en/logout",
      "/en/reset-password",
      "/en/accept-invite",
      "/en/payouts",
      "/en/payouts/method",
      "/en/payment",
      "/en/checkout",
    ]) {
      const matched = matchingRules(path, { destination: "document" });
      expect(matched.map((r) => r.name)).toEqual(["never-cache"]);
      expect(matched[0]?.handler).toBeInstanceOf(NetworkOnly);
      expect(isNeverCacheRoute(new URL(path, APP_ORIGIN).pathname)).toBe(true);
    }
  });

  it("event scanner pages use StaleWhileRevalidate ahead of default cache", () => {
    const path = "/en/events/ev-42/scan";
    expect(isScannerPagePathname(path)).toBe(true);
    expect(firstRuleName(path, { destination: "document" })).toBe("event-scanner-pages");
    expect(ruleByName("event-scanner-pages").handler).toBeInstanceOf(StaleWhileRevalidate);
  });

  it("scan-sync API uses NetworkFirst; other API GETs stay private", () => {
    const syncPath = "/events/ev-42/instances/inst-1/scan-sync";
    const syncUrl = new URL(syncPath, API_ORIGIN);
    expect(isScanSyncApiUrl(syncUrl)).toBe(true);
    expect(
      firstRuleName(syncPath, {
        origin: API_ORIGIN,
        sameOrigin: false,
      }),
    ).toBe("event-scanner-sync-api");
    expect(ruleByName("event-scanner-sync-api").handler).toBeInstanceOf(NetworkFirst);

    expect(
      firstRuleName("/vendor/orders", {
        origin: API_ORIGIN,
        sameOrigin: false,
      }),
    ).toBe("api-private");
    expect(ruleByName("api-private").handler).toBeInstanceOf(NetworkOnly);
    expect(isApiRequest(new URL("/vendor/orders", API_ORIGIN))).toBe(true);
  });

  it("appends Next.js defaultCache after custom rules", () => {
    expect(runtimeCaching.length).toBe(cacheRules.length + defaultCache.length);
    expect(runtimeCaching[0]?.handler).toBeInstanceOf(NetworkOnly);
  });

  it("SAFE update lifecycle: no silent skip-waiting / clients-claim", () => {
    expect(SW_UPDATE_POLICY.skipWaiting).toBe(false);
    expect(SW_UPDATE_POLICY.clientsClaim).toBe(false);
  });
});
