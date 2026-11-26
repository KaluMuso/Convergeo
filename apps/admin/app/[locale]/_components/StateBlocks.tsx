"use client";

import { EmptyState } from "@vergeo/ui/src/empty-state";
import { Skeleton } from "@vergeo/ui/src/skeleton";

import type { ReactNode } from "react";

/** Shared loading placeholder: polite status + skeleton rows (no layout jump). */
export function LoadingBlock({ label, rows = 4 }: { label: string; rows?: number }) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className="space-y-3"
      data-testid="admin-loading"
    >
      <span className="sr-only">{label}</span>
      <Skeleton shape="line" height="0.75rem" width="40%" />
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} shape="block" height="3rem" data-testid="admin-loading-row" />
      ))}
    </div>
  );
}

/** Shared empty state with optional illustration. */
export function EmptyBlock({
  title,
  body,
  action,
  illustration,
}: {
  title: string;
  body?: string;
  action?: ReactNode;
  illustration?: import("@vergeo/ui/src/spot-illustrations").SpotIllustrationId;
}) {
  return (
    <EmptyState
      illustration={illustration ?? "no-results"}
      title={title}
      body={body}
      action={action}
      data-testid="admin-empty"
    />
  );
}
