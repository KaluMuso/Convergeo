import type { MetadataRoute } from "next";

// Vendor app is auth-gated on a separate origin — never indexed.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      disallow: "/",
    },
  };
}
