import type { ReactNode } from "react";

import { Skeleton } from "../skeleton";

export type HeroDefaultProps = {
  eyebrow?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  primaryCta?: ReactNode;
  secondaryCta?: ReactNode;
  media?: ReactNode;
  className?: string;
  /** Ignored — carousel campaigns use `HeroCarousel` via hero-registry. */
  slides?: unknown;
};

export function HeroDefault({
  eyebrow,
  title,
  subtitle,
  primaryCta,
  secondaryCta,
  media,
  className,
}: HeroDefaultProps) {
  return (
    <section
      className={className}
      data-testid="hero-default"
      aria-label={typeof title === "string" ? title : undefined}
      style={{
        borderRadius: "var(--r-lg)",
        border: "1px solid var(--border)",
        backgroundColor: "var(--surface)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          display: "grid",
          gap: "var(--sp-4)",
          padding: "var(--sp-4)",
        }}
      >
        {eyebrow ? (
          <p
            style={{
              margin: 0,
              fontSize: "var(--fs-micro)",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--text-3)",
            }}
          >
            {eyebrow}
          </p>
        ) : null}
        <h1
          className="font-display"
          style={{
            margin: 0,
            fontSize: "var(--fs-hero)",
            lineHeight: 1.1,
            color: "var(--display-ink)",
          }}
        >
          {title}
        </h1>
        {subtitle ? (
          <p style={{ margin: 0, fontSize: "var(--fs-body)", color: "var(--text-2)" }}>
            {subtitle}
          </p>
        ) : null}
        {media ?? (
          <div style={{ width: "100%", aspectRatio: "16 / 9" }}>
            <Skeleton shape="block" />
          </div>
        )}
        {primaryCta || secondaryCta ? (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-2)" }}>
            {primaryCta}
            {secondaryCta}
          </div>
        ) : null}
      </div>
    </section>
  );
}
