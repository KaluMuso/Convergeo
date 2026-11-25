import type { ReactNode } from "react";

export type SectionCardProps = {
  title?: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  "data-testid"?: string;
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/** Bordered content section with optional heading and footer slot. */
export function SectionCard({
  title,
  description,
  children,
  footer,
  className,
  "data-testid": dataTestId,
}: SectionCardProps) {
  return (
    <section
      data-testid={dataTestId ?? "section-card"}
      className={cx("rounded-xl border border-border bg-surface shadow-1", className)}
    >
      {title || description ? (
        <header className="border-b border-border px-4 py-3">
          {title ? <h2 className="text-h3 font-semibold text-display-ink">{title}</h2> : null}
          {description ? <p className="mt-1 text-sm text-text-2">{description}</p> : null}
        </header>
      ) : null}
      <div className="p-4">{children}</div>
      {footer ? (
        <footer className="border-t border-border px-4 py-3 text-sm text-text-2">{footer}</footer>
      ) : null}
    </section>
  );
}
