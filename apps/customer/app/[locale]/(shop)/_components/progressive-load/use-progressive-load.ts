"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";

export type ProgressiveLoadStatus = "ready" | "loading" | "error" | "complete";

export type ProgressivePage<T> = {
  items: T[];
  /** Opaque cursor for the next page, or null when exhausted. */
  nextCursor: string | null;
};

export type ProgressiveLoadOptions<T extends { id: string }> = {
  /** Server-rendered first page (SEO / first paint). */
  initialItems: T[];
  /** Cursor for the page after `initialItems`, or null when none. */
  initialCursor: string | null;
  /**
   * Stable identity for the current filter/sort/query/locale set.
   * When this changes, items and cursor reset to the initial page.
   */
  resetKey: string;
  fetchPage: (cursor: string, signal: AbortSignal) => Promise<ProgressivePage<T>>;
  /**
   * When true (default), use IntersectionObserver to trigger one fetch when the
   * sentinel enters the viewport. Disabled when unsupported, when the user has
   * `Save-Data`, or when `preferButtonOnly` is set.
   */
  enableIntersectionObserver?: boolean;
  preferButtonOnly?: boolean;
};

export type ProgressiveLoadResult<T extends { id: string }> = {
  items: T[];
  status: ProgressiveLoadStatus;
  hasMore: boolean;
  lastAppendedCount: number;
  errorMessage: string | null;
  loadMore: () => void;
  sentinelRef: RefObject<HTMLDivElement | null>;
};

function prefersSaveData(): boolean {
  if (typeof navigator === "undefined") return false;
  const conn = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
  return Boolean(conn?.saveData);
}

function mergeUniqueById<T extends { id: string }>(existing: T[], incoming: T[]): T[] {
  if (incoming.length === 0) return existing;
  const seen = new Set(existing.map((item) => item.id));
  const appended: T[] = [];
  for (const item of incoming) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    appended.push(item);
  }
  return appended.length === 0 ? existing : [...existing, ...appended];
}

/**
 * Accessible cursor/page progressive loading for discovery lists.
 *
 * - Baseline: explicit Load more (keyboard / AT / failure / reduced-data).
 * - Enhancement: IntersectionObserver edge-trigger (one fetch per enter).
 * - Guards: abort + request generation, id dedupe, cursor-loop detection.
 */
export function useProgressiveLoad<T extends { id: string }>(
  options: ProgressiveLoadOptions<T>,
): ProgressiveLoadResult<T> {
  const {
    initialItems,
    initialCursor,
    resetKey,
    fetchPage,
    enableIntersectionObserver = true,
    preferButtonOnly = false,
  } = options;

  const [items, setItems] = useState(initialItems);
  const [cursor, setCursor] = useState<string | null>(initialCursor);
  const [status, setStatus] = useState<ProgressiveLoadStatus>(initialCursor ? "ready" : "complete");
  const [lastAppendedCount, setLastAppendedCount] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const cursorRef = useRef(cursor);
  const statusRef = useRef(status);
  const seenCursorsRef = useRef<Set<string>>(new Set());
  const fetchPageRef = useRef(fetchPage);
  /** Re-arm IO only after the sentinel leaves the viewport (no idle loops). */
  const ioArmedRef = useRef(true);

  cursorRef.current = cursor;
  statusRef.current = status;
  fetchPageRef.current = fetchPage;

  // Reset when filters / sort / query / locale change (new SSR page props).
  useLayoutEffect(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    requestIdRef.current += 1;
    seenCursorsRef.current = new Set();
    ioArmedRef.current = true;
    setItems(initialItems);
    setCursor(initialCursor);
    setStatus(initialCursor ? "ready" : "complete");
    setLastAppendedCount(0);
    setErrorMessage(null);
  }, [resetKey, initialItems, initialCursor]);

  const loadMore = useCallback(() => {
    const next = cursorRef.current;
    if (!next) return;
    if (statusRef.current === "loading") return;
    if (seenCursorsRef.current.has(next)) {
      // Cursor loop — stop rather than re-fetch the same page forever.
      setCursor(null);
      setStatus("complete");
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const requestId = ++requestIdRef.current;
    seenCursorsRef.current.add(next);

    setStatus("loading");
    setErrorMessage(null);

    void fetchPageRef
      .current(next, controller.signal)
      .then((page) => {
        if (requestId !== requestIdRef.current) return;
        if (controller.signal.aborted) return;

        setItems((prev) => {
          const merged = mergeUniqueById(prev, page.items);
          setLastAppendedCount(Math.max(0, merged.length - prev.length));
          return merged;
        });

        const nextCursor = page.nextCursor;
        if (nextCursor && (nextCursor === next || seenCursorsRef.current.has(nextCursor))) {
          setCursor(null);
          setStatus("complete");
          return;
        }

        setCursor(nextCursor);
        setStatus(nextCursor ? "ready" : "complete");
      })
      .catch((err: unknown) => {
        if (requestId !== requestIdRef.current) return;
        if (controller.signal.aborted) return;
        // Allow retry of the same cursor after failure.
        seenCursorsRef.current.delete(next);
        const message = err instanceof Error ? err.message : "Failed to load more results";
        setErrorMessage(message);
        setStatus("error");
        setLastAppendedCount(0);
      });
  }, []);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!enableIntersectionObserver || preferButtonOnly) return;
    if (typeof IntersectionObserver === "undefined") return;
    if (prefersSaveData()) return;
    if (status !== "ready" || !cursor) return;

    const node = sentinelRef.current;
    if (!node) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (!entry) return;
        if (!entry.isIntersecting) {
          ioArmedRef.current = true;
          return;
        }
        if (!ioArmedRef.current) return;
        if (statusRef.current !== "ready" || !cursorRef.current) return;
        ioArmedRef.current = false;
        loadMore();
      },
      { root: null, rootMargin: "200px 0px", threshold: 0 },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [enableIntersectionObserver, preferButtonOnly, status, cursor, loadMore]);

  return {
    items,
    status,
    hasMore: Boolean(cursor) && status !== "complete",
    lastAppendedCount,
    errorMessage,
    loadMore,
    sentinelRef,
  };
}
