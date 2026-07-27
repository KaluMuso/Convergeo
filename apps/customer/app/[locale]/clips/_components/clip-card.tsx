"use client";

import { useTranslations } from "next-intl";

import { SizeChip } from "./size-chip";

import type { Clip } from "./types";

/**
 * M17-P04 — one poster-first card.
 *
 * The card renders **no `<video>` of its own**. D-V6 gives the whole feed exactly
 * one recycled element, owned by the container; a per-card `<video>` is how a
 * feed ends up holding twenty decoders and a hundred megabytes of buffer.
 *
 * `caption` is untrusted vendor text and is rendered as a text node — never as
 * HTML, and never through `dangerouslySetInnerHTML`.
 */
export function ClipCard({
  clip,
  index,
  active,
  playing,
  nearby,
  sizeBytes,
  onPlay,
  children,
}: {
  clip: Clip;
  index: number;
  active: boolean;
  playing: boolean;
  nearby: boolean;
  sizeBytes: number | null;
  onPlay: (clipId: string) => void;
  /** M17-P05 mounts the shoppable overlay here. See the container. */
  children?: React.ReactNode;
}) {
  const t = useTranslations("clips");
  const vendorName = clip.vendor.display_name ?? "";

  return (
    <section
      data-testid="clip-card"
      data-clip-id={clip.id}
      data-clip-index={index}
      data-active={active ? "true" : "false"}
      aria-label={t("a11y.clipLabel", { vendor: vendorName })}
      className="relative flex h-[100dvh] w-full snap-start snap-always items-center justify-center overflow-hidden bg-bg-2"
    >
      {/* Poster-first: nothing but this WebP is fetched until an explicit tap.
          Cards beyond viewport +/-1 render no <img> at all, so scrolling past
          fifty clips does not queue fifty poster requests. */}
      {nearby && clip.poster_url ? (
        // Plain <img>, not next/image: Cloudinary already serves f_auto/q_auto
        // WebP at a fixed poster size, so next/image would add a second optimiser
        // hop and client JS to a route with a 150 KB gz budget.
        <img
          src={clip.poster_url}
          alt={t("a11y.posterAlt", { vendor: vendorName })}
          data-testid="clip-poster"
          loading={index === 0 ? "eager" : "lazy"}
          decoding="async"
          className="absolute inset-0 h-full w-full object-cover"
        />
      ) : (
        <div
          aria-hidden
          className="absolute inset-0 bg-bg-2"
          data-testid="clip-poster-placeholder"
        />
      )}

      {/* Tap-to-play. The button *is* the play affordance — there is no hover
          state on a phone, and no gesture that starts a download by accident. */}
      {!playing ? (
        <button
          type="button"
          data-testid="clip-play-button"
          onClick={() => onPlay(clip.id)}
          aria-label={t("player.play")}
          className="tap relative z-10 inline-flex min-h-11 min-w-11 items-center gap-2 rounded-full border border-border bg-surface/90 px-4 py-3 text-sm font-medium text-text focus-visible:outline-none focus-visible:shadow-focusRing"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            className="h-5 w-5"
            aria-hidden
          >
            <path d="M8 5v14l11-7z" />
          </svg>
          <span>{t("player.tapToPlay")}</span>
        </button>
      ) : null}

      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 flex flex-col gap-2 bg-gradient-to-t from-bg/90 to-transparent p-4 pb-24">
        <div className="pointer-events-auto flex flex-wrap items-center gap-2">
          {/* D-V5: the chip is next to the play control, before any byte moves. */}
          <SizeChip bytes={sizeBytes} />
          {clip.duration_s ? (
            <span className="rounded-full bg-surface/80 px-2 py-1 text-xs text-muted">
              {t("player.duration", { seconds: clip.duration_s })}
            </span>
          ) : null}
        </div>

        <p className="text-sm font-medium text-text">
          {t("feed.byVendor", { vendor: vendorName })}
        </p>

        {clip.caption ? (
          <p
            data-testid="clip-caption"
            aria-label={t("a11y.captionLabel")}
            className="line-clamp-3 text-sm text-text"
          >
            {clip.caption}
          </p>
        ) : null}

        <p className="text-xs text-muted">
          {t("feed.likeCount", { count: clip.like_count })} ·{" "}
          {t("feed.viewCount", { count: clip.view_count })}
        </p>

        {/* ------------------------------------------------------------------
            M17-P05 OVERLAY MOUNT POINT
            The shoppable cart overlay renders here. This slot is intentionally
            empty and behaviourless: P05 owns the overlay entirely, and a stub
            with behaviour would be a second implementation to delete later.
            ------------------------------------------------------------------ */}
        <div data-testid="clip-overlay-slot" className="pointer-events-auto empty:hidden">
          {children}
        </div>
      </div>
    </section>
  );
}
