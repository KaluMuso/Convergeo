import { tokens } from "@vergeo/ui/tokens";

import type { MetadataRoute } from "next";

/**
 * PWA web manifest — Convergeo vendor portal. Icons from `public/brand/`
 * (same founder artwork as the customer app). `start_url` uses the default locale.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Convergeo Vendor",
    short_name: "Vendor",
    description: "Manage listings, orders, events, and payouts for your business on Convergeo.",
    start_url: "/en",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#000000",
    theme_color: tokens.colors.primary,
    icons: [
      {
        src: "/brand/convergeo-icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/brand/convergeo-icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/brand/convergeo-icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
