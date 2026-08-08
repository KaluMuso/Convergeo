import { tokens } from "@vergeo/ui/tokens";

import type { MetadataRoute } from "next";

/**
 * PWA web manifest — Convergeo brand icons from `public/icon-*.png`
 * (petal mark). `start_url` uses the default locale.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Convergeo",
    short_name: "Convergeo",
    description: "Discover products, services, and events across Zambia.",
    start_url: "/en",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#000000",
    theme_color: tokens.colors.primary,
    icons: [
      {
        src: "/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
