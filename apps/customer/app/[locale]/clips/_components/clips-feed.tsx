"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ClipCard } from "./clip-card";
import { DataSaverToggle } from "./data-saver-toggle";
import { FeedEmpty, FeedError, FeedSkeleton } from "./feed-states";
import { ClipOverlay } from "./overlay/clip-overlay";
import {
  connectionKind,
  browserRequestsSaveData,
  mayAutoplay,
  preferredRendition,
  preloadMode,
  readStoredDataSaver,
  writeStoredDataSaver,
  type ConnectionKind,
} from "./playback-policy";
import { pickRendition } from "./size";

import type { Clip, ClipFeedPage } from "./types";

/**
 * M17-P04 — the Clips feed container.
 *
 * Three things live here and nowhere else, because each of them is only safe if
 * there is exactly one of it:
 *
 * 1. **The single `<video>` element** (D-V6). It is rendered once, fixed over the
 *    feed, and its `src` is swapped as the visitor taps between clips. Per-card
 *    video elements are how a feed ends up holding twenty decoders; a DOM
 *    assertion in the tests holds this to exactly one.
 * 2. **The data-saver / connection decision** (D-V1, D-V2). One place decides
 *    whether a byte of video may be fetched, so there is no second code path
 *    that could forget the cellular rule.
 * 3. **Source detachment.** When the active clip scrolls out of view (or the
 *    visitor pauses), the element's `src` is removed and `load()` is called,
 *    which is what actually releases the buffer — pausing alone does not.
 */
