"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";

const DEFAULT_AUTO_ADVANCE_MS = 5000;
const CONTROL_MIN_SIZE_PX = 44;

export type HeroCarouselSlide = {
  key: string;
  eyebrow?: ReactNode;
  title?: ReactNode;
  subtitle?: ReactNode;
  media?: ReactNode;
  cta?: ReactNode;
};

export type HeroCarouselLabels = {
  previous: string;
  next: string;
  slideOf: (current: number, total: number) => string;
  ariaLabel?: string;
};

export type HeroCarouselProps = {
  slides: HeroCarouselSlide[];
  labels: HeroCarouselLabels;
  className?: string;
  /** Stable id for the primary heading (slide 1). */
  headingId?: string;
  autoAdvanceMs?: number;
};

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  return reduced;
}

function usePrefersReducedData(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const conn = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
    if (conn?.saveData) {
      setReduced(true);
      return;
    }

    if (typeof window.matchMedia !== "function") {
      return;
    }

    const mq = window.matchMedia("(prefers-reduced-data: reduce)");
    const update = () => setReduced(mq.matches || Boolean(conn?.saveData));
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  return reduced;
}

function normalizeIndex(index: number, total: number): number {
  if (total <= 0) {
    return 0;
  }
  return ((index % total) + total) % total;
}

