import type { ComponentType, ReactNode } from "react";

type LinkLike = ComponentType<{ href: string; className?: string; children: ReactNode }>;

export type PanelHeroProps = {
  title: ReactNode;
  subtitle?: ReactNode;
  /** Extra content rendered between the subtitle and the CTA row (e.g. a result count). */
  children?: ReactNode;
  /** Optional primary CTA (rendered as a panel-text button) plus a muted pitch. */
  cta?: {
    href: string;
    label: ReactNode;
    pitch?: ReactNode;
    LinkComponent: LinkLike;
  };
  className?: string;
};

/**
 * Shared charcoal hero band for hub pages (services / events / directory).
 * Warm `--panel` chrome — never aubergine (audit §6.1). RSC-safe.
 */
export function PanelHero({ title, subtitle, children, cta, className }: PanelHeroProps) {
  return (
    <section
      className={[
        "overflow-hidden rounded-lg bg-panel px-5 py-8 text-panel-text sm:px-8 sm:py-10",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="max-w-2xl space-y-3">
        <h1 className="font-display text-h1 text-panel-text">{title}</h1>
        {subtitle ? <p className="text-body text-panel-muted">{subtitle}</p> : null}
        {children}
        {cta ? (
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <cta.LinkComponent
              href={cta.href}
              className="inline-flex min-h-11 items-center rounded bg-panel-text px-5 text-sm font-semibold text-panel transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:shadow-focusRing"
            >
              {cta.label}
            </cta.LinkComponent>
            {cta.pitch ? <span className="text-sm text-panel-muted">{cta.pitch}</span> : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
