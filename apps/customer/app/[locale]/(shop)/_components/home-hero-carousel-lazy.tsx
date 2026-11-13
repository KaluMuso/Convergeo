"use client";

import dynamic from "next/dynamic";

/**
 * The hero carousel (auto-advance, swipe, keyboard, reduced-data handling) is
 * split into an async chunk so it does not count toward the home route's
 * first-load JS. SSR stays on (next/dynamic default), so slide 1 is still in
 * the server HTML and paints for LCP; only hydration of the controls waits
 * for the chunk.
 */
export const HomeHeroCarousel = dynamic(
  () => import("./home-hero-carousel").then((mod) => mod.HomeHeroCarousel),
  { ssr: true },
);
