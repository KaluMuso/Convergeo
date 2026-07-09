import type { ReactNode } from "react";

export type HeroCarouselSlide = {
  key: string;
  title: ReactNode;
  subtitle?: ReactNode;
  media?: ReactNode;
  cta?: ReactNode;
};

export type HeroCarouselProps = {
  slides: HeroCarouselSlide[];
  className?: string;
};

export function HeroCarousel({ slides, className }: HeroCarouselProps) {
  const slide = slides[0];

  if (!slide) {
    return null;
  }

  return (
    <section
      className={className}
      data-testid="hero-carousel"
      style={{
        borderRadius: "var(--r-lg)",
        overflow: "hidden",
        border: "1px solid var(--border)",
        backgroundColor: "var(--surface)",
      }}
    >
      {slide.media}
      <div style={{ padding: "var(--sp-4)", display: "grid", gap: "var(--sp-2)" }}>
        <h1
          className="font-display"
          style={{
            margin: 0,
            fontSize: "var(--fs-h1)",
            lineHeight: 1.15,
            color: "var(--display-ink)",
          }}
        >
          {slide.title}
        </h1>
        {slide.subtitle ? (
          <p style={{ margin: 0, fontSize: "var(--fs-body)", color: "var(--text-2)" }}>
            {slide.subtitle}
          </p>
        ) : null}
        {slide.cta}
      </div>
    </section>
  );
}
