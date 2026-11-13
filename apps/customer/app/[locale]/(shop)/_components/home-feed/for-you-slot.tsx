"use client";

import { useEffect, useState, type ComponentType, type ReactNode } from "react";

import type { FeedLabels, FeedSection } from "./feed-types";

/**
 * Personalisation hook (foundation): the SSR `for_you` section is the shared,
 * cacheable guest version (trending). After idle, signed-in shoppers refetch the
 * first page with their bearer token; when the API answers with a `personal`
 * ranking the guest rail is swapped in place. Guests never load extra JS beyond
 * this wrapper.
 */
type IdleWindow = Window & {
  requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
};

export function ForYouSlot({
  children,
  locale,
  labels,
}: {
  children: ReactNode;
  locale: string;
  labels: FeedLabels;
}) {
  const [personal, setPersonal] = useState<{
    section: FeedSection;
    View: ComponentType<{
      section: FeedSection;
      locale: string;
      labels: FeedLabels;
    }>;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const { getReadyCustomerSession } = await import("../../../../../lib/customer-session");
        const session = await getReadyCustomerSession();
        if (!session?.access_token || cancelled) return;
        const [{ fetchFeedPage }, { FeedSectionView }] = await Promise.all([
          import("./feed-pages"),
          import("./feed-section"),
        ]);
        const page = await fetchFeedPage("v1.0", locale, session.access_token);
        const section = page.sections.find(
          (candidate) =>
            candidate.section_type === "for_you" && candidate.explanation?.basis === "personal",
        );
        if (section && !cancelled) setPersonal({ section, View: FeedSectionView });
      } catch {
        // Keep the guest rail.
      }
    };
    const idle = (window as IdleWindow).requestIdleCallback;
    if (idle) idle(() => void run(), { timeout: 4000 });
    else setTimeout(() => void run(), 1500);
    return () => {
      cancelled = true;
    };
  }, [locale]);

  if (personal) {
    const { View, section } = personal;
    return <View section={section} locale={locale} labels={labels} />;
  }
  return <>{children}</>;
}