export function HeroCarousel({
  slides,
  labels,
  className,
  headingId,
  autoAdvanceMs = DEFAULT_AUTO_ADVANCE_MS,
}: HeroCarouselProps) {
  const carouselId = useId();
  const stripRef = useRef<HTMLDivElement>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [liveMessage, setLiveMessage] = useState("");
  const [isHovered, setIsHovered] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const [isDocumentVisible, setIsDocumentVisible] = useState(true);
  const prefersReducedMotion = usePrefersReducedMotion();
  const prefersReducedData = usePrefersReducedData();

  const total = slides.length;
  const canAutoAdvance =
    total > 1 && !prefersReducedMotion && !prefersReducedData && autoAdvanceMs > 0;

  const announceSlide = useCallback(
    (index: number) => {
      setLiveMessage(labels.slideOf(index + 1, total));
    },
    [labels, total],
  );

  const scrollToIndex = useCallback(
    (index: number, behavior: ScrollBehavior, announce: boolean) => {
      const normalized = normalizeIndex(index, total);
      const strip = stripRef.current;
      if (strip) {
        const slide = strip.children.item(normalized) as HTMLElement | null;
        if (slide) {
          if (typeof slide.scrollIntoView === "function") {
            slide.scrollIntoView({
              behavior: prefersReducedMotion ? "auto" : behavior,
              inline: "start",
              block: "nearest",
            });
          } else {
            strip.scrollLeft = slide.offsetLeft;
          }
        }
      }
      setCurrentIndex(normalized);
      if (announce) {
        announceSlide(normalized);
      }
    },
    [announceSlide, prefersReducedMotion, total],
  );

  const goPrevious = useCallback(
    (announce = true) => {
      scrollToIndex(currentIndex - 1, "smooth", announce);
    },
    [currentIndex, scrollToIndex],
  );

  const goNext = useCallback(
    (announce = true) => {
      scrollToIndex(currentIndex + 1, "smooth", announce);
    },
    [currentIndex, scrollToIndex],
  );

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        goPrevious(true);
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        goNext(true);
      }
    },
    [goNext, goPrevious],
  );

  const handleScroll = useCallback(() => {
    const strip = stripRef.current;
    if (!strip || strip.children.length === 0) {
      return;
    }
    const center = strip.scrollLeft + strip.clientWidth / 2;
    let closest = 0;
    let closestDistance = Number.POSITIVE_INFINITY;
    for (let i = 0; i < strip.children.length; i += 1) {
      const child = strip.children.item(i) as HTMLElement;
      const childCenter = child.offsetLeft + child.offsetWidth / 2;
      const distance = Math.abs(center - childCenter);
      if (distance < closestDistance) {
        closestDistance = distance;
        closest = i;
      }
    }
    setCurrentIndex(closest);
  }, []);

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }
    const onVisibilityChange = () => {
      setIsDocumentVisible(document.visibilityState === "visible");
    };
    onVisibilityChange();
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  }, []);

  useEffect(() => {
    if (!canAutoAdvance || isHovered || isFocused || !isDocumentVisible) {
      return;
    }

    const timer = window.setInterval(() => {
      scrollToIndex(currentIndex + 1, "smooth", false);
    }, autoAdvanceMs);

    return () => window.clearInterval(timer);
  }, [
    autoAdvanceMs,
    canAutoAdvance,
    currentIndex,
    isDocumentVisible,
    isFocused,
    isHovered,
    scrollToIndex,
  ]);

  if (total === 0) {
    return null;
  }

  const regionLabel = labels.ariaLabel ?? labels.slideOf(currentIndex + 1, total);

  return (
    <section
      className={className}
      data-testid="hero-carousel"
      role="region"
      aria-roledescription="carousel"
      aria-label={regionLabel}
      onKeyDown={handleKeyDown}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onFocusCapture={() => setIsFocused(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setIsFocused(false);
        }
      }}
      tabIndex={0}
      style={{
        position: "relative",
        overflow: "hidden",
        color: "var(--panel-text)",
      }}
    >
      <div
        ref={stripRef}
        onScroll={handleScroll}
        data-testid="hero-carousel-strip"
        style={{
          display: "flex",
          overflowX: "auto",
          scrollSnapType: "x mandatory",
          scrollBehavior: prefersReducedMotion ? "auto" : "smooth",
          WebkitOverflowScrolling: "touch",
          scrollbarWidth: "none",
          msOverflowStyle: "none",
        }}
      >
        {slides.map((slide, index) => {
          const isActive = index === currentIndex;
          const slideLabel = labels.slideOf(index + 1, total);
          const hasHeading = Boolean(slide.title);

          return (
            <div
              key={`${carouselId}-${slide.key}`}
              data-testid={`hero-carousel-slide-${index}`}
              aria-label={slideLabel}
              aria-hidden={!isActive}
              style={{
                position: "relative",
                flex: "0 0 100%",
                scrollSnapAlign: "start",
                minHeight: "clamp(18rem, 52vw, 28rem)",
                display: "grid",
                alignItems: "end",
              }}
            >
              <div
                aria-hidden
                style={{
                  position: "absolute",
                  inset: 0,
                  overflow: "hidden",
                }}
              >
                {slide.media}
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    background:
                      "linear-gradient(105deg, color-mix(in srgb, var(--panel) 88%, transparent) 0%, color-mix(in srgb, var(--panel) 55%, transparent) 38%, transparent 72%)",
                  }}
                />
              </div>

              {(slide.eyebrow || slide.title || slide.subtitle || slide.cta) && (
                <div
                  className="relative mx-auto flex w-full max-w-7xl flex-col gap-3 px-4 py-10 sm:px-6 sm:py-12 lg:px-6 lg:py-16"
                  style={{ zIndex: 1 }}
                >
                  {slide.eyebrow ? (
                    <p
                      data-testid={index === 0 ? "home-hero-brand" : undefined}
                      className="font-display"
                      style={{
                        margin: 0,
                        fontSize: "var(--fs-hero)",
                        lineHeight: 1,
                        letterSpacing: "-0.02em",
                        color: "var(--panel-text)",
                      }}
                    >
                      {slide.eyebrow}
                    </p>
                  ) : null}
                  {slide.title ? (
                    hasHeading && index === 0 && headingId ? (
                      <h1
                        id={headingId}
                        className="font-display"
                        style={{
                          margin: 0,
                          fontSize: "var(--fs-h1)",
                          lineHeight: 1.15,
                          color: "var(--panel-text)",
                        }}
                      >
                        {slide.title}
                      </h1>
                    ) : (
                      <p
                        className="font-display"
                        style={{
                          margin: 0,
                          fontSize: "var(--fs-h2)",
                          lineHeight: 1.15,
                          color: "var(--panel-text)",
                        }}
                      >
                        {slide.title}
                      </p>
                    )
                  ) : null}
                  {slide.subtitle ? (
                    <p
                      style={{
                        margin: 0,
                        maxWidth: "36rem",
                        fontSize: "var(--fs-body)",
                        color: "var(--panel-muted)",
                      }}
                    >
                      {slide.subtitle}
                    </p>
                  ) : null}
                  {slide.cta ? (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-2)" }}>
                      {slide.cta}
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div
        aria-hidden
        data-testid="hero-carousel-fade"
        style={{
          pointerEvents: "none",
          position: "absolute",
          insetInline: 0,
          bottom: 0,
          height: "45%",
          background:
            "linear-gradient(to top, var(--bg) 0%, color-mix(in srgb, var(--bg) 72%, transparent) 38%, transparent 100%)",
        }}
      />

      {total > 1 ? (
        <>
          <div
            style={{
              position: "absolute",
              insetInline: "var(--sp-2)",
              top: "50%",
              transform: "translateY(-50%)",
              display: "flex",
              justifyContent: "space-between",
              pointerEvents: "none",
              zIndex: 2,
            }}
          >
            <button
              type="button"
              aria-label={labels.previous}
              onClick={() => goPrevious(true)}
              data-testid="hero-carousel-prev"
              style={{
                pointerEvents: "auto",
                minHeight: `${CONTROL_MIN_SIZE_PX}px`,
                minWidth: `${CONTROL_MIN_SIZE_PX}px`,
                borderRadius: "999px",
                border: "1px solid color-mix(in srgb, var(--panel-text) 25%, transparent)",
                background: "color-mix(in srgb, var(--panel) 72%, transparent)",
                color: "var(--panel-text)",
                fontSize: "1.5rem",
                lineHeight: 1,
                cursor: "pointer",
              }}
            >
              ‹
            </button>
            <button
              type="button"
              aria-label={labels.next}
              onClick={() => goNext(true)}
              data-testid="hero-carousel-next"
              style={{
                pointerEvents: "auto",
                minHeight: `${CONTROL_MIN_SIZE_PX}px`,
                minWidth: `${CONTROL_MIN_SIZE_PX}px`,
                borderRadius: "999px",
                border: "1px solid color-mix(in srgb, var(--panel-text) 25%, transparent)",
                background: "color-mix(in srgb, var(--panel) 72%, transparent)",
                color: "var(--panel-text)",
                fontSize: "1.5rem",
                lineHeight: 1,
                cursor: "pointer",
              }}
            >
              ›
            </button>
          </div>

          <div
            data-testid="hero-carousel-dots"
            style={{
              position: "absolute",
              insetInline: 0,
              bottom: "var(--sp-3)",
              display: "flex",
              justifyContent: "center",
              gap: "var(--sp-2)",
              zIndex: 2,
              pointerEvents: "none",
            }}
          >
            {slides.map((slide, index) => (
              <button
                key={`dot-${slide.key}`}
                type="button"
                aria-label={labels.slideOf(index + 1, total)}
                aria-current={index === currentIndex ? "true" : undefined}
                onClick={() => {
                  scrollToIndex(index, "smooth", true);
                }}
                data-testid={`hero-carousel-dot-${index}`}
                style={{
                  pointerEvents: "auto",
                  minHeight: `${CONTROL_MIN_SIZE_PX}px`,
                  minWidth: `${CONTROL_MIN_SIZE_PX}px`,
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  border: "none",
                  background: "transparent",
                  cursor: "pointer",
                  padding: 0,
                }}
              >
                <span
                  aria-hidden
                  style={{
                    display: "block",
                    width: index === currentIndex ? "1.5rem" : "0.5rem",
                    height: "0.5rem",
                    borderRadius: "999px",
                    background:
                      index === currentIndex
                        ? "var(--primary)"
                        : "color-mix(in srgb, var(--panel-text) 45%, transparent)",
                    transition: prefersReducedMotion
                      ? undefined
                      : "width var(--dur) var(--ease-std)",
                  }}
                />
              </button>
            ))}
          </div>

          <p className="sr-only" aria-live="polite" data-testid="hero-carousel-live">
            {liveMessage}
          </p>
        </>
      ) : null}
    </section>
  );
}
