import type { ReactNode } from "react";

export type HeroEditorialLightProps = {
  eyebrow?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  primaryCta?: ReactNode;
  secondaryCta?: ReactNode;
  media?: ReactNode;
  stats?: Array<{ label: ReactNode; value: ReactNode }>;
  className?: string;
};

export function HeroEditorialLight({
  eyebrow,
  title,
  subtitle,
  primaryCta,
  secondaryCta,
  media,
  stats,
  className,
}: HeroEditorialLightProps) {
  return (
    <section
      className={className}
      data-testid="hero-editorial-light"
      style={{
        borderRadius: "var(--r-lg)",
        backgroundColor: "var(--bg)",
        padding: "var(--sp-4)",
      }}
    >
      <div style={{ display: "grid", gap: "var(--sp-4)" }}>
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
        {primaryCta || secondaryCta ? (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-2)" }}>
            {primaryCta}
            {secondaryCta}
          </div>
        ) : null}
        {stats && stats.length > 0 ? (
          <dl
            style={{
              margin: 0,
              display: "grid",
              gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
              gap: "var(--sp-3)",
            }}
          >
            {stats.map((stat, index) => (
              <div key={index}>
                <dt style={{ margin: 0, fontSize: "var(--fs-micro)", color: "var(--text-3)" }}>
                  {stat.label}
                </dt>
                <dd
                  style={{
                    margin: "var(--sp-1) 0 0",
                    fontSize: "var(--fs-h3)",
                    fontWeight: 600,
                    color: "var(--text)",
                  }}
                >
                  {stat.value}
                </dd>
              </div>
            ))}
          </dl>
        ) : null}
        {media ? (
          <div style={{ borderRadius: "var(--r-lg)", overflow: "hidden" }}>{media}</div>
        ) : null}
      </div>
    </section>
  );
}
