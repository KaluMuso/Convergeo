"use client";

import { Skeleton } from "@vergeo/ui/src/skeleton";
import { useCallback, useEffect, useRef, useState, type ComponentType } from "react";

import type { FeedLabels, FeedSection } from "./feed-types";

/**
 * Infinite-scroll trigger for the home feed. Deliberately tiny: the renderer +
 * fetcher live in `feed-pages.tsx`, imported only when the sentinel nears the
 * viewport, so the first-load JS of `/[locale]` stays within budget.
 */
type FeedPagesModule = typeof import("./feed-pages");
type Status = "idle" | "loading" | "error" | "done";

const ROOT_MARGIN = "600px 0px";

async function readAccessToken(): Promise<string | null> {
  try {
    const { getReadyCustomerSession } = await import("../../../../../lib/customer-session");
    const session = await getReadyCustomerSession();
    return session?.access_token ?? null;
  } catch {
    return null;
  }
}

export function HomeFeedLoader({
  initialCursor,
  locale,
  labels,
}: {
  initialCursor: string | null;
  locale: string;
  labels: FeedLabels;
}) {
  const [cursor, setCursor] = useState<string | null>(initialCursor);
  const [sections, setSections] = useState<FeedSection[]>([]);
  const [status, setStatus] = useState<Status>(initialCursor ? "idle" : "done");
  const [Pages, setPages] = useState<ComponentType<{
    sections: FeedSection[];
    locale: string;
    labels: FeedLabels;
  }> | null>(null);
  const moduleRef = useRef<FeedPagesModule | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const inFlight = useRef(false);

  const loadNext = useCallback(async () => {
    if (!cursor || inFlight.current) return;
    inFlight.current = true;
    setStatus("loading");
    try {
      const mod = moduleRef.current ?? (await import("./feed-pages"));
      if (!moduleRef.current) {
        moduleRef.current = mod;
        setPages(() => mod.FeedPages);
      }
      const page = await mod.fetchFeedPage(cursor, locale, await readAccessToken());
      setSections((current) => {
        const seen = new Set(current.map((section) => section.id));
        return [...current, ...page.sections.filter((section) => !seen.has(section.id))];
      });
      setCursor(page.next_cursor);
      setStatus(page.next_cursor ? "idle" : "done");
    } catch {
      setStatus("error");
    } finally {
      inFlight.current = false;
    }
  }, [cursor, locale]);

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node || status !== "idle") return;
    if (typeof IntersectionObserver === "undefined") {
      void loadNext();
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) void loadNext();
      },
      { rootMargin: ROOT_MARGIN },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [loadNext, status]);

  return (
    <>
      {Pages && sections.length > 0 ? (
        <Pages sections={sections} locale={locale} labels={labels} />
      ) : null}
      <div ref={sentinelRef} data-testid="home-feed-sentinel" aria-live="polite">
        {status === "loading" ? (
          <div className="flex flex-col gap-3" aria-busy="true">
            <span className="sr-only">{labels.loadingMore}</span>
            <Skeleton shape="block" className="h-7 w-48 rounded" />
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-3 lg:grid-cols-4">
              {Array.from({ length: 4 }, (_, index) => (
                <Skeleton key={index} shape="block" className="aspect-[3/4] w-full rounded-lg" />
              ))}
            </div>
          </div>
        ) : null}
        {status === "error" ? (
          <div className="flex items-center gap-3 text-sm text-muted">
            <span>{labels.loadError}</span>
            <button
              type="button"
              className="inline-flex min-h-11 items-center rounded-md border border-border px-4 font-medium text-primary"
              onClick={() => {
                setStatus("idle");
                void loadNext();
              }}
            >
              {labels.retry}
            </button>
          </div>
        ) : null}
        {status === "done" ? (
          <p className="py-4 text-center text-sm text-muted" data-testid="home-feed-end">
            {labels.end}
          </p>
        ) : null}
      </div>
    </>
  );
}
