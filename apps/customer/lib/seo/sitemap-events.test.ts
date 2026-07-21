import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchEventSitemapSlugs, isEventStaleForSitemap } from "./sitemap-events";

describe("isEventStaleForSitemap", () => {
  const now = new Date("2026-07-21T00:00:00.000Z").getTime();

  it("keeps events with unknown or recent instances, drops long-past ones", () => {
    expect(isEventStaleForSitemap(null, now)).toBe(false);
    expect(isEventStaleForSitemap("not-a-date", now)).toBe(false);
    // 5 days ago → within the 30-day grace window → kept.
    expect(isEventStaleForSitemap("2026-07-16T00:00:00.000Z", now)).toBe(false);
    // 60 days ago → stale → dropped.
    expect(isEventStaleForSitemap("2026-05-22T00:00:00.000Z", now)).toBe(true);
  });
});

describe("fetchEventSitemapSlugs", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("fails closed (no fetch, empty chunk) when the API base is unset in production", async () => {
    // A public sitemap must never emit a localhost loc: with no configured API
    // base, a production build resolves to null and the chunk is simply empty.
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "");
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    await expect(fetchEventSitemapSlugs()).resolves.toEqual([]);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("returns published, non-stale slugs when the API base is set", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.vergeo5.com");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          items: [
            { slug: "lusaka-night-market", next_starts_at: null },
            { slug: "old-expo", next_starts_at: "2020-01-01T00:00:00.000Z" },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const slugs = await fetchEventSitemapSlugs();

    expect(fetchSpy).toHaveBeenCalledOnce();
    expect(fetchSpy.mock.calls[0]?.[0]).toBe("https://api.vergeo5.com/events");
    // Stale "old-expo" is filtered; the fresh one is kept.
    expect(slugs).toEqual(["lusaka-night-market"]);
  });
});
