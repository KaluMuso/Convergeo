"use client";

import type { ComponentType, ReactNode } from "react";

export type LoadMorePaginationProps = {
  onLoadMore: () => void;
  loading: boolean;
  remainingCount?: number;
  loadMoreLabel: ReactNode;
  loadingLabel: ReactNode;
  remainingLabel?: (count: number) => ReactNode;
  className?: string;
  disabled?: boolean;
};

export type NumberedPaginationProps = {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  previousLabel: ReactNode;
  nextLabel: ReactNode;
  pageLabel: (page: number) => ReactNode;
  ariaLabel: string;
  className?: string;
};

function mergeClasses(...classes: Array<string | false | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

/** Primary pagination pattern — load more for data-frugal mobile feeds. */
export function LoadMorePagination({
  onLoadMore,
  loading,
  remainingCount,
  loadMoreLabel,
  loadingLabel,
  remainingLabel,
  className,
  disabled = false,
}: LoadMorePaginationProps) {
  return (
    <div className={mergeClasses("flex flex-col items-center gap-2 py-4", className)}>
      {remainingCount != null && remainingCount > 0 && remainingLabel ? (
        <p className="text-sm text-text-2">{remainingLabel(remainingCount)}</p>
      ) : null}
      <button
        type="button"
        onClick={onLoadMore}
        disabled={disabled || loading}
        aria-busy={loading}
        className={mergeClasses(
          "inline-flex min-h-11 min-w-44 items-center justify-center rounded-lg border border-border bg-surface px-6 py-2 text-sm font-semibold text-primary transition-colors",
          "hover:bg-primary-tint focus-visible:outline-none focus-visible:shadow-focusRing disabled:cursor-not-allowed disabled:opacity-50",
        )}
        style={{ transitionTimingFunction: "var(--ease-std)" }}
      >
        {loading ? loadingLabel : loadMoreLabel}
      </button>
    </div>
  );
}

type PageButtonProps = {
  page: number;
  current: boolean;
  onClick: () => void;
  label: ReactNode;
};

function PageButton({ page, current, onClick, label }: PageButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={current ? "page" : undefined}
      aria-label={typeof label === "string" ? label : undefined}
      className={mergeClasses(
        "inline-flex min-h-11 min-w-11 items-center justify-center rounded text-sm font-medium transition-colors focus-visible:outline-none focus-visible:shadow-focusRing",
        current ? "bg-primary text-surface" : "text-primary hover:bg-primary-tint",
      )}
      style={{ transitionTimingFunction: "var(--ease-std)" }}
    >
      {label}
    </button>
  );
}

/** Secondary numbered pager for admin tables. */
export function NumberedPagination({
  page,
  totalPages,
  onPageChange,
  previousLabel,
  nextLabel,
  pageLabel,
  ariaLabel,
  className,
}: NumberedPaginationProps) {
  const canGoPrev = page > 1;
  const canGoNext = page < totalPages;

  const pages = Array.from({ length: totalPages }, (_, i) => i + 1);

  return (
    <nav aria-label={ariaLabel} className={mergeClasses("flex items-center gap-1", className)}>
      <button
        type="button"
        onClick={() => onPageChange(page - 1)}
        disabled={!canGoPrev}
        className={mergeClasses(
          "inline-flex min-h-11 items-center justify-center rounded px-3 text-sm font-medium text-primary",
          "hover:bg-primary-tint focus-visible:outline-none focus-visible:shadow-focusRing disabled:cursor-not-allowed disabled:opacity-50",
        )}
        style={{ transitionTimingFunction: "var(--ease-std)" }}
      >
        {previousLabel}
      </button>
      <div className="flex items-center gap-0.5">
        {pages.map((p) => (
          <PageButton
            key={p}
            page={p}
            current={p === page}
            onClick={() => onPageChange(p)}
            label={pageLabel(p)}
          />
        ))}
      </div>
      <button
        type="button"
        onClick={() => onPageChange(page + 1)}
        disabled={!canGoNext}
        className={mergeClasses(
          "inline-flex min-h-11 items-center justify-center rounded px-3 text-sm font-medium text-primary",
          "hover:bg-primary-tint focus-visible:outline-none focus-visible:shadow-focusRing disabled:cursor-not-allowed disabled:opacity-50",
        )}
        style={{ transitionTimingFunction: "var(--ease-std)" }}
      >
        {nextLabel}
      </button>
    </nav>
  );
}

/** @deprecated Use LoadMorePagination — load-more is the primary export. */
export const Pagination = LoadMorePagination;
