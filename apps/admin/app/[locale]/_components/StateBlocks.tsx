"use client";

import type { ReactNode } from "react";

/** Shared loading placeholder: polite status + skeleton rows (no layout jump). */
export function LoadingBlock({ label, rows = 3 }: { label: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" className="space-y-2" data-testid="admin-loading">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <div
          key={index}
          aria-hidden="true"
          className="h-12 animate-pulse rounded-md border border-border bg-bg-2"
        />
      ))}
    </div>
  );
}

/** Shared empty state: says why it is empty and what to do next. */
export function EmptyBlock({
  title,
  body,
  action,
}: {
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <div
      className="space-y-1 rounded-md border border-dashed border-border bg-surface p-6 text-center"
      data-testid="admin-empty"
    >
      <p className="text-sm font-medium text-text">{title}</p>
      {body ? <p className="text-xs text-muted">{body}</p> : null}
      {action ? <div className="pt-2">{action}</div> : null}
    </div>
  );
}
