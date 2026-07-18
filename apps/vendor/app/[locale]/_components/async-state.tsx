"use client";

import { EmptyState } from "@vergeo/ui/src/empty-state";
import { ErrorState } from "@vergeo/ui/src/error-state";

import type { ReactNode } from "react";

type VendorErrorStateProps = {
  title: string;
  body?: string;
  retryLabel: string;
  onRetry?: () => void;
  action?: ReactNode;
  "data-testid"?: string;
};

export function VendorErrorState({
  title,
  body,
  retryLabel,
  onRetry,
  action,
  "data-testid": dataTestId,
}: VendorErrorStateProps) {
  return (
    <ErrorState
      title={title}
      body={body}
      retryLabel={retryLabel}
      onRetry={onRetry}
      action={action}
      data-testid={dataTestId ?? "vendor-error-state"}
      className="min-h-[40vh]"
    />
  );
}

type VendorEmptyStateProps = {
  title: string;
  body?: string;
  action?: ReactNode;
  "data-testid"?: string;
};

export function VendorEmptyState({
  title,
  body,
  action,
  "data-testid": dataTestId,
}: VendorEmptyStateProps) {
  return (
    <EmptyState
      title={title}
      body={body}
      action={action}
      data-testid={dataTestId ?? "vendor-empty-state"}
      className="rounded-lg border border-dashed border-border"
    />
  );
}
