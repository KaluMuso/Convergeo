"use client";

import { PageHeader } from "@vergeo/ui/src/page-header";

import type { BreadcrumbItem } from "@vergeo/ui/src/breadcrumbs";
import type { ReactNode } from "react";

export type AdminPageClientProps = {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  breadcrumbs?: readonly BreadcrumbItem[];
  children: ReactNode;
  className?: string;
  "data-testid"?: string;
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/** Client-route chrome matching the server AdminPage wrapper. */
export function AdminPageClient({
  title,
  subtitle,
  actions,
  breadcrumbs,
  children,
  className,
  "data-testid": dataTestId,
}: AdminPageClientProps) {
  return (
    <div
      className={cx("animate-page-in mx-auto w-full max-w-7xl space-y-4", className)}
      data-testid={dataTestId}
    >
      <PageHeader title={title} subtitle={subtitle} actions={actions} breadcrumbs={breadcrumbs} />
      {children}
    </div>
  );
}
