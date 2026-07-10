import { getSiteUrl } from "@vergeo/ui/src/seo/json-ld";

import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  const siteUrl = getSiteUrl();

  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: [
          "/*/checkout",
          "/*/checkout/",
          "/*/cart",
          "/*/account",
          "/*/account/",
          "/*/admin",
          "/*/admin/",
        ],
      },
    ],
    sitemap: `${siteUrl}/sitemap.xml`,
    host: siteUrl,
  };
}