export function ClipsFeed({
  initialItems,
  initialCursor,
  apiBaseUrl,
  locale = "en",
}: {
  initialItems: Clip[];
  initialCursor: string | null;
  apiBaseUrl: string;
  locale?: string;
}) {
  const t = useTranslations("clips");

  const [items, setItems] = useState<Clip[]>(initialItems);
  const [cursor, setCursor] = useState<string | null>(initialCursor);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState(false);

  // Saver starts ON for the first paint and is reconciled from storage in an
  // effect. Reading storage during render would either break SSR or force the
  // first frame to guess "off" — and guessing "off" spends someone's bundle.
  const [dataSaverOn, setDataSaverOn] = useState(true);
  const [connection, setConnection] = useState<ConnectionKind>("unknown");
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  const [inViewId, setInViewId] = useState<string | null>(initialItems[0]?.id ?? null);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [failedId, setFailedId] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // --- Environment reconciliation -------------------------------------------
  useEffect(() => {
    // `navigator` is structurally typed here: the Network Information API is not
    // in lib.dom, and declaring it globally would assert it exists everywhere —
    // which is exactly the assumption the "unknown means cellular" rule rejects.
    const nav = navigator as unknown as Parameters<typeof connectionKind>[0];
    const stored = readStoredDataSaver(window.localStorage);
    // The browser's own Save-Data header is a stated preference; it can turn
    // saver on but never off.
    setDataSaverOn(stored || browserRequestsSaveData(nav));

    const readConnection = () => setConnection(connectionKind(nav));
    readConnection();

    const info = (navigator as { connection?: EventTarget }).connection;
    info?.addEventListener?.("change", readConnection);

    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    setPrefersReducedMotion(motion.matches);
    const onMotionChange = (event: MediaQueryListEvent) => setPrefersReducedMotion(event.matches);
    motion.addEventListener("change", onMotionChange);

    return () => {
      info?.removeEventListener?.("change", readConnection);
      motion.removeEventListener("change", onMotionChange);
    };
  }, []);

  const onSaverChange = useCallback((next: boolean) => {
    setDataSaverOn(next);
    writeStoredDataSaver(window.localStorage, next);
    if (next) {
      // Turning saver on stops what is already playing. Anything else would let
      // the setting mean "from the next clip onward", which is not what it says.
      setPlayingId(null);
    }
  }, []);

  // --- Which clip is on screen ---------------------------------------------
  useEffect(() => {
    const root = scrollRef.current;
    if (!root || typeof IntersectionObserver === "undefined") {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && entry.intersectionRatio >= 0.6) {
            const id = (entry.target as HTMLElement).dataset.clipId;
            if (id) {
              setInViewId(id);
            }
          }
        }
      },
      { root, threshold: [0.6] },
    );
    for (const card of root.querySelectorAll("[data-clip-id]")) {
      observer.observe(card);
    }
    return () => observer.disconnect();
  }, [items]);

  // Scrolling away from the playing clip unloads it. This is the viewport +/-1
  // rule: at most one clip is ever loaded, and it is the one you are looking at.
  useEffect(() => {
    if (playingId && inViewId !== playingId) {
      setPlayingId(null);
    }
  }, [inViewId, playingId]);

  const activeIndex = useMemo(
    () =>
      Math.max(
        0,
        items.findIndex((clip) => clip.id === inViewId),
      ),
    [items, inViewId],
  );

  const rendition = preferredRendition(dataSaverOn, connection);
  const playingClip = useMemo(
    () => items.find((clip) => clip.id === playingId) ?? null,
    [items, playingId],
  );
  const playingSource = playingClip ? pickRendition(playingClip, rendition) : null;

  // --- The single <video>: attach on play, DETACH on stop -------------------
  useEffect(() => {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    if (!playingClip || !playingSource) {
      // Removing the attribute and calling load() is what releases the buffer.
      // Pausing keeps the downloaded bytes — and the download — alive.
      video.removeAttribute("src");
      video.load();
      return;
    }
    if (video.getAttribute("src") !== playingSource.url) {
      video.setAttribute("src", playingSource.url);
      video.load();
    }
    void video.play().catch(() => {
      // Autoplay refusal or a decode error: fall back to the poster rather than
      // leaving a black rectangle where a clip should be.
      setFailedId(playingClip.id);
      setPlayingId(null);
    });
  }, [playingClip, playingSource]);

  // --- Autoplay: the one permitted case ------------------------------------
  useEffect(() => {
    if (!inViewId || playingId) {
      return;
    }
    const allowed = mayAutoplay({
      connection,
      dataSaverOn,
      prefersReducedMotion,
      inView: true,
    });
    if (allowed) {
      setPlayingId(inViewId);
    }
  }, [inViewId, playingId, connection, dataSaverOn, prefersReducedMotion]);

  const onPlay = useCallback((clipId: string) => {
    setFailedId(null);
    // A tap on a card's play control is proof that card is on screen, so it also
    // settles "what is in view". Without this, a tap landing between two
    // IntersectionObserver callbacks would be unloaded by the rule below.
    setInViewId(clipId);
    setPlayingId(clipId);
  }, []);

  const onStop = useCallback(() => setPlayingId(null), []);

  // --- Pagination -----------------------------------------------------------
  const loadMore = useCallback(async () => {
    if (!cursor || loadingMore) {
      return;
    }
    setLoadingMore(true);
    setLoadError(false);
    try {
      const response = await fetch(
        `${apiBaseUrl}/clips/feed?cursor=${encodeURIComponent(cursor)}`,
        { headers: { Accept: "application/json" } },
      );
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const page = (await response.json()) as ClipFeedPage;
      setItems((current) => [...current, ...page.items]);
      setCursor(page.next_cursor);
    } catch {
      setLoadError(true);
    } finally {
      setLoadingMore(false);
    }
  }, [apiBaseUrl, cursor, loadingMore]);

  if (items.length === 0) {
    return <FeedEmpty />;
  }

  return (
    <div className="relative">
      <div className="sticky top-0 z-30 flex items-center justify-between gap-2 bg-bg/90 px-4 py-2 backdrop-blur">
        <h1 className="text-h3 font-semibold text-text">{t("feed.title")}</h1>
        <DataSaverToggle on={dataSaverOn} onChange={onSaverChange} />
      </div>

      {/* Reduced motion removes the snap animation as well as autoplay: a
          scroll that yanks is as much of a motion problem as a video that moves. */}
      <div
        ref={scrollRef}
        data-testid="clips-scroller"
        aria-label={t("a11y.feedLabel")}
        className={`h-[100dvh] w-full overflow-y-auto ${
          prefersReducedMotion ? "" : "snap-y snap-mandatory scroll-smooth"
        } motion-reduce:scroll-auto`}
      >
        {items.map((clip, index) => (
          <ClipCard
            key={clip.id}
            clip={clip}
            index={index}
            active={clip.id === inViewId}
            playing={clip.id === playingId}
            nearby={Math.abs(index - activeIndex) <= 1}
            sizeBytes={pickRendition(clip, rendition)?.bytes ?? null}
            onPlay={onPlay}
          >
            {/* M17-P05 mounts here — the slot M17-P04 left, nothing restructured. */}
            <ClipOverlay clip={clip} locale={locale} />
          </ClipCard>
        ))}

        {failedId ? (
          <p role="status" className="px-4 py-3 text-sm text-danger">
            {t("player.failed.title")}
          </p>
        ) : null}

        {cursor ? (
          <div className="flex justify-center px-4 py-6">
            <button
              type="button"
              onClick={() => void loadMore()}
              disabled={loadingMore}
              data-testid="clips-load-more"
              className="tap min-h-11 rounded-full border border-border bg-surface px-4 py-2 text-sm text-text focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {loadingMore ? t("feed.loading") : t("feed.loadMore")}
            </button>
          </div>
        ) : (
          <p className="px-4 py-6 text-center text-sm text-muted">{t("feed.endOfFeed")}</p>
        )}

        {loadError ? <FeedError onRetry={() => void loadMore()} /> : null}
      </div>

      {/* THE single <video> (D-V6). One element for the whole feed, fixed over
          the active card. It is rendered only while something is playing, so a
          poster-only scroll never even has a video element in the document. */}
      {playingClip ? (
        <div className="pointer-events-none fixed inset-0 z-20 flex items-center justify-center">
          <video
            ref={videoRef}
            data-testid="clips-video"
            aria-label={t("a11y.playerLabel")}
            className="pointer-events-auto h-full w-full object-contain"
            playsInline
            muted
            controls
            preload={preloadMode(dataSaverOn, connection)}
            poster={playingClip.poster_url ?? undefined}
            onEnded={onStop}
            onError={() => {
              setFailedId(playingClip.id);
              setPlayingId(null);
            }}
          >
            {/* Vendor clips carry no caption track yet; the element declares one
                so assistive tech is not told the video simply has no text
                alternative. The visible caption text lives on the card. */}
            <track kind="captions" />
          </video>
        </div>
      ) : null}
    </div>
  );
}

export { FeedSkeleton };
