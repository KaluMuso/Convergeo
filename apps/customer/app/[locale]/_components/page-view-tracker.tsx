"use client";

import { trackPageView } from "@vergeo/analytics";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

/**
 * analytics_v2 page_view emitter (Convergeo Intelligence 1A-04). Renders nothing.
 * `trackPageView` is a no-op unless the build sets NEXT_PUBLIC_ANALYTICS_V2_TRACKING=1,
 * and it records only a page template key — never the URL, slug or query string.
 */
export function PageViewTracker(): null {
  const pathname = usePathname();
  useEffect(() => {
    trackPageView();
  }, [pathname]);
  return null;
}
