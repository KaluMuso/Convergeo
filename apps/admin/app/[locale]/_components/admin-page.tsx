import { PageHeader } from "@vergeo/ui/src/page-header";

import type { BreadcrumbItem } from "@vergeo/ui/src/breadcrumbs";
import type { ReactNode } from "react";

export type AdminPageProps = {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  breadcrumbs?: readonly BreadcrumbItem[];
  breadcrumbAriaLabel?: string;
  children: ReactNode;
  className?: string;
  "data-testid"?: string;
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/** Consistent route chrome: PageHeader + page-in motion + max width. */
export function AdminPage({
  title,
  subtitle,
  actions,
  breadcrumbs,
  breadcrumbAriaLabel,
  children,
  className,
  "data-testid": dataTestId,
}: AdminPageProps) {
  return (
    <div
      className={cx("animate-page-in mx-auto w-full max-w-7xl space-y-4", className)}
      data-testid={dataTestId}
    >
      <PageHeader
        title={title}
        subtitle={subtitle}
        actions={actions}
        breadcrumbs={breadcrumbs}
        breadcrumbAriaLabel={breadcrumbAriaLabel}
      />
      {children}
    </div>
  );
}
