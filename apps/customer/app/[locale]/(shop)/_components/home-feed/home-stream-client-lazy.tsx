"use client";

import dynamic from "next/dynamic";

/**
 * The stream's load-more controls (progressive-load hook, fetch, skeletons)
 * sit below every home section, so they load as an async chunk outside the
 * home route's first-load JS. SSR stays on: the first page of listings is in
 * the server HTML; only the "load more" control waits for the chunk.
 */
export const HomeStreamClient = dynamic(
  () => import("./home-stream-client").then((mod) => mod.HomeStreamClient),
  { ssr: true },
);
