import { getSiteUrl } from "@vergeo/ui/src/seo/json-ld";

import { ROBOTS_DISALLOW_SUFFIXES } from "../lib/seo/sitemap-eligibility";

import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  const siteUrl = getSiteUrl();

  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ROBOTS_DISALLOW_SUFFIXES.map((suffix) => `/*${suffix}`),
      },
    ],
    sitemap: `${siteUrl}/sitemap.xml`,
    host: siteUrl,
  };
}
