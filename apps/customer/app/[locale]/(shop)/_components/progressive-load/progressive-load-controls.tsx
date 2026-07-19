"use client";

import { Button } from "@vergeo/ui/src/button";

import type { ProgressiveLoadStatus } from "./use-progressive-load";
import type { RefObject } from "react";

export type ProgressiveLoadControlsLabels = {
  loadMore: string;
  loading: string;
  moreLoaded: string;
  endOfResults: string;
  loadError: string;
  retry: string;
};

type ProgressiveLoadControlsProps = {
  status: ProgressiveLoadStatus;
  hasMore: boolean;
  lastAppendedCount: number;
  labels: ProgressiveLoadControlsLabels;
  onLoadMore: () => void;
  sentinelRef: RefObject<HTMLDivElement | null>;
  /** Optional test id prefix (e.g. "plp" → plp-load-more). */
  testIdPrefix?: string;
};

function formatCountLabel(template: string, count: number): string {
  return template.replace(/\{count\}/g, String(count));
}

/**
 * Baseline Load more + aria-live + end/retry. IntersectionObserver is handled
 * by the hook via `sentinelRef`; the button stays for keyboard / AT / failure.
 */
export function ProgressiveLoadControls({
  status,
  hasMore,
  lastAppendedCount,
  labels,
  onLoadMore,
  sentinelRef,
  testIdPrefix = "discovery",
}: ProgressiveLoadControlsProps) {
  const loading = status === "loading";
  const errored = status === "error";
  const complete = status === "complete" || (!hasMore && !errored && !loading);
  const showButton = hasMore || errored || loading;

  const liveMessage =
    lastAppendedCount > 0 ? formatCountLabel(labels.moreLoaded, lastAppendedCount) : "";

  return (
    <div className="flex flex-col items-center gap-2 pt-4">
      <div
        className="sr-only"
        aria-live="polite"
        aria-atomic="true"
        data-testid={`${testIdPrefix}-aria-live`}
      >
        {liveMessage}
      </div>

      {errored ? (
        <p className="text-sm text-text-2" role="alert" data-testid={`${testIdPrefix}-load-error`}>
          {labels.loadError}
        </p>
      ) : null}

      {complete && !errored ? (
        <p className="text-sm text-text-3" data-testid={`${testIdPrefix}-end-of-results`}>
          {labels.endOfResults}
        </p>
      ) : null}

      {showButton ? (
        <Button
          type="button"
          onClick={onLoadMore}
          disabled={loading}
          loading={loading}
          loadingLabel={labels.loading}
          data-testid={`${testIdPrefix}-load-more`}
        >
          {loading ? labels.loading : errored ? labels.retry : labels.loadMore}
        </Button>
      ) : null}

      {/* Sentinel for IntersectionObserver enhancement — not a focus target. */}
      {hasMore && !errored ? (
        <div
          ref={sentinelRef}
          aria-hidden="true"
          className="h-px w-full"
          data-testid={`${testIdPrefix}-load-sentinel`}
        />
      ) : null}
    </div>
  );
}
