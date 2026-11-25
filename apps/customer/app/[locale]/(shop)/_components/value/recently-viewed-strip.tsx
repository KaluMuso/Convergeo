import dynamic from "next/dynamic";

import type { RecentlyViewedStripLabels } from "./recently-viewed-strip.client";

const RecentlyViewedStripClient = dynamic(
  () => import("./recently-viewed-strip.client").then((mod) => mod.RecentlyViewedStripClient),
  { ssr: false },
);

export type { RecentlyViewedStripLabels };

type RecentlyViewedStripProps = {
  locale: string;
  currentSlug: string;
  labels: RecentlyViewedStripLabels;
};

/** Lazy-loaded recently viewed rail for product detail (below the fold). */
export function RecentlyViewedStrip(props: RecentlyViewedStripProps) {
  return <RecentlyViewedStripClient {...props} />;
}
