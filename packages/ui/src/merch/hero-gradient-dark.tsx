import type { ReactNode } from "react";

export type HeroGradientDarkProps = {
  title: ReactNode;
  subtitle?: ReactNode;
  primaryCta?: ReactNode;
  media?: ReactNode;
  className?: string;
};

export function HeroGradientDark({
  title,
  subtitle,
  primaryCta,
  media,
  className,
}: HeroGradientDarkProps) {
  return (
    <section
      className={className}
      data-testid="hero-gradient-dark"
      style={{
        borderRadius: "var(--r-lg)",
        background: "linear-gradient(145deg, var(--panel) 0%, var(--panel-2) 100%)",
        color: "var(--panel-text)",
        padding: "var(--sp-5) var(--sp-4)",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div
        aria-hidden
        style={{
          position: "absolute",
          inset: "-20%",
          background:
            "radial-gradient(circle at 20% 20%, rgba(255,255,255,0.08), transparent 55%), radial-gradient(circle at 80% 70%, rgba(200,134,26,0.18), transparent 50%)",
        }}
      />
      <div style={{ position: "relative", display: "grid", gap: "var(--sp-3)" }}>
        <h1
          className="font-display"
          style={{
            margin: 0,
            fontSize: "var(--fs-hero)",
            lineHeight: 1.1,
            color: "var(--panel-text)",
          }}
        >
          {title}
        </h1>
        {subtitle ? (
          <p style={{ margin: 0, fontSize: "var(--fs-body)", color: "var(--panel-muted)" }}>
            {subtitle}
          </p>
        ) : null}
        {primaryCta}
        {media ? (
          <div
            style={{ borderRadius: "var(--r-lg)", overflow: "hidden", marginTop: "var(--sp-2)" }}
          >
            {media}
          </div>
        ) : null}
      </div>
    </section>
  );
}
