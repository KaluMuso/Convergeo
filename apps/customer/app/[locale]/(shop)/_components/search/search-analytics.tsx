"use client";

import { track } from "@vergeo/analytics";
import { useEffect, useRef } from "react";

type SearchAnalyticsProps = {
  normalizedTerm: string;
  zeroResult: boolean;
  resultCount?: number;
};

/**
 * Fires a single consent-aware `search` beacon per query/result fingerprint.
 */
export function SearchAnalytics({
  normalizedTerm,
  zeroResult,
  resultCount,
}: SearchAnalyticsProps): null {
  const lastKey = useRef<string | null>(null);

  useEffect(() => {
    const key = `${normalizedTerm}|${zeroResult}|${resultCount ?? ""}`;
    if (!normalizedTerm || lastKey.current === key) {
      return;
    }
    lastKey.current = key;
    track(
      "search",
      zeroResult
        ? { normalized_term: normalizedTerm, zero_result: true }
        : {
            normalized_term: normalizedTerm,
            zero_result: false,
            result_count: resultCount ?? 0,
          },
    );
  }, [normalizedTerm, resultCount, zeroResult]);

  return null;
}
