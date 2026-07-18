import { defaultCache } from "@serwist/next/worker";
import {
  CacheFirst,
  ExpirationPlugin,
  NetworkFirst,
  NetworkOnly,
  StaleWhileRevalidate,
} from "serwist";
import { beforeAll, describe, expect, it } from "vitest";

import {
  cacheRules,
  isNeverCacheRoute,
  isWalletApi,
  isWalletPage,
  runtimeCaching,
  SW_UPDATE_POLICY,
} from "./sw";

const APP_ORIGIN = "https://vergeo5.com";
const API_ORIGIN = "https://api.vergeo5.com";

beforeAll(() => {
  process.env.NEXT_PUBLIC_API_BASE_URL = API_ORIGIN;
});

type MatchOpts = { origin?: string; destination?: string; sameOrigin?: boolean };

function matchingRules(pathname: string, opts: MatchOpts = {}) {
  const { origin = APP_ORIGIN, destination = "", sameOrigin = origin === APP_ORIGIN } = opts;
  const url = new URL(pathname, origin);
  const request = { destination } as unknown as Request;
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

describe("service-worker runtime-cache rules", () => {
  it("HARD INVARIANT: checkout/cart/payment/auth are NetworkOnly and never cached", () => {
    for (const path of [
      "/en/checkout",
      "/en/checkout/card/pay-123",
      "/en/checkout/pending/grp-1",
      "/en/cart",
      "/en/login",
      "/en/signup",
      "/en/otp",
    ]) {
      // exactly one rule matches, and it is the NetworkOnly never-cache rule
      const matched = matchingRules(path, { destination: "document" });
      expect(matched.map((r) => r.name)).toEqual(["never-cache"]);
      expect(matched[0]?.handler).toBeInstanceOf(NetworkOnly);
      expect(isNeverCacheRoute(new URL(path, APP_ORIGIN).pathname)).toBe(true);
    }
    // The never-cache handler is NetworkOnly — by strategy it never persists a
    // response to any cache (no stale prices can be served offline).
    const neverCache = ruleByName("never-cache").handler;
    expect(neverCache).toBeInstanceOf(NetworkOnly);
    expect(neverCache).not.toBeInstanceOf(CacheFirst);
    expect(neverCache).not.toBeInstanceOf(NetworkFirst);
    expect(neverCache).not.toBeInstanceOf(StaleWhileRevalidate);
  });

  it("catalog / PDP navigations use StaleWhileRevalidate", () => {
    for (const path of [
      "/en/p/blue-widget",
      "/en/c/electronics",
      "/en/e/expo",
      "/en/v/acme",
      "/en/categories",
      "/en/compare",
      "/en/calendar",
    ]) {
      expect(firstRuleName(path, { destination: "document" })).toBe("catalog");
    }
    expect(ruleByName("catalog").handler).toBeInstanceOf(StaleWhileRevalidate);
  });

  it("images use CacheFirst with a capped, expiring cache", () => {
    expect(firstRuleName("/some/photo.webp")).toBe("images");
    expect(
      firstRuleName("/img/x.png", { origin: "https://res.cloudinary.com", sameOrigin: false }),
    ).toBe("images");
    const images = ruleByName("images");
    expect(images.handler).toBeInstanceOf(CacheFirst);
    // Expiration plugin present → the image cache is bounded (capped).
    const plugins = (images.handler as { plugins?: unknown[] }).plugins ?? [];
    expect(plugins.some((p) => p instanceof ExpirationPlugin)).toBe(true);
  });

  it("our API GETs use NetworkFirst", () => {
    expect(firstRuleName("/products", { origin: API_ORIGIN, sameOrigin: false })).toBe("api");
    expect(ruleByName("api").handler).toBeInstanceOf(NetworkFirst);
  });

  it("folds the M10 ticket-wallet fragment into this SW (coexistence)", () => {
    expect(firstRuleName("/en/account/tickets", { destination: "document" })).toBe(
      "ticket-wallet-pages",
    );
    expect(firstRuleName("/account/tickets/t-1", { origin: API_ORIGIN, sameOrigin: false })).toBe(
      "ticket-wallet-api",
    );
    expect(ruleByName("ticket-wallet-pages").handler).toBeInstanceOf(NetworkFirst);
    expect(ruleByName("ticket-wallet-api").handler).toBeInstanceOf(NetworkFirst);
    expect(isWalletPage("/en/account/tickets")).toBe(true);
    expect(isWalletApi(new URL("/account/tickets/t-1", API_ORIGIN))).toBe(true);
    // Wallet API is not swallowed by the generic API rule (order preserved).
    expect(
      firstRuleName("/account/tickets/t-1", { origin: API_ORIGIN, sameOrigin: false }),
    ).not.toBe("api");
  });

  it("appends the Next.js defaultCache after the custom rules", () => {
    expect(runtimeCaching.length).toBe(cacheRules.length + defaultCache.length);
    // custom rules come first so they win over the framework defaults
    expect(runtimeCaching[0]?.handler).toBeInstanceOf(NetworkOnly);
  });

  it("SAFE update lifecycle: no silent skip-waiting / clients-claim", () => {
    expect(SW_UPDATE_POLICY.skipWaiting).toBe(false);
    expect(SW_UPDATE_POLICY.clientsClaim).toBe(false);
  });
});
