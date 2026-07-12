import { tokens } from "@vergeo/ui/tokens";

import type { MetadataRoute } from "next";

/**
 * PWA web manifest — M16-P02. Colors come from the shared design tokens
 * (`packages/ui`); no ad-hoc values. `start_url` uses the default locale
 * (manifest is a single, non-localized document at `/manifest.webmanifest`).
 * Icons reference an existing authored asset in `public/` (no unverifiable
 * binaries added).
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Vergeo5",
    short_name: "Vergeo5",
    description: "Discover products, services, and events across Zambia.",
    start_url: "/en",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: tokens.colors.bg,
    theme_color: tokens.colors.primary,
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any",
      },
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "maskable",
      },
    ],
  };
}
