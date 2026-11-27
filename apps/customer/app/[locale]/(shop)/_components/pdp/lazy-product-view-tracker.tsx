"use client";

import dynamic from "next/dynamic";

/** Render-less analytics / recently-viewed side effect: never needed for first paint. */
export const LazyProductViewTracker = dynamic(
  () => import("./product-view-tracker").then((mod) => mod.ProductViewTracker),
  { ssr: false, loading: () => null },
);
