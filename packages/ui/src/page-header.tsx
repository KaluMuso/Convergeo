import type { ReactNode } from "react";

import { Breadcrumbs, type BreadcrumbItem } from "./breadcrumbs";

export type PageHeaderProps = {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  breadcrumbs?: readonly BreadcrumbItem[];
  breadcrumbAriaLabel?: string;
  breadcrumbEllipsisLabel?: string;
  className?: string;
  "data-testid"?: string;
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/**
 * Consistent page chrome: optional breadcrumb, title, subtitle, trailing actions.
 */
export function PageHeader({
  title,
  subtitle,
  actions,
  breadcrumbs,
  breadcrumbAriaLabel = "Breadcrumb",
  breadcrumbEllipsisLabel = "…",
  className,
  "data-testid": dataTestId,
}: PageHeaderProps) {
  return (
    <header
      data-testid={dataTestId ?? "page-header"}
      className={cx("flex flex-col gap-3 border-b border-border pb-5", className)}
    >
      {breadcrumbs && breadcrumbs.length > 0 ? (
        <Breadcrumbs
          items={[...breadcrumbs]}
          ariaLabel={breadcrumbAriaLabel}
          ellipsisLabel={breadcrumbEllipsisLabel}
        />
      ) : null}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <h1 className="font-display text-h2 tracking-tight text-display-ink">{title}</h1>
          {subtitle ? <p className="max-w-prose text-body text-text-2">{subtitle}</p> : null}
        </div>
        {actions ? (
          <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
        ) : null}
      </div>
    </header>
  );
}
