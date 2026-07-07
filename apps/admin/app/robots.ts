import type { MetadataRoute } from "next";

// Admin is a private, auth-gated tool on a separate origin (D20) — never indexed.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      disallow: "/",
    },
  };
}
