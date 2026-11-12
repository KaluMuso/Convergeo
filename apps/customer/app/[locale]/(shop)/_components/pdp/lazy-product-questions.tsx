"use client";

import dynamic from "next/dynamic";

/** Q&A is below the fold: keep it out of the PDP first-load bundle. */
export const LazyProductQuestions = dynamic(
  () => import("./product-questions").then((mod) => mod.ProductQuestions),
  { ssr: false, loading: () => null },
);
